import json
import os
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, RLock


class DatabaseManager:
    """Единый экземпляр для чтения и атомарной записи JSON."""

    _instance = None
    _instance_lock = Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._lock = RLock()
                cls._instance = instance
        return cls._instance

    def read(self, path: str | Path, default):
        """Читает JSON; для отсутствующего или пустого файла даёт копию default."""
        path = Path(path)

        with self._lock:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except FileNotFoundError:
                return deepcopy(default)

            if not text.strip():
                return deepcopy(default)

            try:
                return json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(f"Некорректный JSON в файле {path}.") from error

    def write(self, path: str | Path, data) -> None:
        """Сначала готовит JSON, затем атомарно заменяет один файл."""
        path = Path(path)
        text = json.dumps(
            data,
            ensure_ascii=False,
            indent=4,
            allow_nan=False,
        )

        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None

            try:
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    newline="\n",
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(text + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

                temporary.replace(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
