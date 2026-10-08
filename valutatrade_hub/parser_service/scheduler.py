import argparse
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


class RatesScheduler:
    """Последовательно обновляет курсы с паузой между попытками."""

    def __init__(self, updater: RatesUpdater, interval: int):
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise TypeError("Интервал должен быть целым числом.")
        if interval <= 0:
            raise ValueError("Интервал должен быть положительным.")

        self.updater = updater
        self.interval = interval
        self.logger = updater.logger

    def run(self) -> None:
        """Работает до остановки пользователем через Ctrl+C."""
        self.logger.info(
            "Планировщик запущен. Интервал: %s секунд.",
            self.interval,
        )
        print(
            f"Планировщик запущен. Пауза: {self.interval} секунд. "
            "Для остановки нажмите Ctrl+C.",
            flush=True,
        )

        try:
            while True:
                try:
                    result = self.updater.run_update()
                except ApiRequestError as error:
                    self.logger.warning(
                        "Ошибка API. Следующая попытка через %s секунд.",
                        self.interval,
                    )
                    print(
                        f"{error}\nПовтор через {self.interval} секунд.",
                        flush=True,
                    )
                else:
                    status = "успешно" if result["status"] == "ok" else "частично"
                    print(
                        f"Обновление завершено {status}. "
                        f"Обновлено пар: {result['updated']}. "
                        f"Время: {result['last_refresh']}",
                        flush=True,
                    )
                    if result["errors"]:
                        print(
                            "Ошибки источников: см. logs/parser.log.",
                            flush=True,
                        )

                time.sleep(self.interval)
        except KeyboardInterrupt:
            self.logger.info("Планировщик остановлен пользователем.")
            print("\nПланировщик остановлен.", flush=True)


def main() -> None:
    """Создаёт API-клиентов и запускает планировщик."""
    config = ParserConfig()

    parser = argparse.ArgumentParser(
        description="Периодическое обновление курсов валют."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=config.UPDATE_INTERVAL_SECONDS,
        help="Пауза между обновлениями в секундах.",
    )
    parser.add_argument(
        "--source",
        choices=("coingecko", "exchangerate"),
        default=None,
        help="Обновлять только указанный источник.",
    )
    args = parser.parse_args()

    if args.interval <= 0:
        parser.error("--interval должен быть положительным числом.")

    clients = []
    if args.source in (None, "coingecko"):
        clients.append(CoinGeckoClient(config))
    if args.source in (None, "exchangerate"):
        clients.append(ExchangeRateApiClient(config))

    updater = RatesUpdater(
        clients=clients,
        storage=RatesStorage(config),
    )
    scheduler = RatesScheduler(updater, args.interval)

    try:
        scheduler.run()
    except (OSError, ValueError, TypeError) as error:
        print(f"Планировщик остановлен из-за ошибки: {error}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
