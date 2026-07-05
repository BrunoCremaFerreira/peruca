from abc import ABC, abstractmethod
import logging
import sqlite3


logger = logging.getLogger(__name__)


class SqliteBaseRepository(ABC):
    """
    Base repository class for Sqlite repositories implementation
    """

    def __init__(self, db_path: str):
        self.db_path = db_path.replace("sqlite://", "")
        self._startup()

    # =======================================
    # Abstract Methods
    # =======================================

    @abstractmethod
    def _startup(self) -> None:
        pass

    @abstractmethod
    def _create_table(self) -> None:
        pass

    # =======================================
    # Connection Methods
    # =======================================

    def connect(self):
        """
        Connect to the database
        """
        logger.info("%s connecting to %r", self.__class__.__name__, self.db_path)
        self.conn = sqlite3.connect(database=self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    def close(self):
        self.conn.close()
