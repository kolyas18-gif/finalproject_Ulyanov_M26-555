import math
from datetime import UTC, datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.utils import load_json
from valutatrade_hub.infra.settings import SettingsLoader


def normalize_currency(currency_code: str) -> str:
    if not isinstance(currency_code, str):
        raise TypeError("Код валюты должен быть строкой.")
    if not currency_code.strip():
        raise ValueError("Код валюты не может быть пустым.")
    return currency_code.strip().upper()


def _record_time(record: dict) -> datetime:
    updated = datetime.fromisoformat(record["updated_at"])
    if updated.tzinfo is None:
        raise ValueError("Время курса должно содержать часовой пояс.")
    return updated.astimezone(UTC)


def _is_fresh(record: dict, now: datetime) -> bool:
    try:
        rate = record["rate"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            return False
        if not math.isfinite(rate) or rate <= 0:
            return False

        source = record.get("source")
        if not isinstance(source, str) or not source.strip():
            return False
        if source == "Stub":
            return False

        age = (now - _record_time(record)).total_seconds()
        ttl = SettingsLoader().get("rates_ttl_seconds")
        return 0 <= age < ttl
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def load_rates_cache() -> dict:
    """Читает новый кэш; старый формат требует обновления парсером."""

    cache = load_json("rates.json", {})
    if not isinstance(cache, dict):
        raise TypeError("В rates.json должен храниться JSON-объект.")

    pairs = cache.get("pairs", {})
    if not isinstance(pairs, dict):
        raise TypeError("Поле pairs должно быть словарём.")

    return {
        "pairs": pairs,
        "last_refresh": cache.get("last_refresh"),
    }


def _checked_rate(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(
            "Некорректный результат пересчёта курса. Выполните update-rates."
        )
    return value


def _read_pair(
    pairs: dict,
    source: str,
    target: str,
    now: datetime,
) -> dict | None:
    for key, inverse in (
        (f"{source}_{target}", False),
        (f"{target}_{source}", True),
    ):
        record = pairs.get(key)
        if record is None:
            continue

        if not isinstance(record, dict) or not _is_fresh(record, now):
            raise ValueError(
                f"Курс {key} устарел или некорректен. Выполните update-rates."
            )

        rate = float(record["rate"])
        if inverse:
            rate = 1.0 / rate

        return {
            "rate": _checked_rate(rate),
            "updated_at": record["updated_at"],
            "source": record["source"],
        }

    return None


def get_rate(from_currency: str, to_currency: str) -> dict:
    """Возвращает свежий курс из кэша, при необходимости через USD."""

    source = get_currency(normalize_currency(from_currency)).code
    target = get_currency(normalize_currency(to_currency)).code
    now = datetime.now(UTC)

    if source == target:
        return {
            "rate": 1.0,
            "updated_at": now.isoformat(),
            "source": "Identity",
        }

    cache = load_rates_cache()
    pairs = cache["pairs"]
    if not pairs:
        raise ValueError(
            "Локальный кэш курсов пуст или имеет старый формат. Выполните update-rates."
        )

    direct = _read_pair(pairs, source, target, now)
    if direct is not None:
        return direct

    if source != "USD" and target != "USD":
        source_usd = _read_pair(pairs, source, "USD", now)
        target_usd = _read_pair(pairs, target, "USD", now)

        if source_usd is not None and target_usd is not None:
            rate = _checked_rate(source_usd["rate"] / target_usd["rate"])
            oldest = min(
                _record_time(source_usd),
                _record_time(target_usd),
            )
            sources = sorted(
                {
                    source_usd["source"],
                    target_usd["source"],
                }
            )
            return {
                "rate": rate,
                "updated_at": oldest.isoformat(),
                "source": " / ".join(sources),
            }

    raise ValueError(
        f"Курс {source}→{target} не найден в кэше. Выполните update-rates."
    )
