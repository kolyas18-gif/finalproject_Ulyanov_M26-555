import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "pyproject.toml"

DEFAULT_SETTINGS = {
    "data_dir": "data",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_file": "logs/actions.log",
    "log_format": "%(asctime)s %(levelname)s %(message)s",
}


class SettingsLoader:
    """Хранит единственный экземпляр конфигурации приложения."""

    _instance = None

    def __new__(cls):
        # __new__ выбран за простоту: повторный вызов возвращает тот же объект.
        if cls._instance is None:
            instance = super().__new__(cls)
            instance.reload()
            cls._instance = instance
        return cls._instance

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает настройку, не позволяя изменить внутренний кеш."""
        return deepcopy(self._settings.get(key, default))

    def reload(self) -> None:
        """Перечитывает конфигурацию и заменяет кеш после проверки."""
        settings = DEFAULT_SETTINGS.copy()

        try:
            with CONFIG_PATH.open("rb") as file:
                document = tomllib.load(file)
        except FileNotFoundError:
            document = {}

        section = document.get("tool", {}).get("valutatrade", {})
        if not isinstance(section, dict):
            raise TypeError("Секция tool.valutatrade должна быть таблицей.")

        settings.update(section)

        ttl = settings["rates_ttl_seconds"]
        if isinstance(ttl, bool) or not isinstance(ttl, int):
            raise TypeError("rates_ttl_seconds должен быть целым числом.")
        if ttl <= 0:
            raise ValueError("rates_ttl_seconds должен быть больше нуля.")

        for key in (
            "data_dir",
            "default_base_currency",
            "log_file",
            "log_format",
        ):
            value = settings[key]
            if not isinstance(value, str):
                raise TypeError(f"Настройка {key} должна быть строкой.")
            if not value.strip():
                raise ValueError(f"Настройка {key} не может быть пустой.")

        settings["default_base_currency"] = (
            settings["default_base_currency"].strip().upper()
        )

        for key in ("data_dir", "log_file"):
            path = Path(settings[key])
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            settings[key] = str(path.resolve())

        self._settings = settings
