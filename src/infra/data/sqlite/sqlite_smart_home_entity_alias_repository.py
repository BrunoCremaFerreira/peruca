from typing import Optional
from domain.entities import SmartHomeEntityAlias
from domain.interfaces.repository import SmartHomeEntityAliasRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteSmartHomeEntityAliasRepository(SqliteBaseRepository, SmartHomeEntityAliasRepository):
    
    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    
    def add(self, entity_alias: SmartHomeEntityAlias):
        """
        Add Smart Home Entity Alias
        """
        pass

    def get_by_id(self, entity_id: str) -> Optional[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias by Entity Id
        """
        pass

    def get_by_alias(self, alias: str) -> Optional[SmartHomeEntityAlias]:
        """
        Get Smart Home Entity Alias
        """
        pass

    def delete_all(self) -> None:
        """
        Remove all SmartHomeEntityAlias
        """
        pass