from pathlib import Path

from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

DATA_DIR = Path(SettingsLoader().get("data_dir"))


def load_json(filename: str, default):
    """Читает JSON через общий менеджер хранилища."""
    return DatabaseManager().read(DATA_DIR / filename, default)


def save_json(filename: str, data) -> None:
    """Атомарно сохраняет JSON через общий менеджер хранилища."""
    DatabaseManager().write(DATA_DIR / filename, data)
