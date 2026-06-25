import gc
import os
from collections import deque
from typing import Any, cast

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlApplicationEngine

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
from scihub_eva.globals.versions import APPLICATION_VERSION
from scihub_eva.ui.captcha import UICaptcha
from scihub_eva.ui.preferences import UIPreferences
from scihub_eva.utils.api_utils import gen_range_query_list, is_range_query
from scihub_eva.utils.logging_utils import (
    DEFAULT_LOG_DIRECTORY,
    DEFAULT_LOG_FILE,
    DEFAULT_LOGGER,
    LOGGER_SEP,
    UISciHubEVALogHandler,
)
from scihub_eva.utils.network_utils import get_session
from scihub_eva.utils.preferences_utils import Preferences
from scihub_eva.utils.download_log import DOWNLOAD_LOG_FILE
from scihub_eva.utils.sys_utils import (
    PYTHON_VERSION,
    QT_VERSION,
    is_text_file,
    open_directory,
    open_file,
)
from scihub_eva.utils.ui_utils import center_window


class UISciHubEVA(QObject):
    set_save_to_dir = Signal(str)
    append_log = Signal(str)
    before_rampage = Signal()
    after_rampage = Signal()
    update_progress = Signal(int, int, int, int)   # completed, total, success, failed
    update_task_row = Signal(str, str, str, str)    # doi, mirror, speed, status
    set_paused = Signal(bool)

    # Internal signal to route worker-thread callbacks back to the main thread
    _rampage_done = Signal(str, object, object)

    def __init__(self) -> None:
        super(UISciHubEVA, self).__init__()

        self._engine = QQmlApplicationEngine()
        self._engine.rootContext().setContextProperty(
            'APPLICATION_VERSION', APPLICATION_VERSION
        )
        self._engine.rootContext().setContextProperty('PYTHON_VERSION', PYTHON_VERSION)
        self._engine.rootContext().setContextProperty('QT_VERSION', QT_VERSION)
        self._engine.load('qrc:/ui/SciHubEVA.qml')
        self._window = self._engine.rootObjects()[0]

        self._logger = DEFAULT_LOGGER
        self._logger.addHandler(UISciHubEVALogHandler(self))

        self._connect()

        self._ui_preferences = UIPreferences(self)
        self._ui_captcha = UICaptcha(self, self._logger)

        self._query_list: deque = deque()
        self._query_list_length = 0
        self._captcha_img_file_path: str = ''
        self._failed_queries: set = set()
        self._success_count = 0
        self._failed_count = 0
        self._completed_count = 0
        self._is_paused = False

        # Parallel download: list of active SciHubAPI threads (main-thread only)
        self._active_apis: list[SciHubAPI] = []

        self._save_to_dir = Preferences.get_or_default(
            FILE_SAVE_TO_DIR_KEY, FILE_SAVE_TO_DIR_DEFAULT
        )
        self.set_save_to_dir.emit(self._save_to_dir)

        self._scihub_url = Preferences.get_or_default(
            API_SCIHUB_URL_KEY, API_SCIHUB_URL_DEFAULT
        )

    @property
    def window(self) -> QWindow:
        return cast(QWindow, self._window)

    def _connect(self) -> None:
        self.window.openSaveToDir.connect(self.open_save_to_dir)  # type: ignore
        self.window.systemOpenSaveToDir.connect(self.system_open_save_to_dir)  # type: ignore
        self.window.showUIPreference.connect(self.show_ui_preference)  # type: ignore
        self.window.systemOpenLogFile.connect(self.system_open_log_file)  # type: ignore
        self.window.systemOpenLogDirectory.connect(self.system_open_log_directory)  # type: ignore
        self.window.systemOpenDownloadLog.connect(self.system_open_download_log)  # type: ignore
        self.window.exportFailedQueries.connect(self.export_failed_queries)  # type: ignore
        self.window.rampage.connect(self.rampage)  # type: ignore
        self.window.pauseRampage.connect(self.pause_rampage)  # type: ignore
        self.window.resumeRampage.connect(self.resume_rampage)  # type: ignore

        self.set_save_to_dir.connect(self.window.setSaveToDir)  # type: ignore
        self.append_log.connect(self.window.appendLog)  # type: ignore
        self.before_rampage.connect(self.window.beforeRampage)  # type: ignore
        self.after_rampage.connect(self.window.afterRampage)  # type: ignore
        self.update_progress.connect(self.window.updateProgress)  # type: ignore
        self.update_task_row.connect(self.window.updateTaskRow)  # type: ignore
        self.set_paused.connect(self.window.setPaused)  # type: ignore

        self._rampage_done.connect(self._on_rampage_done)  # type: ignore

    @Slot(str)
    def open_save_to_dir(self, directory: str) -> None:
        self._save_to_dir = directory
        Preferences.set(FILE_SAVE_TO_DIR_KEY, directory)

    @Slot(str)
    def system_open_save_to_dir(self, directory: str) -> None:
        if os.path.exists(directory):
            open_directory(directory)

    @Slot()
    def show_ui_preference(self) -> None:
        self._ui_preferences.load_preferences()
        self._ui_preferences.show.emit()
        center_window(self._ui_preferences.window, self.window)

    @Slot()
    def system_open_log_file(self) -> None:
        open_file(DEFAULT_LOG_FILE)

    @Slot()
    def system_open_log_directory(self) -> None:
        open_directory(DEFAULT_LOG_DIRECTORY)

    @Slot()
    def system_open_download_log(self) -> None:
        open_file(DOWNLOAD_LOG_FILE)

    @Slot()
    def pause_rampage(self) -> None:
        self._is_paused = True
        self.set_paused.emit(True)
        self._logger.info(
            self.tr('Paused. {} queries remaining.').format(len(self._query_list))
        )

    @Slot()
    def resume_rampage(self) -> None:
        self._is_paused = False
        self.set_paused.emit(False)
        self._logger.info(self.tr('Resumed.'))
        self.rampage_query_list()

    @Slot(str)
    def export_failed_queries(self, path: str) -> None:
        with open(path, 'wt') as f:
            for failed_query in self._failed_queries:
                f.write(failed_query + '\n')

        self._failed_queries.clear()

    @Slot(str)
    def rampage(self, raw_query: str) -> None:
        scihub_url = Preferences.get_or_default(
            API_SCIHUB_URL_KEY, API_SCIHUB_URL_DEFAULT
        )
        if self._scihub_url != scihub_url:
            self._scihub_url = scihub_url

        if os.path.exists(raw_query):
            if is_text_file(raw_query):
                self._query_list = deque()

                seen: set = set()
                with open(raw_query, 'rt') as f:
                    for line in f:
                        cleaned_line = line.strip()
                        if cleaned_line and cleaned_line not in seen:
                            seen.add(cleaned_line)
                            self._query_list.append(cleaned_line)

                self._query_list_length = len(self._query_list)
                self._success_count = 0
                self._failed_count = 0
                self._completed_count = 0
                self.update_progress.emit(0, self._query_list_length, 0, 0)
                for q in self._query_list:
                    self.update_task_row.emit(q, '', '', 'queued')
                self.before_rampage.emit()
                self.rampage_query_list()
            else:
                self._logger.error(LOGGER_SEP)
                self._logger.error(self.tr('Query list file is not a text file!'))
        elif is_range_query(raw_query):
            self._query_list = deque(gen_range_query_list(raw_query))
            self._query_list_length = len(self._query_list)
            self._success_count = 0
            self._failed_count = 0
            self._completed_count = 0
            self.update_progress.emit(0, self._query_list_length, 0, 0)
            for q in self._query_list:
                self.update_task_row.emit(q, '', '', 'queued')
            self.before_rampage.emit()
            self.rampage_query_list()
        else:
            self._query_list_length = 1
            self._success_count = 0
            self._failed_count = 0
            self._completed_count = 0
            self.update_progress.emit(0, 1, 0, 0)
            self.update_task_row.emit(raw_query, '', '', 'queued')
            self.before_rampage.emit()
            self.rampage_query(raw_query)

    def _concurrency(self) -> int:
        value = Preferences.get_or_default(
            NETWORK_CONCURRENCY_KEY, NETWORK_CONCURRENCY_DEFAULT, value_type=int
        )
        return max(1, min(value, 5))

    def rampage_query_list(self) -> None:
        """Fill all available concurrency slots from the queue."""
        if self._is_paused:
            return

        scihub_urls = Preferences.get_or_default(
            API_SCIHUB_URLS_KEY, API_SCIHUB_URLS_DEFAULT, value_type=list
        )
        limit = self._concurrency()

        while len(self._active_apis) < limit and self._query_list:
            query = self._query_list.popleft()
            done_so_far = self._query_list_length - len(self._query_list)
            self._logger.info(LOGGER_SEP)
            self._logger.info(
                self.tr('Dealing with {}/{} query ...').format(
                    done_so_far, self._query_list_length
                )
            )
            self.update_task_row.emit(query, '', '', 'resolving')
            api = SciHubAPI(
                self._logger,
                self.rampage_callback,
                self._scihub_url,
                get_session(self._scihub_url),
                raw_query=query,
                query=query,
                rampage_type=SciHubAPIRampageType.RAW,
                scihub_urls=scihub_urls,
            )
            self._active_apis.append(api)
            api.start()

    def rampage_query(self, query: str) -> None:
        """Start a single query outside of the list flow (direct DOI input)."""
        scihub_urls = Preferences.get_or_default(
            API_SCIHUB_URLS_KEY, API_SCIHUB_URLS_DEFAULT, value_type=list
        )
        api = SciHubAPI(
            self._logger,
            self.rampage_callback,
            self._scihub_url,
            get_session(self._scihub_url),
            raw_query=query,
            query=query,
            rampage_type=SciHubAPIRampageType.RAW,
            scihub_urls=scihub_urls,
        )
        self._active_apis.append(api)
        api.start()

    def rampage_with_typed_captcha(self, captcha_answer: str) -> None:
        if self._active_apis:
            self._active_apis[-1].captcha_answer = captcha_answer
        self.remove_captcha_img()
        self._active_apis[-1].start()

    def rampage_callback(self, raw_query: str, res: Any, err: Any) -> None:
        """Called from a worker thread — route to main thread via Signal."""
        self._rampage_done.emit(raw_query, res, err)

    @Slot(str, object, object)
    def _on_rampage_done(self, raw_query: str, res: Any, err: Any) -> None:
        """Runs on the main thread. Update state and fill empty slots."""
        # Remove finished API from active list
        self._active_apis = [a for a in self._active_apis if a.raw_query != raw_query]

        self._completed_count += 1

        if err in (
            SciHubAPIError.UNKNOWN,
            SciHubAPIError.WRONG_CAPTCHA,
            SciHubAPIError.NO_VALID_PDF,
        ):
            self._failed_queries.add(raw_query)
            self._failed_count += 1
            self.update_task_row.emit(raw_query, '', '', 'failed:' + err.name)
        elif err is None:
            self._failed_queries.discard(raw_query)
            self._success_count += 1
            self.update_task_row.emit(raw_query, '', '', 'success')

        self.update_progress.emit(
            self._completed_count,
            self._query_list_length,
            self._success_count,
            self._failed_count,
        )

        if err == SciHubAPIError.BLOCKED_BY_CAPTCHA:
            # Captcha only blocks this slot; other slots keep running
            self._failed_queries.add(raw_query)
            self._failed_count += 1
            self.update_task_row.emit(raw_query, '', '', 'failed:CAPTCHA')
            self._logger.warning(
                self.tr('Captcha encountered for {}, added to failed list.').format(
                    raw_query
                )
            )

        # Refill slots from the queue
        if self._query_list:
            self.rampage_query_list()

        # All slots empty and queue exhausted — done
        if not self._active_apis and not self._query_list:
            self.after_rampage.emit()

    def show_captcha(self, pdf_captcha_response: Any) -> None:
        captcha_api = self._active_apis[-1] if self._active_apis else None
        raw_query = captcha_api.raw_query if captcha_api else None

        scihub_urls = Preferences.get_or_default(
            API_SCIHUB_URLS_KEY, API_SCIHUB_URLS_DEFAULT, value_type=list
        )

        new_api = SciHubAPI(
            self._logger,
            self.rampage_callback,
            self._scihub_url,
            get_session(self._scihub_url),
            raw_query=raw_query,
            query=pdf_captcha_response,
            rampage_type=SciHubAPIRampageType.WITH_CAPTCHA,
            scihub_urls=scihub_urls,
        )

        # Replace the finished api with the captcha-mode one
        if captcha_api in self._active_apis:
            idx = self._active_apis.index(captcha_api)
            self._active_apis[idx] = new_api
            gc.collect()
        else:
            self._active_apis.append(new_api)

        _, captcha_img_url = new_api.get_captcha_info(pdf_captcha_response)
        captcha_img_file_path = new_api.download_captcha_img(captcha_img_url)
        self._captcha_img_file_path = captcha_img_file_path.resolve().as_posix()
        captcha_img_local_uri = captcha_img_file_path.as_uri()

        self._ui_captcha.show_ui_captcha.emit(captcha_img_local_uri)
        center_window(self._ui_captcha.window, self.window)

    def remove_captcha_img(self) -> None:
        if os.path.exists(self._captcha_img_file_path) and os.path.isfile(
            self._captcha_img_file_path
        ):
            os.remove(self._captcha_img_file_path)
