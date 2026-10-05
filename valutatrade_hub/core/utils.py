import json
from pathlib import Path

DATA_DIR = Path("data")


def load_json(filename: str, default):
    """Читает JSON; для отсутствующего или пустого файла возвращает default."""
    path = DATA_DIR / filename
    if not path.exists():
        return default

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return default

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Некорректный JSON в файле {path}.") from error


def save_json(filename: str, data) -> None:
    """Записывает JSON через временный файл, затем заменяет основной."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    temporary = path.with_suffix(".json.tmp")

    text = json.dumps(
        data,
        ensure_ascii=False,
        indent=4,
        allow_nan=False,
    )
    temporary.write_text(text + "\n", encoding="utf-8")
    temporary.replace(path)
