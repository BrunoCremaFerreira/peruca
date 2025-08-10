from typing import List, Optional
from domain.entities import ShoppingListItem
from domain.interfaces.repository import ShoppingListRepository
from infra.data.sqlite.sqlite_base_repository import SqliteBaseRepository


class SqliteShoppingListRepository(SqliteBaseRepository, ShoppingListRepository):
    """
    Shopping List Sqlite implementation repository
    """

    def __init__(self, db_path: str):
        super().__init__(db_path=db_path)

    def _startup(self) -> None:
        self.connect()
        self._create_table()

    def _create_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS shopping_list (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    quantity FLOAT,
                    checked BOOLEAN NOT NULL DEFAULT 0,
                    when_created TIMESTAMP,
                    when_updated TIMESTAMP DEFAULT NULL,
                    when_deleted TIMESTAMP DEFAULT NULL
                )
            """)

    def add(self, shopping_list_item: ShoppingListItem):
        with self.conn:
            self.conn.execute(
                "INSERT INTO shopping_list (id, name, quantity, when_created) VALUES (?, ?, ?, ?)",
                (shopping_list_item.id,
                 shopping_list_item.name,
                 shopping_list_item.quantity,
                 shopping_list_item.when_created)
            )
    
    
    def get_by_id(self, item_id: str) -> Optional[ShoppingListItem]:
        """
        Get Shopping List Item By Id
        """
        cursor = self.conn.execute(
            "SELECT id, name, quantity, checked, when_created, when_updated, when_deleted FROM shopping_list WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return self._map_shopping_list_item(row) if row else None
    
    def get_by_name(self, item_name: str) -> Optional[ShoppingListItem]:
        """
        Get Shopping List Item By Name
        """
        cursor = self.conn.execute(
            "SELECT id, name, quantity, checked, when_created, when_updated, when_deleted FROM shopping_list WHERE LOWER(name) = ?", (item_name.lower(),))
        row = cursor.fetchone()
        return self._map_shopping_list_item(row) if row else None
    
    def get_all(self) -> List[ShoppingListItem]:
        """
        List All Shopping List
        """
        cursor = self.conn.execute("SELECT id, name, quantity, checked, when_created, when_updated, when_deleted FROM shopping_list")
        return [self._map_shopping_list_item(row) for row in cursor.fetchall()]


    def update(self, item: ShoppingListItem):
        """
        Update Shopping List Item
        """
        with self.conn:
            self.conn.execute(
                "UPDATE shopping_list SET name = ?, quantity = ?, when_created = ? WHERE id = ?",
                (item.name, item.quantity, item.when_created, item.id)
            )

    def delete(self, item_id: str):
        """
        Delete Shopping List Item
        """
        with self.conn:
            self.conn.execute("DELETE FROM shopping_list WHERE id = ?", (item_id,))

    def clear(self):
        """
        Delete all Shopping List Items
        """
        with self.conn:
            self.conn.execute("DELETE FROM shopping_list")

    def _map_shopping_list_item(self, row):
        return ShoppingListItem(
            id=row["id"],
            name=row["name"],
            quantity=row["quantity"],
            checked=row["checked"],
            when_created=row["when_created"],
            when_updated=row["when_updated"],
            when_deleted=row["when_deleted"])
