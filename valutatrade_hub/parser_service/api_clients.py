from __future__ import annotations

import math
from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    """Единый интерфейс клиентов внешних API."""

    SOURCE = "External API"

    def __init__(self, config: ParserConfig | None = None) -> None:
        self.config = config or ParserConfig()
        self.last_meta: dict[str, Any] = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Получает курсы и возвращает их в едином формате."""

    def _request(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Выполняет GET-запрос и проверяет ответ API."""
        started = perf_counter()
        request_kwargs: dict[str, Any] = {
            "timeout": self.config.REQUEST_TIMEOUT,
        }

        if params is not None:
            request_kwargs["params"] = params

        if headers:
            request_kwargs["headers"] = headers

        try:
            response = requests.get(url, **request_kwargs)
        except requests.exceptions.Timeout as error:
            raise ApiRequestError(
                f"{self.SOURCE}: превышено время ожидания."
            ) from error
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(f"{self.SOURCE}: ошибка сети.") from error

        status_code = getattr(response, "status_code", None)
        response_headers = getattr(response, "headers", {}) or {}

        self.last_meta = {
            "request_ms": round((perf_counter() - started) * 1000),
            "status_code": status_code,
        }

        etag = response_headers.get("ETag") or response_headers.get("etag")
        if etag:
            self.last_meta["etag"] = etag

        if status_code != 200:
            if status_code == 429:
                reason = (
                    f"HTTP {status_code}, превышен лимит запросов; повторите позже."
                )
            elif status_code in (401, 403):
                reason = f"HTTP {status_code}, доступ запрещён или API-ключ неверен."
            else:
                reason = f"HTTP {status_code}."

            raise ApiRequestError(f"{self.SOURCE}: {reason}")

        try:
            data = response.json()
        except (AttributeError, TypeError, ValueError) as error:
            raise ApiRequestError(
                f"{self.SOURCE}: API вернул некорректный JSON."
            ) from error

        if not isinstance(data, dict):
            raise ApiRequestError(f"{self.SOURCE}: API вернул JSON-объект.")

        return data

    def _validate_rate(self, value: Any, pair: str) -> float:
        """Проверяет, что курс является конечным положительным числом."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ApiRequestError(
                f"{self.SOURCE}: курс {pair} должен быть конечным и положительным."
            )

        try:
            rate = float(value)
        except (OverflowError, TypeError, ValueError) as error:
            raise ApiRequestError(
                f"{self.SOURCE}: курс {pair} должен быть конечным и положительным."
            ) from error

        if not math.isfinite(rate) or rate <= 0:
            raise ApiRequestError(
                f"{self.SOURCE}: курс {pair} должен быть конечным и положительным."
            )

        return rate


class CoinGeckoClient(BaseApiClient):
    """Получает курсы криптовалют через публичный CoinGecko API."""

    SOURCE = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Получает курсы криптовалют к базовой валюте."""
        base = self.config.BASE_CURRENCY.strip().upper()
        codes = tuple(
            str(code).strip().upper() for code in self.config.CRYPTO_CURRENCIES
        )

        ids: list[str] = []
        for code in codes:
            raw_id = self.config.CRYPTO_ID_MAP.get(code)

            if not isinstance(raw_id, str) or not raw_id.strip():
                raise ApiRequestError(
                    f"{self.SOURCE}: не найден CoinGecko ID для {code}."
                )

            ids.append(raw_id.strip())

        data = self._request(
            self.config.COINGECKO_URL,
            params={
                "ids": ",".join(ids),
                "vs_currencies": base.lower(),
            },
        )

        result: dict[str, float] = {}
        rate_key = base.lower()

        for code, raw_id in zip(codes, ids, strict=True):
            pair = f"{code}_{base}"
            record = data.get(raw_id)

            if not isinstance(record, dict):
                raise ApiRequestError(
                    f"{self.SOURCE}: в ответе отсутствует курс {pair}."
                )

            if rate_key not in record:
                raise ApiRequestError(
                    f"{self.SOURCE}: в ответе отсутствует курс {pair}."
                )

            result[pair] = self._validate_rate(record[rate_key], pair)

        return result


class ExchangeRateApiClient(BaseApiClient):
    """Получает курсы фиатных валют через ExchangeRate-API."""

    SOURCE = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Получает курсы фиатных валют к базовой валюте."""
        api_key = self.config.EXCHANGERATE_API_KEY.strip()

        if not api_key:
            raise ApiRequestError(f"{self.SOURCE}: API-ключ не задан.")

        base = self.config.BASE_CURRENCY.strip().upper()
        url = (
            f"{self.config.EXCHANGERATE_API_URL.rstrip('/')}/"
            f"{api_key}/latest/{base}"
        )

        data = self._request(url)

        if data.get("result") != "success":
            error_type = data.get("error-type", "неизвестная ошибка")
            raise ApiRequestError(f"{self.SOURCE}: {error_type}.")

        response_base = data.get("base_code")
        if response_base != base:
            raise ApiRequestError(
                f"{self.SOURCE}: API вернул базу {response_base!r} вместо {base!r}."
            )

        conversion_rates = data.get("conversion_rates")
        if not isinstance(conversion_rates, dict):
            raise ApiRequestError(
                f"{self.SOURCE}: отсутствует словарь conversion_rates."
            )

        result: dict[str, float] = {}

        for raw_code in self.config.FIAT_CURRENCIES:
            code = str(raw_code).strip().upper()

            if code == base:
                continue

            pair = f"{code}_{base}"
            direct_rate = conversion_rates.get(code)

            if direct_rate is None:
                raise ApiRequestError(
                    f"{self.SOURCE}: в ответе отсутствует курс {pair}."
                )

            usd_to_currency = self._validate_rate(direct_rate, pair)

            try:
                currency_to_base = 1.0 / usd_to_currency
            except (OverflowError, ZeroDivisionError) as error:
                raise ApiRequestError(
                    f"{self.SOURCE}: курс {pair} должен быть конечным и положительным."
                ) from error

            result[pair] = self._validate_rate(
                currency_to_base,
                pair,
            )

        return result
