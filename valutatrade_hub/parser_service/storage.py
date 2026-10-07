import json
import math
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from valutatrade_hub.parser_service.config import ParserConfig


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("Время должно быть строкой ISO.")

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Время должно содержать часовой пояс.")

    return parsed.astimezone(UTC)


def _normalize_timestamp(value: str) -> str:
    return _parse_timestamp(value).isoformat().replace("+00:00", "Z")


def _validate_code(code: str) -> None:
    if not isinstance(code, str):
        raise TypeError("Код валюты должен быть строкой.")
    if (
        not 2 <= len(code) <= 5
        or code != code.upper()
        or "_" in code
        or any(char.isspace() for char in code)
    ):
        raise ValueError(f"Некорректный код валюты: {code!r}.")


class RatesStorage:
    """Сохраняет историю измерений и последние курсы валют."""

    def __init__(self, config: ParserConfig | None = None):
        self.config = config if config is not None else ParserConfig()
        self.rates_path = Path(self.config.RATES_FILE_PATH)
        self.history_path = Path(self.config.HISTORY_FILE_PATH)

        if self.rates_path.resolve() == self.history_path.resolve():
            raise ValueError("Кэш и история должны храниться в разных файлах.")

    @staticmethod
    def _read_json(path: Path, default):
        try:
            with path.open(encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError:
            raise ValueError(f"Файл {path.name} содержит некорректный JSON.") from None

    @staticmethod
    def _write_json(path: Path, data) -> None:
        """Заменяет файл только после полной записи временного файла."""

        text = json.dumps(data, ensure_ascii=False, indent=4, allow_nan=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary = Path(file.name)
                file.write(text + "\n")

            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load_rates(self) -> dict:
        data = self._read_json(
            self.rates_path,
            {"pairs": {}, "last_refresh": None},
        )
        if not isinstance(data, dict):
            raise TypeError("В rates.json должен храниться JSON-объект.")

        if "pairs" not in data:
            # Поддерживаем прежний плоский формат кэша.
            data = {
                "pairs": {
                    key: value
                    for key, value in data.items()
                    if "_" in key and isinstance(value, dict)
                },
                "last_refresh": data.get("last_refresh"),
            }

        if not isinstance(data["pairs"], dict):
            raise TypeError("Поле pairs должно быть словарём.")

        for pair, record in data["pairs"].items():
            parts = pair.split("_")
            if len(parts) != 2 or not isinstance(record, dict):
                raise ValueError(f"Некорректная запись кэша: {pair}.")

            self._prepare_record(
                {
                    "from_currency": parts[0],
                    "to_currency": parts[1],
                    "rate": record.get("rate"),
                    "timestamp": record.get("updated_at"),
                    "source": record.get("source"),
                }
            )

        return data

    def load_history(self) -> list[dict]:
        data = self._read_json(self.history_path, [])
        if not isinstance(data, list):
            raise TypeError("В exchange_rates.json должен храниться список.")

        return [self._prepare_record(record) for record in data]

    @staticmethod
    def _prepare_record(record: dict) -> dict:
        if not isinstance(record, dict):
            raise TypeError("Измерение должно быть словарём.")

        source_code = record.get("from_currency")
        target_code = record.get("to_currency")
        _validate_code(source_code)
        _validate_code(target_code)

        rate = record.get("rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            raise TypeError("Курс должен быть числом.")

        rate = float(rate)
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Курс должен быть конечным и положительным.")

        timestamp = _normalize_timestamp(record.get("timestamp"))
        source = record.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Источник курса не указан.")

        meta = record.get("meta", {})
        if not isinstance(meta, dict):
            raise TypeError("Метаданные должны быть словарём.")

        record_id = f"{source_code}_{target_code}_{timestamp}"
        if "id" in record and record["id"] != record_id:
            raise ValueError("ID измерения не соответствует паре и времени.")

        return {
            "id": record_id,
            "from_currency": source_code,
            "to_currency": target_code,
            "rate": rate,
            "timestamp": timestamp,
            "source": source.strip(),
            "meta": meta.copy(),
        }

    def save(self, records: list[dict]) -> int:
        """Добавляет измерения и возвращает число обновлённых пар."""

        prepared = [self._prepare_record(record) for record in records]
        if not prepared:
            return 0

        history = self.load_history()
        cache = self.load_rates()
        known_ids = {record["id"] for record in history}

        for record in prepared:
            if record["id"] not in known_ids:
                history.append(record)
                known_ids.add(record["id"])

        updated_pairs = set()

        # История позволяет восстановить кэш после сбоя его записи.
        for record in history:
            pair = f"{record['from_currency']}_{record['to_currency']}"
            current = cache["pairs"].get(pair)

            if current is not None:
                new_time = _parse_timestamp(record["timestamp"])
                old_time = _parse_timestamp(current["updated_at"])
                if new_time <= old_time:
                    continue

            cache["pairs"][pair] = {
                "rate": record["rate"],
                "updated_at": record["timestamp"],
                "source": record["source"],
            }
            updated_pairs.add(pair)

        cache["last_refresh"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Проверяем сериализацию обоих объектов до начала записи.
        json.dumps(history, allow_nan=False)
        json.dumps(cache, allow_nan=False)

        self._write_json(self.history_path, history)
        self._write_json(self.rates_path, cache)
        return len(updated_pairs)
