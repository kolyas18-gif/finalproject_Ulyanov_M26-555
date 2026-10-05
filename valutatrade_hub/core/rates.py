import math
from datetime import UTC, datetime

from valutatrade_hub.core.utils import load_json, save_json

CACHE_TTL = 300

EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 1.1,
    "RUB": 0.01,
    "BTC": 60000.0,
    "ETH": 3000.0,
}


def normalize_currency(currency_code: str) -> str:
    if not isinstance(currency_code, str):
        raise TypeError("Код валюты должен быть строкой.")
    if not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым.")
    return currency_code.strip().upper()


def _is_fresh(record: dict, now: datetime) -> bool:
    """Проверяет корректность курса и срок действия записи."""
    try:
        rate = record["rate"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            return False
        if not math.isfinite(rate) or rate <= 0:
            return False

        updated_at = datetime.fromisoformat(record["updated_at"])
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)

        age = (now - updated_at).total_seconds()
        return 0 <= age < CACHE_TTL
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def get_rate(from_currency: str, to_currency: str) -> dict:
    """Возвращает курс и время; устаревший кеш обновляет из заглушки."""
    source = normalize_currency(from_currency)
    target = normalize_currency(to_currency)
    now = datetime.now(UTC)

    cache = load_json("rates.json", {})
    if not isinstance(cache, dict):
        raise TypeError("В rates.json должен храниться JSON-объект.")

    key = f"{source}_{target}"
    record = cache.get(key)

    if isinstance(record, dict) and _is_fresh(record, now):
        return record.copy()

    if source not in EXCHANGE_RATES or target not in EXCHANGE_RATES:
        raise ValueError(f"Курс {source}→{target} недоступен. Повторите попытку позже.")

    rate = EXCHANGE_RATES[source] / EXCHANGE_RATES[target]
    timestamp = now.isoformat()

    record = {
        "rate": rate,
        "updated_at": timestamp,
        "source": "Stub",
    }
    cache[key] = record
    cache[f"{target}_{source}"] = {
        "rate": 1.0 / rate,
        "updated_at": timestamp,
        "source": "Stub",
    }
    cache["source"] = "Stub"
    cache["last_refresh"] = timestamp
    save_json("rates.json", cache)

    return record.copy()
