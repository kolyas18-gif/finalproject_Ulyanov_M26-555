import math
from datetime import UTC, datetime
from secrets import token_hex

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.rates import get_rate, normalize_currency
from valutatrade_hub.core.utils import load_json, save_json
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_logging


class TradingService:
    """Выполняет операции приложения и хранит текущую сессию."""

    def __init__(self):
        self.current_user: User | None = None
        self.settings = SettingsLoader()
        setup_logging()

    @staticmethod
    def _validate_username(username: str) -> str:
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Имя пользователя не может быть пустым.")
        return username.strip()

    @staticmethod
    def _user_from_record(record: dict) -> User:
        return User(
            user_id=record["user_id"],
            username=record["username"],
            hashed_password=record["hashed_password"],
            salt=record["salt"],
            registration_date=datetime.fromisoformat(record["registration_date"]),
        )

    def register(self, username: str, password: str) -> User:
        """Сохраняет нового пользователя и создаёт пустой портфель."""
        username = self._validate_username(username)
        users = load_json("users.json", [])
        portfolios = load_json("portfolios.json", [])

        if any(record["username"] == username for record in users):
            raise ValueError(f"Имя пользователя '{username}' уже занято.")

        user_id = (
            max(
                (record["user_id"] for record in users),
                default=0,
            )
            + 1
        )

        user = User(
            user_id=user_id,
            username=username,
            hashed_password="",
            salt=token_hex(16),
            registration_date=datetime.now(UTC),
        )
        user.change_password(password)

        record = {
            "user_id": user.user_id,
            "username": user.username,
            "hashed_password": user.hashed_password,
            "salt": user.salt,
            "registration_date": user.registration_date.isoformat(),
        }
        portfolio = {
            "user_id": user.user_id,
            "wallets": {},
        }

        save_json("users.json", users + [record])
        try:
            save_json("portfolios.json", portfolios + [portfolio])
        except OSError:
            save_json("users.json", users)
            raise

        return user

    def login(self, username: str, password: str) -> User:
        """Проверяет пароль и сохраняет пользователя в текущей сессии."""
        username = self._validate_username(username)
        users = load_json("users.json", [])

        record = next(
            (item for item in users if item["username"] == username),
            None,
        )
        if record is None:
            raise ValueError(f"Пользователь '{username}' не найден.")

        user = self._user_from_record(record)
        if not user.verify_password(password):
            raise ValueError("Неверный пароль.")

        self.current_user = user
        return user

    def require_login(self) -> User:
        """Возвращает текущего пользователя или требует выполнить вход."""
        if self.current_user is None:
            raise ValueError("Сначала выполните login.")
        return self.current_user

    def get_portfolio(self) -> Portfolio:
        """Восстанавливает портфель текущего пользователя из JSON."""
        user = self.require_login()
        portfolios = load_json("portfolios.json", [])

        record = next(
            (item for item in portfolios if item["user_id"] == user.user_id),
            None,
        )
        if record is None:
            raise ValueError("Портфель пользователя не найден.")

        wallets = {
            code: Wallet(code, data["balance"])
            for code, data in record["wallets"].items()
        }
        return Portfolio(
            user_id=user.user_id,
            user=user,
            wallets=wallets,
        )

    def _save_portfolio(self, portfolio: Portfolio) -> None:
        """Сохраняет кошельки, оставляя портфели других пользователей."""
        user = self.require_login()
        if portfolio.user_id != user.user_id:
            raise ValueError("Нельзя изменить чужой портфель.")

        portfolios = load_json("portfolios.json", [])
        for record in portfolios:
            if record["user_id"] == user.user_id:
                record["wallets"] = {
                    code: {"balance": wallet.balance}
                    for code, wallet in portfolio.wallets.items()
                }
                save_json("portfolios.json", portfolios)
                return

        raise ValueError("Портфель пользователя не найден.")

    def get_rate(self, from_currency: str, to_currency: str) -> dict:
        return get_rate(from_currency, to_currency)

    def show_portfolio(self, base_currency: str | None = None) -> dict:
        """Готовит балансы и оценку портфеля для вывода в CLI."""
        portfolio = self.get_portfolio()

        if base_currency is None:
            base_currency = self.settings.get("default_base_currency")

        base = normalize_currency(base_currency)

        try:
            self.get_rate(base, "USD")
        except ValueError as error:
            raise ValueError(f"Неизвестная базовая валюта '{base}'.") from error

        rows = []
        total = 0.0

        for code, wallet in portfolio.wallets.items():
            rate = 1.0 if code == base else self.get_rate(code, base)["rate"]
            value = wallet.balance * rate
            rows.append(
                {
                    "currency_code": code,
                    "balance": wallet.balance,
                    "value": value,
                }
            )
            total += value

        return {
            "username": portfolio.user.username,
            "base_currency": base,
            "wallets": rows,
            "total": total,
        }

    @staticmethod
    def _validate_amount(amount: float) -> float:
        """Проверяет, что сумма является положительным конечным числом."""
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Количество должно быть числом.")

        amount = float(amount)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Количество должно быть положительным числом.")

        return amount

    @log_action("BUY", verbose=True)
    def buy(self, currency_code: str, amount: float) -> dict:
        """Покупает валюту за USD и сохраняет оба баланса."""
        portfolio = self.get_portfolio()
        code = get_currency(normalize_currency(currency_code)).code
        amount = self._validate_amount(amount)

        if code == "USD":
            raise ValueError("Нельзя покупать USD за USD.")

        rate = self.get_rate(code, "USD")["rate"]
        cost = amount * rate
        if not math.isfinite(cost) or cost <= 0:
            raise ValueError("Некорректная стоимость покупки.")

        if "USD" not in portfolio.wallets:
            raise InsufficientFundsError(
                available=0.0,
                required=cost,
                code="USD",
            )

        usd_wallet = portfolio.get_wallet("USD")
        if usd_wallet.balance < cost:
            raise InsufficientFundsError(
                available=usd_wallet.balance,
                required=cost,
                code="USD",
            )

        if code not in portfolio.wallets:
            portfolio.add_currency(code)

        wallet = portfolio.get_wallet(code)
        balance_before = wallet.balance
        usd_before = usd_wallet.balance

        wallet.deposit(amount)
        usd_wallet.withdraw(cost)
        self._save_portfolio(portfolio)

        return {
            "currency_code": code,
            "amount": amount,
            "rate": rate,
            "total_usd": cost,
            "balance_before": balance_before,
            "balance_after": wallet.balance,
            "usd_before": usd_before,
            "usd_after": usd_wallet.balance,
        }

    @log_action("SELL", verbose=True)
    def sell(self, currency_code: str, amount: float) -> dict:
        """Продаёт валюту и зачисляет выручку на USD-кошелёк."""
        portfolio = self.get_portfolio()
        code = get_currency(normalize_currency(currency_code)).code
        amount = self._validate_amount(amount)

        if code == "USD":
            raise ValueError("Нельзя продавать USD за USD.")

        if code not in portfolio.wallets:
            raise InsufficientFundsError(
                available=0.0,
                required=amount,
                code=code,
            )

        wallet = portfolio.get_wallet(code)
        if wallet.balance < amount:
            raise InsufficientFundsError(
                available=wallet.balance,
                required=amount,
                code=code,
            )

        rate = self.get_rate(code, "USD")["rate"]
        proceeds = amount * rate
        if not math.isfinite(proceeds) or proceeds <= 0:
            raise ValueError("Некорректная стоимость продажи.")

        if "USD" not in portfolio.wallets:
            portfolio.add_currency("USD")

        usd_wallet = portfolio.get_wallet("USD")
        balance_before = wallet.balance
        usd_before = usd_wallet.balance

        usd_wallet.deposit(proceeds)
        wallet.withdraw(amount)
        self._save_portfolio(portfolio)

        return {
            "currency_code": code,
            "amount": amount,
            "rate": rate,
            "total_usd": proceeds,
            "balance_before": balance_before,
            "balance_after": wallet.balance,
            "usd_before": usd_before,
            "usd_after": usd_wallet.balance,
        }
