import uuid
import pytest

from domain.entities import User


@pytest.fixture
def sample_user_entity():
    uid = str(uuid.uuid4())
    return User(id=uid, external_id=uid, name="Alice", summary="test summary")
