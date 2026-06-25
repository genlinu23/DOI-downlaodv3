"""Download manager — pure Python, no Qt dependency."""
from __future__ import annotations

import os
import queue
from collections import deque
from typing import Any, Callable

from scihub_eva.api.scihub_api import SciHubAPI, SciHubAPIError, SciHubAPIRampageType
from scihub_eva.globals.preferences import (
    API_SCIHUB_URL_DEFAULT,
    API_SCIHUB_URL_KEY,
    API_SCIHUB_URLS_DEFAULT,
    API_SCIHUB_URLS_KEY,
    FILE_SAVE_TO_DIR_DEFAULT,
    FILE_SAVE_TO_DIR_KEY,
    NETWORK_CONCURRENCY_DEFAULT,
    NETWORK_CONCURRENCY_KEY,
)
from scihub_eva.utils.api_utils import gen_range_query_list, is_range_query
from scihub_eva.utils.logging_utils import DEFAULT_LOGGER, LOGGER_SEP
from scihub_eva.utils.network_utils import get_session
from scihub_eva.utils.preferences_utils import Preferences
from scihub_eva.utils.sys_utils import is_text_file


class DownloadManager:
    """Manages a batch download session without any Qt dependencies.

    Thread-safety contract
    ----------------------
    * Worker (SciHubAPI daemon) threads are the only producers of ``_done_queue``.
    * The NiceGUI ``ui.timer`` callback calls ``poll()`` on the asyncio / main thread.
    * All ``on_*`` UI callbacks are invoked exclusively from ``poll()`` (main thread).
    """

    def __init__(self) -> None:
        # Worker → main thread bridge (only SciHubAPI threads write here)
        self._done_queue: queue.Queue = queue.Queue()

        # Batch state (main-thread only)
        self._query_list: deque = deque()
        self._query_list_length = 0
        self._active_apis: list[SciHubAPI] = []
        self._failed_queries: set[str] = set()
        self._success_count = 0
        self._failed_count = 0
        self._completed_count = 0
        self._is_paused = False
        self._is_running = False

        self._logger = DEFAULT_LOGGER

        # UI callbacks — assigned by the NiceGUI layer
        self.on_before_rampage: Callable[[], None] | None = None
        self.on_after_rampage: Callable[[], None] | None = None
        self.on_progress: Callable[[int, int, int, int], None] | None = None
        # on_task(doi, mirror, speed, status)
        self.on_task: Callable[[str, str, str, str], None] | None = None
        self.on_paused: Callable[[bool], None] | None = None
        self.on_notify_error: Callable[[str], None] | None = None

    # ── public API ──────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def start_rampage(self, raw_query: str) -> None:
        if self._is_running:
            return

        raw_query = raw_query.strip()
        if not raw_query:
            self._notify_error('Query is empty.')
            return

        save_dir = Preferences.get_or_default(FILE_SAVE_TO_DIR_KEY, FILE_SAVE_TO_DIR_DEFAULT)
        if not save_dir:
            self._notify_error('Please set the save directory first.')
            return

        queries = self._build_query_list(raw_query)
        if queries is None:
            return  # error already reported
        if not queries:
            self._notify_error('Query list is empty.')
            return

        self._begin_batch(queries)

    def pause(self) -> None:
        self._is_paused = True
        self._logger.info(f'Paused — {len(self._query_list)} queries remaining in queue.')
        if self.on_paused:
            self.on_paused(True)

    def resume(self) -> None:
        self._is_paused = False
        self._logger.info('Resumed.')
        if self.on_paused:
            self.on_paused(False)
        self._fill_slots()

    def poll(self) -> None:
        """Drain the done queue. Must be called from the main (asyncio) thread."""
        while True:
            try:
                raw_query, res, err = self._done_queue.get_nowait()
            except queue.Empty:
                break
            self._on_done(raw_query, res, err)

    # ── internal ─────────────────────────────────────────────────────────────

    def _notify_error(self, msg: str) -> None:
        if self.on_notify_error:
            self.on_notify_error(msg)
        else:
            self._logger.error(msg)

    def _build_query_list(self, raw_query: str) -> deque | None:
        if os.path.exists(raw_query):
            if not is_text_file(raw_query):
                self._notify_error('File is not a readable text file.')
                return None
            seen: set[str] = set()
            queries: deque = deque()
            with open(raw_query, 'rt') as fh:
                for line in fh:
                    q = line.strip()
                    if q and q not in seen:
                        seen.add(q)
                        queries.append(q)
            return queries
        if is_range_query(raw_query):
            return deque(gen_range_query_list(raw_query))
        return deque([raw_query])

    def _begin_batch(self, queries: deque) -> None:
        self._query_list = queries
        self._query_list_length = len(queries)
        self._active_apis = []
        self._failed_queries.clear()
        self._success_count = 0
        self._failed_count = 0
        self._completed_count = 0
        self._is_paused = False
        self._is_running = True

        if self.on_before_rampage:
            self.on_before_rampage()
        if self.on_progress:
            self.on_progress(0, self._query_list_length, 0, 0)
        if self.on_task:
            for q in self._query_list:
                self.on_task(q, '', '', 'queued')

        self._fill_slots()

    def _concurrency(self) -> int:
        v = Preferences.get_or_default(
            NETWORK_CONCURRENCY_KEY, NETWORK_CONCURRENCY_DEFAULT, value_type=int
        )
        return max(1, min(v, 5))

    def _primary_url(self) -> str:
        return Preferences.get_or_default(API_SCIHUB_URL_KEY, API_SCIHUB_URL_DEFAULT)

    def _fill_slots(self) -> None:
        if self._is_paused or not self._is_running:
            return
        scihub_urls: list[str] = Preferences.get_or_default(
            API_SCIHUB_URLS_KEY, API_SCIHUB_URLS_DEFAULT, value_type=list
        )
        limit = self._concurrency()
        while len(self._active_apis) < limit and self._query_list:
            query = self._query_list.popleft()
            scihub_url = self._primary_url()
            self._logger.info(LOGGER_SEP)
            self._logger.info(f'Starting download: {query}')
            if self.on_task:
                self.on_task(query, '', '', 'resolving')
            api = SciHubAPI(
                self._logger,
                self._rampage_callback,
                scihub_url,
                get_session(scihub_url),
                raw_query=query,
                query=query,
                rampage_type=SciHubAPIRampageType.RAW,
                scihub_urls=scihub_urls,
            )
            self._active_apis.append(api)
            api.start()

    def _rampage_callback(self, raw_query: str, res: Any, err: Any) -> None:
        """Called from worker thread — enqueue for main-thread processing."""
        self._done_queue.put((raw_query, res, err))

    def _on_done(self, raw_query: str, res: Any, err: Any) -> None:
        self._active_apis = [a for a in self._active_apis if a.raw_query != raw_query]
        self._completed_count += 1

        if err is None:
            self._success_count += 1
            status = 'success'
        elif err == SciHubAPIError.BLOCKED_BY_CAPTCHA:
            self._failed_count += 1
            self._failed_queries.add(raw_query)
            status = 'failed:captcha'
        else:
            self._failed_count += 1
            self._failed_queries.add(raw_query)
            status = f'failed:{err.name.lower()}'

        if self.on_task:
            self.on_task(raw_query, '', '', status)
        if self.on_progress:
            self.on_progress(
                self._completed_count, self._query_list_length,
                self._success_count, self._failed_count,
            )

        if self._query_list:
            self._fill_slots()
        elif not self._active_apis:
            self._is_running = False
            self._logger.info(LOGGER_SEP)
            self._logger.info(
                f'Batch complete — success: {self._success_count}, '
                f'failed: {self._failed_count} / {self._query_list_length}'
            )
            if self.on_after_rampage:
                self.on_after_rampage()


__all__ = ['DownloadManager']
