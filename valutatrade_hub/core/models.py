import hashlib
import hmac
import math
from datetime import datetime


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым.")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    def get_user_info(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "registration_date": self.registration_date.isoformat(),
        }

    def _hash_password(self, password: str) -> str:
        salted_password = (password + self.salt).encode("utf-8")
        return hashlib.sha256(salted_password).hexdigest()

    def change_password(self, new_password: str) -> None:
        if not isinstance(new_password, str) or len(new_password) < 4:
            raise ValueError("Пароль должен содержать минимум 4 символа.")
        self._hashed_password = self._hash_password(new_password)

    def verify_password(self, password: str) -> bool:
        if not isinstance(password, str):
            return False
        return hmac.compare_digest(
            self._hashed_password,
            self._hash_password(password),
        )


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0):
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым.")

        self.currency_code = currency_code.strip().upper()
        self.balance = balance

    @staticmethod
    def _validate_number(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Значение должно быть числом.")

        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Значение должно быть конечным числом.")

        return value

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        value = self._validate_number(value)
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным.")

        self._balance = value

    def deposit(self, amount: float) -> None:
        amount = self._validate_number(amount)
        if amount <= 0:
            raise ValueError("Сумма пополнения должна быть положительной.")

        self.balance = self.balance + amount

    def withdraw(self, amount: float) -> None:
        amount = self._validate_number(amount)
        if amount <= 0:
            raise ValueError("Сумма снятия должна быть положительной.")
        if amount > self.balance:
            raise ValueError("Недостаточно средств.")

        self.balance = self.balance - amount

    def get_balance_info(self) -> dict:
        return {
            "currency_code": self.currency_code,
            "balance": self.balance,
        }

    
class Portfolio:
    """Хранит кошельки пользователя и рассчитывает их общую стоимость."""

    def __init__(
        self,
        user_id: int,
        user: User,
        wallets: dict[str, Wallet] | None = None,
    ):
        if user_id != user.user_id:
            raise ValueError("Идентификатор не совпадает с пользователем.")

        self._user_id = user_id
        self._user = user
        self._wallets: dict[str, Wallet] = {}

        if wallets is not None:
            for code, wallet in wallets.items():
                if not isinstance(wallet, Wallet):
                    raise TypeError("Значение должно быть объектом Wallet.")
                if code != wallet.currency_code:
                    raise ValueError("Ключ не совпадает с кодом кошелька.")
                self._wallets[code] = wallet

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def user(self) -> User:
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Возвращает копию словаря с теми же объектами кошельков."""
        return self._wallets.copy()

    @staticmethod
    def _normalize_currency(currency_code: str) -> str:
        if not isinstance(currency_code, str) or not currency_code.strip():
            raise ValueError("Код валюты не может быть пустым.")
        return currency_code.strip().upper()

    def add_currency(self, currency_code: str) -> None:
        """Создаёт пустой кошелёк, запрещая повторное добавление валюты."""
        code = self._normalize_currency(currency_code)
        if code in self._wallets:
            raise ValueError(f"Кошелёк {code} уже существует.")

        self._wallets[code] = Wallet(code)

    def get_wallet(self, currency_code: str) -> Wallet:
        code = self._normalize_currency(currency_code)
        if code not in self._wallets:
            raise ValueError(f"Кошелёк {code} не найден.")

        return self._wallets[code]

    def get_total_value(self, base_currency: str = "USD") -> float:
        """Пересчитывает балансы в базовую валюту по учебным курсам."""
        exchange_rates = {
            "USD": 1.0,
            "EUR": 1.1,
            "RUB": 0.01,
            "BTC": 60000.0,
            "ETH": 3000.0,
        }

        base = self._normalize_currency(base_currency)
        if base not in exchange_rates:
            raise ValueError(f"Неизвестен курс базовой валюты {base}.")

        total = 0.0
        for code, wallet in self._wallets.items():
            if code == base:
                total += wallet.balance
                continue

            if code not in exchange_rates:
                raise ValueError(f"Неизвестен курс валюты {code}.")

            rate = exchange_rates[code] / exchange_rates[base]
            total += wallet.balance * rate

        return total