import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def _data_path(filename: str) -> Path:
    return Path(SettingsLoader().get("data_dir")) / filename


@dataclass
class ParserConfig:
    """Хранит настройки парсера и читает API-ключи из окружения."""

    EXCHANGERATE_API_KEY: str = field(
        default_factory=lambda: os.getenv("EXCHANGERATE_API_KEY", "").strip(),
        repr=False,
    )
    COINGECKO_API_KEY: str = field(
        default_factory=lambda: os.getenv("COINGECKO_API_KEY", "").strip(),
        repr=False,
    )

    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")

    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    RATES_FILE_PATH: Path = field(default_factory=lambda: _data_path("rates.json"))
    HISTORY_FILE_PATH: Path = field(
        default_factory=lambda: _data_path("exchange_rates.json")
    )

    REQUEST_TIMEOUT: int = 10
