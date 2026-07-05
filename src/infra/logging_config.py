import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(level: str | int) -> None:
    """Configure structured logging on the root logger.

    Idempotent: removes only the handlers this function previously added
    (tagged with the ``_peruca`` attribute) and installs exactly one new
    tagged ``StreamHandler`` writing to stdout. Foreign handlers (e.g. the
    ones installed by uvicorn) are left untouched.

    ``level`` accepts both a string name and an integer. An invalid string
    level propagates the ``ValueError`` raised by ``root.setLevel``.
    """
    root = logging.getLogger()

    root.handlers[:] = [
        handler
        for handler in root.handlers
        if not getattr(handler, "_peruca", False)
    ]

    handler = logging.StreamHandler(sys.stdout)
    handler._peruca = True
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
    root.addHandler(handler)

    root.setLevel(level)
