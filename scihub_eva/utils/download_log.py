import csv
import threading
from datetime import datetime
from pathlib import Path

from scihub_eva.utils.path_utils import LOGS_DIR

DOWNLOAD_LOG_FILE = LOGS_DIR / 'download_records.csv'
_CSV_LOCK = threading.Lock()
_CSV_FIELDS = ['timestamp', 'doi', 'filename', 'scihub_url', 'status']


def _ensure_header() -> None:
    if not DOWNLOAD_LOG_FILE.exists() or DOWNLOAD_LOG_FILE.stat().st_size == 0:
        with open(DOWNLOAD_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writeheader()


def record_download(
    doi: str,
    filename: str,
    scihub_url: str,
    status: str = 'success',
) -> None:
    """Thread-safe append of one download record to the CSV log."""
    with _CSV_LOCK:
        _ensure_header()
        with open(DOWNLOAD_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writerow({
                'timestamp': datetime.now().isoformat(timespec='seconds'),
                'doi': doi,
                'filename': filename,
                'scihub_url': scihub_url,
                'status': status,
            })


__all__ = ['DOWNLOAD_LOG_FILE', 'record_download']
