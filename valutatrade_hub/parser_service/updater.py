import logging
from datetime import UTC, datetime

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import setup_parser_logging
from valutatrade_hub.parser_service.api_clients import BaseApiClient
from valutatrade_hub.parser_service.storage import RatesStorage


class RatesUpdater:
    """Обновляет курсы, сохраняя результаты доступных источников."""

    def __init__(
        self,
        clients: list[BaseApiClient],
        storage: RatesStorage,
        logger: logging.Logger | None = None,
    ):
        self.clients = list(clients)
        self.storage = storage
        self.logger = logger if logger is not None else setup_parser_logging()

    def run_update(self) -> dict:
        """Возвращает итог обновления; при полном отказе сообщает ошибку."""

        self.logger.info("Начато обновление курсов.")
        records = []
        errors = []
        successful_sources = []

        for client in self.clients:
            self.logger.info("Запрос курсов: %s.", client.SOURCE)

            try:
                rates = client.fetch_rates()
                if not rates:
                    raise ApiRequestError(
                        f"{client.SOURCE}: получен пустой список курсов."
                    )
            except ApiRequestError as error:
                errors.append(
                    {
                        "source": client.SOURCE,
                        "message": str(error),
                    }
                )
                self.logger.error(
                    "Не удалось получить курсы: %s.",
                    error,
                )
                continue

            timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

            for pair, rate in rates.items():
                source_code, target_code = pair.split("_")
                meta = client.last_meta.copy()

                if client.SOURCE == "CoinGecko":
                    meta["raw_id"] = client.config.CRYPTO_ID_MAP[source_code]

                records.append(
                    {
                        "from_currency": source_code,
                        "to_currency": target_code,
                        "rate": rate,
                        "timestamp": timestamp,
                        "source": client.SOURCE,
                        "meta": meta,
                    }
                )

            successful_sources.append(client.SOURCE)
            self.logger.info(
                "Получены курсы: %s, количество: %s.",
                client.SOURCE,
                len(rates),
            )

        if not records:
            self.logger.error("Обновление завершилось без данных. Файлы не изменены.")
            raise ApiRequestError(
                "не удалось получить курсы ни от одного источника. "
                "Подробности в logs/parser.log."
            )

        self.logger.info("Сохранение %s измерений.", len(records))

        try:
            updated = self.storage.save(records)
            cache = self.storage.load_rates()
        except (OSError, ValueError, TypeError):
            self.logger.exception("Ошибка сохранения курсов.")
            raise

        status = "partial" if errors else "ok"
        self.logger.info(
            "Обновление завершено. Статус: %s, обновлено пар: %s.",
            status,
            updated,
        )

        return {
            "status": status,
            "updated": updated,
            "received": len(records),
            "last_refresh": cache["last_refresh"],
            "sources": successful_sources,
            "errors": errors,
        }
