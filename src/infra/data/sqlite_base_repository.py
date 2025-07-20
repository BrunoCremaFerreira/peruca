from abc import ABC, abstractmethod


class SqliteBaseRepository(ABC):
    """
    Base repository class for Sqlite repositories implementation
    """

    def __init__(self, db_path: str):
        self.db_path = db_path.replace("sqlite://", "")
        self._startup()

    @abstractmethod
    def _startup(self) -> None:
        pass

    @abstractmethod
    def _create_table(self) -> None:
        pass