import argparse
import shlex

from prettytable import PrettyTable

from valutatrade_hub.core.usecases import TradingService

HELP_TEXT = """
Команды:
  register --username alice --password 1234
  login --username alice --password 1234
  show-portfolio [--base USD]
  buy --currency BTC --amount 0.01
  sell --currency BTC --amount 0.01
  get-rate --from BTC --to USD
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
    portfolio.add_argument("--base", default="USD")

    for name in ("buy", "sell"):
        command = commands.add_parser(name)
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", required=True, type=float)

    rate = commands.add_parser("get-rate")
    rate.add_argument("--from", dest="from_currency", required=True)
    rate.add_argument("--to", dest="to_currency", required=True)

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
        except (ValueError, TypeError, OSError) as error:
            print(f"Ошибка: {error}")
