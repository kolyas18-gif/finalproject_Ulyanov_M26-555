import math
from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


def validate_text(value: str, field: str) -> str:
    """Проверяет непустую строку и убирает пробелы по краям."""
    if not isinstance(value, str):
        raise TypeError(f"{field} должно быть строкой.")
    if not value.strip():
        raise ValueError(f"{field} не может быть пустым.")
    return value.strip()


def normalize_code(code: str) -> str:
    """Приводит код к верхнему регистру и проверяет его формат."""
    if not isinstance(code, str):
        raise TypeError("Код валюты должен быть строкой.")

    code = code.upper()
    if not 2 <= len(code) <= 5 or any(char.isspace() for char in code):
        raise ValueError("Код валюты должен содержать от 2 до 5 символов без пробелов.")
    return code


class Currency(ABC):
    """Определяет общие атрибуты и интерфейс всех валют."""

    def __init__(self, name: str, code: str):
        self.name = name
        self.code = code

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = validate_text(value, "Название валюты")

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        self._code = normalize_code(value)

    @abstractmethod
    def get_display_info(self) -> str:
        """Возвращает описание валюты для интерфейса и логов."""
        raise NotImplementedError


class FiatCurrency(Currency):
    """Представляет обычную валюту со страной или зоной эмиссии."""

    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = validate_text(
            issuing_country, "Название страны или зоны эмиссии"
        )

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Представляет криптовалюту с алгоритмом и капитализацией."""

    def __init__(
        self,
        name: str,
        code: str,
        algorithm: str,
        market_cap: float,
    ):
        super().__init__(name, code)
        self.algorithm = validate_text(algorithm, "Название алгоритма")

        if isinstance(market_cap, bool) or not isinstance(market_cap, (int, float)):
            raise TypeError("Капитализация должна быть числом.")

        market_cap = float(market_cap)
        if not math.isfinite(market_cap) or market_cap < 0:
            raise ValueError(
                "Капитализация должна быть конечным неотрицательным числом."
            )

        self.market_cap = market_cap

    def get_display_info(self) -> str:
        mantissa, exponent = f"{self.market_cap:.2e}".split("e")
        short_cap = f"{mantissa}e{int(exponent)}"
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {short_cap})"
        )


# Учебные значения капитализации, не текущие рыночные данные.
CURRENCY_REGISTRY = {
    "USD": {
        "type": FiatCurrency,
        "name": "US Dollar",
        "issuing_country": "United States",
    },
    "EUR": {
        "type": FiatCurrency,
        "name": "Euro",
        "issuing_country": "Eurozone",
    },
    "RUB": {
        "type": FiatCurrency,
        "name": "Russian Ruble",
        "issuing_country": "Russia",
    },
    "BTC": {
        "type": CryptoCurrency,
        "name": "Bitcoin",
        "algorithm": "SHA-256",
        "market_cap": 1.12e12,
    },
    "ETH": {
        "type": CryptoCurrency,
        "name": "Ethereum",
        "algorithm": "Proof of Stake",
        "market_cap": 3.6e11,
    },
}

CURRENCY_REGISTRY.update(
    {
        "GBP": {
            "type": FiatCurrency,
            "name": "British Pound",
            "issuing_country": "United Kingdom",
        },
        "SOL": {
            "type": CryptoCurrency,
            "name": "Solana",
            "algorithm": "Proof of Stake",
            "market_cap": 0.0,
        },
    }
)


def get_currency(code: str) -> Currency:
    """Создаёт валюту по коду или сообщает, что она не найдена."""
    code = normalize_code(code)
    if code not in CURRENCY_REGISTRY:
        raise CurrencyNotFoundError(code)

    parameters = CURRENCY_REGISTRY[code].copy()
    currency_class = parameters.pop("type")
    return currency_class(code=code, **parameters)
