import multiprocessing
import os
import subprocess
import sys
from pathlib import Path


def _ensure_resources() -> None:
    """Recompile resources.py if any QML/image file is newer than it."""
    base = Path(__file__).parent
    qrc = base / 'SciHubEVA.qrc'
    resources_py = base / 'scihub_eva' / 'resources.py'

    # Collect all source files listed in the QRC
    sources = [qrc]
    try:
        import xml.etree.ElementTree as ET
        for f in ET.parse(qrc).iter('file'):
            sources.append(base / f.text.strip())
    except Exception:
        pass

    needs_rebuild = (
        not resources_py.exists()
        or any(
            s.exists() and s.stat().st_mtime > resources_py.stat().st_mtime
            for s in sources
        )
    )

    if needs_rebuild:
        print('[dev] Recompiling resources...', flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'PySide6.scripts.pyside_tool', 'rcc',
             str(qrc), '-o', str(resources_py)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # Fallback: try pyside6-rcc directly
            result = subprocess.run(
                ['pyside6-rcc', str(qrc), '-o', str(resources_py)],
                capture_output=True, text=True,
            )
        if result.returncode != 0:
            print('[dev] WARNING: resource recompile failed:', result.stderr, flush=True)
        else:
            print('[dev] Resources recompiled OK.', flush=True)


_ensure_resources()


from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtGui import QGuiApplication, QIcon

import scihub_eva.resources
from scihub_eva.globals.preferences import APPEARANCE_LANGUAGE_KEY
from scihub_eva.globals.versions import (
    APPLICATION_NAME,
    ORGANIZATION_DOMAIN,
    ORGANIZATION_NAME,
)
from scihub_eva.ui.main import UISciHubEVA
from scihub_eva.utils.path_utils import I18N_DIR, IMAGES_DIR
from scihub_eva.utils.preferences_utils import Preferences
from scihub_eva.utils.sys_utils import SYSTEM_LANGUAGE
from scihub_eva.utils.ui_utils import set_ui_env


def main() -> None:
    multiprocessing.freeze_support()

    set_ui_env()

    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setOrganizationDomain(ORGANIZATION_DOMAIN)
    QCoreApplication.setApplicationName(APPLICATION_NAME)

    app = QGuiApplication(sys.argv)

    lang = Preferences.get_or_default(APPEARANCE_LANGUAGE_KEY, SYSTEM_LANGUAGE)
    lang_file_path = (
        (I18N_DIR / 'SciHubEVA_{lang}.qm'.format(lang=lang)).resolve().as_posix()
    )

    if os.path.exists(lang_file_path):
        translator = QTranslator()
        translator.load(lang_file_path)
        app.installTranslator(translator)

    icon_file_path = (IMAGES_DIR / 'SciHubEVA-icon.png').resolve().as_posix()
    app.setWindowIcon(QIcon(icon_file_path))

    UISciHubEVA()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
