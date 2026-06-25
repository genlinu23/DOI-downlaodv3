"""Platform-aware INI-based preferences storage (replaces Qt QSettings)."""
import configparser
import json
from pathlib import Path
from typing import Any

from scihub_eva.globals.versions import APPLICATION_NAME, ORGANIZATION_DOMAIN
from scihub_eva.utils.sys_utils import is_macos, is_windows


def _settings_file_path() -> Path:
    if is_macos():
        config_dir = Path.home() / 'Library' / 'Preferences' / ORGANIZATION_DOMAIN
    elif is_windows():
        config_dir = Path.home() / 'AppData' / 'Roaming' / ORGANIZATION_DOMAIN
    else:
        config_dir = Path.home() / '.config' / ORGANIZATION_DOMAIN
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / f'{APPLICATION_NAME}.ini'


class Preferences:
    _config: configparser.RawConfigParser | None = None
    _file_path: Path | None = None

    def __init__(self) -> None:
        pass

    @classmethod
    def _load(cls) -> None:
        if cls._config is not None:
            return
        cls._file_path = _settings_file_path()
        cls._config = configparser.RawConfigParser()
        cls._config.optionxform = str  # preserve key case
        if cls._file_path.exists():
            cls._config.read(cls._file_path, encoding='utf-8')

    @classmethod
    def _save(cls) -> None:
        if cls._config is None or cls._file_path is None:
            return
        with open(cls._file_path, 'w', encoding='utf-8') as fh:
            cls._config.write(fh)

    @classmethod
    def _split_key(cls, key: str) -> tuple[str, str]:
        parts = key.split('/', 1)
        return (parts[0], parts[1]) if len(parts) == 2 else ('General', parts[0])

    @classmethod
    def contains(cls, key: str) -> bool:
        cls._load()
        assert cls._config is not None
        section, option = cls._split_key(key)
        return cls._config.has_option(section, option)

    @classmethod
    def get_or_default(
        cls, key: str, default: Any, value_type: type | None = None
    ) -> Any:
        cls._load()
        assert cls._config is not None
        section, option = cls._split_key(key)

        if not cls._config.has_option(section, option):
            return default

        raw = cls._config.get(section, option)

        if value_type is None and default is not None:
            value_type = type(default)

        if value_type is None:
            return raw
        if value_type is bool:
            return raw.lower() in ('true', '1', 'yes')
        if value_type is int:
            try:
                return int(raw)
            except ValueError:
                return default
        if value_type is float:
            try:
                return float(raw)
            except ValueError:
                return default
        if value_type is list:
            try:
                result = json.loads(raw)
                return result if isinstance(result, list) else default
            except Exception:
                return default
        return raw

    @classmethod
    def get(cls, key: str, value_type: type | None = None) -> Any:
        return cls.get_or_default(key, None, value_type=value_type)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        cls._load()
        assert cls._config is not None
        section, option = cls._split_key(key)
        if not cls._config.has_section(section):
            cls._config.add_section(section)
        if isinstance(value, list):
            cls._config.set(section, option, json.dumps(value, ensure_ascii=False))
        elif isinstance(value, bool):
            cls._config.set(section, option, str(value))
        else:
            cls._config.set(section, option, str(value))
        cls._save()

    @classmethod
    def remove(cls, key: str) -> None:
        cls._load()
        assert cls._config is not None
        section, option = cls._split_key(key)
        if cls._config.has_option(section, option):
            cls._config.remove_option(section, option)
            cls._save()


__all__ = ['Preferences']
