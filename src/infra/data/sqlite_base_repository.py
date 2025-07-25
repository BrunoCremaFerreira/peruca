from abc import ABC, abstractmethod
import sqlite3


class SqliteBaseRepository(ABC):
    """
    Base repository class for Sqlite repositories implementation
    """

    def __init__(self, db_path: str):
        self.db_path = db_path.replace("sqlite://", "")
        self._startup()

    #=======================================
    # Abstract Methods
    #=======================================

    @abstractmethod
    def _startup(self) -> None:
        pass

    @abstractmethod
    def _create_table(self) -> None:
        pass

    #=======================================
    # Connection Methods
    #=======================================

    def connect(self):
        """
        Connect to the database
        """
        print(f"[{self.__class__.__name__}]: Connecting to '{self.db_path}'...")
        self.conn = sqlite3.connect(database=self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()