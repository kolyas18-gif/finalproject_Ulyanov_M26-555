import math
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError
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


def _fetch_stub_rate(source: str, target: str) -> float:
    """Получает курс из учебной заглушки и проверяет данные источника."""
    try:
        source_rate = EXCHANGE_RATES[source]
        target_rate = EXCHANGE_RATES[target]

        for value in (source_rate, target_rate):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("Источник вернул нечисловой курс.")
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Источник вернул некорректный курс.")

        rate = source_rate / target_rate
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Невозможно рассчитать курс.")

        if not math.isfinite(1.0 / rate):
            raise ValueError("Невозможно рассчитать обратный курс.")

        return rate
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise ApiRequestError(
            f"не удалось получить курс {source}→{target} из заглушки"
        ) from error


def get_rate(from_currency: str, to_currency: str) -> dict:
    """Проверяет валюты и возвращает свежий курс из кеша или заглушки."""
    source = get_currency(normalize_currency(from_currency)).code
    target = get_currency(normalize_currency(to_currency)).code
    now = datetime.now(UTC)

    cache = load_json("rates.json", {})
    if not isinstance(cache, dict):
        raise TypeError("В rates.json должен храниться JSON-объект.")

    key = f"{source}_{target}"
    record = cache.get(key)

    if isinstance(record, dict) and _is_fresh(record, now):
        return record.copy()

    rate = _fetch_stub_rate(source, target)
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
