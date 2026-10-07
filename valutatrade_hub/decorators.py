import logging
from functools import wraps
from inspect import signature

from valutatrade_hub.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


def _format_fields(fields: dict) -> str:
    return " ".join(f"{key}={value!r}" for key, value in fields.items())


def log_action(action: str, *, verbose: bool = False):
    """Записывает результат операции и передаёт исключения вызывающему коду."""

    def decorator(func):
        func_signature = signature(func)

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            bound = func_signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            arguments = bound.arguments

            user = self.current_user
            currency = arguments.get("currency_code", arguments.get("currency"))
            if isinstance(currency, str):
                currency = currency.strip().upper()

            fields = {
                "action": action.upper(),
                "username": user.username if user is not None else None,
                "currency_code": currency,
                "amount": arguments.get("amount"),
                "base": "USD",
            }

            try:
                result = func(self, *args, **kwargs)
            except Exception as error:
                # Фиксируем любой сбой операции и пробрасываем его без замены.
                fields.update(
                    result="ERROR",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                logger.info("%s", _format_fields(fields))
                raise

            fields["result"] = "OK"

            if isinstance(result, dict):
                fields["rate"] = result.get("rate")

                if verbose:
                    for key in (
                        "balance_before",
                        "balance_after",
                        "usd_before",
                        "usd_after",
                    ):
                        if key in result:
                            fields[key] = result[key]

            logger.info("%s", _format_fields(fields))
            return result

        return wrapper

    return decorator
