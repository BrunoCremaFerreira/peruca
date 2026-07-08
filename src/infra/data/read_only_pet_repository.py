from typing import List, Optional

from domain.entities import Pet
from domain.interfaces.pet_repository import PetReadRepository


class ReadOnlyPetRepository(PetReadRepository):
    """
    Read-only adapter over a pet repository. It exposes ONLY the read methods, so
    the object handed to the chat/graph path physically lacks add/update/delete
    (§2.4, level 1). This turns the "no pet writes from chat" guarantee into a
    structural one: even a future refactor that tried to write would not compile
    against this object, instead of relying on a nominal type annotation that
    Python does not enforce at runtime.
    """

    def __init__(self, inner: PetReadRepository):
        self._inner = inner

    def get_by_id(self, pet_id: str) -> Optional[Pet]:
        return self._inner.get_by_id(pet_id)

    def get_all_by_user_id(self, user_id: str) -> List[Pet]:
        return self._inner.get_all_by_user_id(user_id)
