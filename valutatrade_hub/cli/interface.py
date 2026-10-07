import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import (
    CURRENCY_REGISTRY,
    CryptoCurrency,
    get_currency,
)
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.rates import (
    get_rate,
    load_rates_cache,
    normalize_currency,
)
from valutatrade_hub.core.usecases import TradingService
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater

HELP_TEXT = """
Команды:
  register --username alice --password 1234
  login --username alice --password 1234
  show-portfolio [--base USD]
  buy --currency BTC --amount 0.01
  sell --currency BTC --amount 0.01
  get-rate --from BTC --to USD
  update-rates [--source coingecko|exchangerate]
  show-rates [--currency BTC] [--top 2] [--base USD]
  help
  exit
"""


def build_parser() -> argparse.ArgumentParser:
    """Описывает команды и их аргументы."""
    parser = argparse.ArgumentParser(prog="valutatrade")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("register", "login"):
        command = commands.add_parser(name)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)

    portfolio = commands.add_parser("show-portfolio")
    portfolio.add_argument("--base", default=None)

    for name in ("buy", "sell"):
        command = commands.add_parser(name)
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", required=True, type=float)

    rate = commands.add_parser("get-rate")
    rate.add_argument("--from", dest="from_currency", required=True)
    rate.add_argument("--to", dest="to_currency", required=True)

    update = commands.add_parser("update-rates")
    update.add_argument(
        "--source",
        choices=("coingecko", "exchangerate"),
        default=None,
    )

    rates = commands.add_parser("show-rates")
    rates.add_argument("--currency", default=None)
    rates.add_argument("--top", type=int, default=None)
    rates.add_argument("--base", default="USD")

    commands.add_parser("help")
    commands.add_parser("exit")
    return parser


def print_portfolio(result: dict) -> None:
    """Выводит кошельки и общую стоимость портфеля."""
    print(f"Портфель пользователя '{result['username']}'")

    if not result["wallets"]:
        print("Ваш портфель пуст.")
        return

    base = result["base_currency"]
    table = PrettyTable()
    table.field_names = ["Валюта", "Баланс", f"Стоимость в {base}"]

    for wallet in result["wallets"]:
        table.add_row(
            [
                wallet["currency_code"],
                f"{wallet['balance']:.4f}",
                f"{wallet['value']:.2f}",
            ]
        )

    print(table)
    print(f"Итого: {result['total']:.2f} {base}")


def print_trade(result: dict, operation: str) -> None:
    """Показывает результат сделки и изменение балансов."""
    code = result["currency_code"]
    print(f"{operation}: {result['amount']:.4f} {code}")
    print(f"Курс: {result['rate']:.4f} USD за 1 {code}")
    print(f"Сумма: {result['total_usd']:.2f} USD")
    print(
        f"Баланс {code}: {result['balance_before']:.4f} → {result['balance_after']:.4f}"
    )
    print(f"Баланс USD: {result['usd_before']:.2f} → {result['usd_after']:.2f}")


def update_rates(source: str | None = None) -> None:
    """Обновляет курсы и сообщает о полном или частичном успехе."""
    config = ParserConfig()
    client_types = {
        "coingecko": CoinGeckoClient,
        "exchangerate": ExchangeRateApiClient,
    }
    selected = (source,) if source else tuple(client_types)
    clients = [client_types[name](config) for name in selected]

    print("Начато обновление курсов...")
    updater = RatesUpdater(clients, RatesStorage(config))
    result = updater.run_update()

    if result["status"] == "partial":
        print("Обновление завершено частично.")
        for error in result["errors"]:
            print(error["message"])
        print("Подробности: logs/parser.log")
    else:
        print("Обновление выполнено успешно.")

    print(f"Обновлено пар: {result['updated']}")
    print(f"Последнее обновление: {result['last_refresh']}")


def show_rates(
    currency: str | None = None,
    top: int | None = None,
    base: str = "USD",
) -> None:
    """Показывает свежие курсы из кэша с фильтрацией и пересчётом."""
    if top is not None and top <= 0:
        raise ValueError("--top должен быть положительным целым числом.")

    base_code = get_currency(normalize_currency(base)).code
    currency_code = (
        get_currency(normalize_currency(currency)).code
        if currency is not None
        else None
    )

    cache = load_rates_cache()
    pairs = cache["pairs"]
    if not pairs:
        print("Локальный кэш курсов пуст. Выполните update-rates.")
        return

    available = set()
    for pair in pairs:
        parts = pair.split("_")
        if len(parts) != 2:
            raise ValueError(f"Некорректная валютная пара в кэше: {pair}")
        available.update(parts)

    if currency_code is not None:
        if currency_code not in available:
            print(f"Курс для '{currency_code}' не найден в кэше.")
            print("Выполните update-rates.")
            return
        codes = [currency_code]
    else:
        codes = sorted(available - {base_code})

    if top is not None:
        codes = [
            code for code in codes if isinstance(get_currency(code), CryptoCurrency)
        ]

    rows = []
    for code in codes:
        try:
            record = get_rate(code, base_code)
        except ValueError as error:
            print(f"Пропущен {code}: {error}")
            continue

        rows.append(
            {
                "code": code,
                "rate": record["rate"],
                "updated_at": record["updated_at"],
                "source": record["source"],
            }
        )

    if top is not None:
        rows.sort(key=lambda row: (-row["rate"], row["code"]))
        rows = rows[:top]

    if not rows:
        print("Нет актуальных курсов по выбранным условиям.")
        print("Для обновления выполните update-rates.")
        return

    table = PrettyTable()
    table.field_names = [
        "Пара",
        f"Цена в {base_code}",
        "Обновлён",
        "Источник",
    ]
    for row in rows:
        table.add_row(
            [
                f"{row['code']}_{base_code}",
                f"{row['rate']:.8f}",
                row["updated_at"],
                row["source"],
            ]
        )

    print(table)
    print(f"Последнее обновление кэша: {cache['last_refresh']}")


def execute_command(service: TradingService, args: argparse.Namespace) -> None:
    """Передаёт команду сервису и выводит результат."""
    match args.command:
        case "register":
            user = service.register(args.username, args.password)
            print(
                f"Пользователь '{user.username}' зарегистрирован "
                f"(id={user.user_id}). Выполните login."
            )

        case "login":
            user = service.login(args.username, args.password)
            print(f"Вы вошли как '{user.username}'.")

        case "show-portfolio":
            print_portfolio(service.show_portfolio(args.base))

        case "buy":
            result = service.buy(args.currency, args.amount)
            print_trade(result, "Покупка выполнена")

        case "sell":
            result = service.sell(args.currency, args.amount)
            print_trade(result, "Продажа выполнена")

        case "get-rate":
            result = service.get_rate(args.from_currency, args.to_currency)
            source = args.from_currency.strip().upper()
            target = args.to_currency.strip().upper()
            print(f"Курс {source} → {target}: {result['rate']:.8f}")
            print(f"Обратный курс: {1.0 / result['rate']:.8f}")
            print(f"Обновлён: {result['updated_at']}")

        case "update-rates":
            update_rates(args.source)

        case "show-rates":
            show_rates(args.currency, args.top, args.base)

        case "help":
            print(HELP_TEXT)


def main() -> None:
    """Запускает цикл команд с общей сессией пользователя."""
    service = TradingService()
    parser = build_parser()

    print("Добро пожаловать в ValutaTrade Hub!")
    print(HELP_TEXT)

    while True:
        try:
            line = input("valutatrade> ")
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break

        try:
            tokens = shlex.split(line)
            if not tokens:
                continue

            try:
                args = parser.parse_args(tokens)
            except SystemExit:
                continue

            if args.command == "exit":
                print("До свидания!")
                break

            execute_command(service, args)
        except InsufficientFundsError as error:
            print(error)
        except CurrencyNotFoundError as error:
            print(error)
            codes = ", ".join(sorted(CURRENCY_REGISTRY))
            print(f"Поддерживаемые валюты: {codes}")
        except ApiRequestError as error:
            print(error)
            print("Повторите попытку позже или проверьте подключение к сети.")
        except (ValueError, TypeError, OSError) as error:
            print(f"Ошибка: {error}")
