import pytest
from sqlalchemy.orm import Session

from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.security.passwords import hash_password


@pytest.fixture
def two_admins(db: Session) -> tuple[SystemUser, SystemUser]:
    users = (
        SystemUser(
            username="owner1", display_name="管理员一", password_hash=hash_password("password123")
        ),
        SystemUser(
            username="owner2", display_name="管理员二", password_hash=hash_password("password123")
        ),
    )
    db.add_all(users)
    db.commit()
    return users
