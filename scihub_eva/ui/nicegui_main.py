"""NiceGUI front-end for SciHub EVA — renders in the local browser at localhost:8080."""
from __future__ import annotations

import os
import queue
from typing import Any

from nicegui import ui

from scihub_eva.core.manager import DownloadManager
from scihub_eva.globals.preferences import (
    API_SCIHUB_URL_DEFAULT,
    API_SCIHUB_URL_KEY,
    API_SCIHUB_URLS_DEFAULT,
    API_SCIHUB_URLS_KEY,
    FILE_SAVE_TO_DIR_DEFAULT,
    FILE_SAVE_TO_DIR_KEY,
    NETWORK_CONCURRENCY_DEFAULT,
    NETWORK_CONCURRENCY_KEY,
    NETWORK_TIMEOUT_DEFAULT,
    NETWORK_TIMEOUT_KEY,
)
from scihub_eva.globals.versions import APPLICATION_NAME, APPLICATION_VERSION
from scihub_eva.utils.download_log import DOWNLOAD_LOG_FILE
from scihub_eva.utils.logging_utils import (
    DEFAULT_LOG_FILE,
    DEFAULT_LOGGER,
    CallbackLogHandler,
)
from scihub_eva.utils.preferences_utils import Preferences
from scihub_eva.utils.sys_utils import open_directory, open_file

# ── thread-safe log buffer ────────────────────────────────────────────────────
# Worker threads write to this queue; the UI timer drains it on the main thread.
_LOG_BUFFER: queue.SimpleQueue = queue.SimpleQueue()
_log_handler = CallbackLogHandler(_LOG_BUFFER.put)
DEFAULT_LOGGER.addHandler(_log_handler)

# ── status helpers ─────────────────────────────────────────────────────────────
_STATUS_ICONS: dict[str, str] = {
    'queued': '⏳',
    'resolving': '🔍',
    'success': '✓',
    'skipped': '⏭',
    'failed': '✗',
}

_STATUS_COLORS: dict[str, str] = {
    'success': 'positive',
    'skipped': 'warning',
    'failed': 'negative',
    'resolving': 'primary',
    'queued': '',
}


def _icon_for(status: str) -> str:
    for prefix, icon in _STATUS_ICONS.items():
        if status == prefix or status.startswith(prefix + ':'):
            return icon
    return '?'


def _color_for(status: str) -> str:
    for prefix, color in _STATUS_COLORS.items():
        if status == prefix or status.startswith(prefix + ':'):
            return color
    return ''


def _label_for(status: str) -> str:
    mapping = {
        'queued': 'Queued',
        'resolving': 'Resolving…',
        'success': 'Saved',
        'skipped': 'Skipped (exists)',
    }
    if status in mapping:
        return mapping[status]
    if status.startswith('failed:'):
        reason = status[7:].replace('_', ' ').title()
        return f'Failed ({reason})'
    return status.title()


# ── page factory ───────────────────────────────────────────────────────────────

def run_app() -> None:
    manager = DownloadManager()

    @ui.page('/')
    def index() -> None:  # noqa: C901
        # Per-page task state
        task_row_map: dict[str, dict] = {}

        dark = ui.dark_mode()

        # ── custom CSS ────────────────────────────────────────────────────────
        ui.add_head_html('''
        <style>
          .scihub-card { max-width: 900px; margin: 24px auto; }
          .task-icon   { font-size: 1.15em; }
          .q-table td  { white-space: nowrap; overflow: hidden;
                         text-overflow: ellipsis; max-width: 300px; }
        </style>
        ''')

        # ── layout ────────────────────────────────────────────────────────────
        with ui.card().classes('scihub-card w-full q-pa-md'):

            # Header
            with ui.row().classes('w-full items-center q-mb-xs'):
                ui.label(APPLICATION_NAME).classes('text-h5 text-weight-bold')
                ui.badge(APPLICATION_VERSION).props('color=grey-7 text-color=white')
                ui.space()
                ui.button(
                    icon='settings',
                    on_click=lambda: settings_dialog.open(),
                ).props('flat round dense')
                ui.button(icon='dark_mode', on_click=dark.toggle).props('flat round dense')

            ui.separator()

            # Query input
            query_in = ui.textarea(
                label='Query — DOI / PMID / URL, or path to a .txt file of queries',
                placeholder='10.1038/nature12373',
            ).classes('w-full q-mt-sm').props('outlined rows=3 dense')

            with ui.row().classes('w-full justify-end gap-2 q-mt-xs'):
                ui.button(
                    'Load from file', icon='upload_file', on_click=_load_from_file,
                ).props('flat dense color=secondary')
                rampage_btn = ui.button(
                    'Start Rampage', icon='rocket_launch', on_click=_start_rampage,
                ).props('color=primary unelevated')

            # Save directory
            saved_dir = (
                Preferences.get_or_default(FILE_SAVE_TO_DIR_KEY, FILE_SAVE_TO_DIR_DEFAULT) or ''
            )
            with ui.row().classes('w-full items-center gap-2 q-mt-xs'):
                save_dir_in = ui.input(
                    label='Save directory',
                    value=saved_dir,
                    on_change=lambda e: Preferences.set(FILE_SAVE_TO_DIR_KEY, e.value),
                ).classes('col-grow').props('outlined dense')
                ui.button(icon='folder_open', on_click=_browse_dir).props(
                    'flat dense'
                ).tooltip('Browse for folder')
                ui.button(icon='open_in_new', on_click=_open_save_dir).props(
                    'flat dense'
                ).tooltip('Open save folder')

            ui.separator().classes('q-mt-sm')

            # Progress row
            with ui.row().classes('w-full items-center gap-3 q-mt-sm'):
                progress_bar = ui.linear_progress(value=0).classes('col-grow').props(
                    'size=10px rounded'
                )
                prog_label = ui.label('0 / 0').classes('text-caption text-grey')
                ok_label = ui.label('✓ 0').classes('text-caption text-positive')
                fail_label = ui.label('✗ 0').classes('text-caption text-negative')
                pause_btn = ui.button(
                    'Pause', icon='pause', on_click=_toggle_pause,
                ).props('flat dense color=grey').classes('invisible')

            # Task table
            columns = [
                {
                    'name': 'icon', 'label': '', 'field': 'icon',
                    'align': 'center', 'style': 'width:40px',
                },
                {
                    'name': 'doi', 'label': 'Query / DOI', 'field': 'doi',
                    'align': 'left',
                },
                {
                    'name': 'mirror', 'label': 'Mirror', 'field': 'mirror',
                    'align': 'left', 'style': 'width:220px',
                },
                {
                    'name': 'state', 'label': 'State', 'field': 'state',
                    'align': 'left', 'style': 'width:160px',
                },
            ]
            task_table = ui.table(
                columns=columns, rows=[], row_key='doi',
            ).classes('w-full q-mt-sm').props('dense flat bordered virtual-scroll')
            task_table.add_slot(
                'body-cell-icon',
                r'''<q-td :props="props" class="task-icon">
                      <span :class="'text-' + (props.row.color || 'grey')">
                        {{ props.row.icon }}
                      </span>
                    </q-td>''',
            )
            task_table.add_slot(
                'body-cell-state',
                r'''<q-td :props="props">
                      <span :class="'text-' + (props.row.color || 'grey')">
                        {{ props.row.state }}
                      </span>
                    </q-td>''',
            )

            # Log expansion
            with ui.expansion('Logs', icon='article').classes('w-full q-mt-md'):
                with ui.row().classes('w-full justify-end gap-2 q-mb-xs'):
                    ui.button(
                        'Open log file', icon='description', on_click=_open_log_file,
                    ).props('flat dense color=secondary')
                    ui.button(
                        'Open download CSV', icon='table_view', on_click=_open_csv,
                    ).props('flat dense color=secondary')
                log_area = ui.log(max_lines=500).classes('w-full').style('height:220px; font-size:0.78rem')

        # ── settings dialog ───────────────────────────────────────────────────
        with ui.dialog() as settings_dialog, ui.card().classes('w-full').style('max-width:520px'):
            ui.label('Settings').classes('text-h6')
            ui.separator()

            with ui.column().classes('w-full gap-2 q-mt-sm'):
                sci_url_in = ui.input(
                    label='Primary Sci-Hub URL',
                    value=Preferences.get_or_default(
                        API_SCIHUB_URL_KEY, API_SCIHUB_URL_DEFAULT
                    ),
                ).classes('w-full').props('outlined dense')

                mirrors = Preferences.get_or_default(
                    API_SCIHUB_URLS_KEY, API_SCIHUB_URLS_DEFAULT, value_type=list
                )
                sci_urls_in = ui.textarea(
                    label='Mirror list (one URL per line)',
                    value='\n'.join(mirrors),
                ).classes('w-full').props('outlined rows=5 dense')

                concurrency_in = ui.number(
                    label='Parallel downloads (1–5)',
                    value=Preferences.get_or_default(
                        NETWORK_CONCURRENCY_KEY, NETWORK_CONCURRENCY_DEFAULT, value_type=int
                    ),
                    min=1, max=5, step=1,
                ).classes('w-full').props('outlined dense')

                timeout_in = ui.number(
                    label='Request timeout (ms)',
                    value=Preferences.get_or_default(
                        NETWORK_TIMEOUT_KEY, NETWORK_TIMEOUT_DEFAULT, value_type=int
                    ),
                    min=500, max=60000, step=500,
                ).classes('w-full').props('outlined dense')

            with ui.row().classes('w-full justify-end gap-2 q-mt-sm'):
                ui.button('Cancel', on_click=settings_dialog.close).props('flat')
                ui.button('Save', on_click=_save_settings).props('color=primary unelevated')

        # ── manager callbacks ─────────────────────────────────────────────────

        def _on_before_rampage() -> None:
            rampage_btn.disable()
            pause_btn.classes(remove='invisible')
            task_row_map.clear()
            task_table.rows.clear()
            task_table.update()

        def _on_after_rampage() -> None:
            rampage_btn.enable()
            pause_btn.classes(add='invisible')

        def _on_progress(completed: int, total: int, success: int, failed: int) -> None:
            frac = completed / total if total > 0 else 0.0
            progress_bar.value = frac
            prog_label.text = f'{completed} / {total}'
            ok_label.text = f'✓ {success}'
            fail_label.text = f'✗ {failed}'

        def _on_task(doi: str, mirror: str, _speed: str, status: str) -> None:
            icon = _icon_for(status)
            color = _color_for(status)
            state_label = _label_for(status)
            if doi in task_row_map:
                row = task_row_map[doi]
                row['icon'] = icon
                row['color'] = color
                if mirror:
                    row['mirror'] = mirror
                row['state'] = state_label
            else:
                row = {
                    'icon': icon, 'doi': doi,
                    'mirror': mirror, 'state': state_label,
                    'color': color,
                }
                task_row_map[doi] = row
                task_table.rows.append(row)
            task_table.update()

        def _on_paused(paused: bool) -> None:
            if paused:
                pause_btn._props['icon'] = 'play_arrow'
                pause_btn.text = 'Resume'
            else:
                pause_btn._props['icon'] = 'pause'
                pause_btn.text = 'Pause'
            pause_btn.update()

        def _on_notify_error(msg: str) -> None:
            ui.notify(msg, type='negative', position='top')

        manager.on_before_rampage = _on_before_rampage
        manager.on_after_rampage = _on_after_rampage
        manager.on_progress = _on_progress
        manager.on_task = _on_task
        manager.on_paused = _on_paused
        manager.on_notify_error = _on_notify_error

        # ── action handlers ───────────────────────────────────────────────────

        def _start_rampage() -> None:
            query = query_in.value.strip()
            if not query:
                ui.notify('Please enter a query.', type='warning', position='top')
                return
            save_dir = save_dir_in.value.strip()
            if save_dir:
                Preferences.set(FILE_SAVE_TO_DIR_KEY, save_dir)
            manager.start_rampage(query)

        def _toggle_pause() -> None:
            if manager.is_paused:
                manager.resume()
            else:
                manager.pause()

        def _load_from_file() -> None:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                path = filedialog.askopenfilename(
                    title='Select query list file',
                    filetypes=[('Text files', '*.txt'), ('All files', '*.*')],
                    parent=root,
                )
                root.destroy()
                if path:
                    query_in.set_value(path)
            except Exception as exc:
                ui.notify(f'File picker error: {exc}', type='warning', position='top')

        def _browse_dir() -> None:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                path = filedialog.askdirectory(
                    title='Select Save Directory', parent=root
                )
                root.destroy()
                if path:
                    save_dir_in.set_value(path)
                    Preferences.set(FILE_SAVE_TO_DIR_KEY, path)
            except Exception as exc:
                ui.notify(f'File picker error: {exc}', type='warning', position='top')

        def _open_save_dir() -> None:
            d = save_dir_in.value.strip()
            if d and os.path.isdir(d):
                open_directory(d)
            else:
                ui.notify(
                    'Save directory is not set or does not exist.',
                    type='warning', position='top',
                )

        def _open_log_file() -> None:
            open_file(str(DEFAULT_LOG_FILE))

        def _open_csv() -> None:
            open_file(str(DOWNLOAD_LOG_FILE))

        def _save_settings() -> None:
            Preferences.set(API_SCIHUB_URL_KEY, sci_url_in.value.strip())
            urls = [u.strip() for u in sci_urls_in.value.splitlines() if u.strip()]
            Preferences.set(API_SCIHUB_URLS_KEY, urls)
            Preferences.set(NETWORK_CONCURRENCY_KEY, int(concurrency_in.value or NETWORK_CONCURRENCY_DEFAULT))
            Preferences.set(NETWORK_TIMEOUT_KEY, int(timeout_in.value or NETWORK_TIMEOUT_DEFAULT))
            settings_dialog.close()
            ui.notify('Settings saved.', type='positive', position='top')

        # ── timer: drain done queue + log buffer ──────────────────────────────

        def _poll() -> None:
            manager.poll()
            while True:
                try:
                    msg = _LOG_BUFFER.get_nowait()
                except queue.Empty:
                    break
                log_area.push(msg)

        ui.timer(0.2, _poll)

    # ── launch ────────────────────────────────────────────────────────────────
    ui.run(
        title=f'{APPLICATION_NAME} {APPLICATION_VERSION}',
        port=8080,
        reload=False,
        favicon='🎓',
        show=True,
    )


__all__ = ['run_app']
