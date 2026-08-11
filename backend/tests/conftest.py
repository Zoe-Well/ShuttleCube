import os
from collections.abc import Generator
from datetime import time
from decimal import Decimal

os.environ["SHUTTLECUBE_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SHUTTLECUBE_SECRET_KEY"] = "test-secret-key-that-is-long-enough"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from shuttlecube.app import create_app
from shuttlecube.domain import models as _models  # noqa: F401
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.venue_bookings.models import VenuePriceRule
from shuttlecube.infrastructure.database.base import Base
from shuttlecube.infrastructure.database.session import get_db
from shuttlecube.infrastructure.security.passwords import hash_password

pytest_plugins = ("tests.fixtures.users",)


@pytest.fixture
def db() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as session:
        yield session


@pytest.fixture
def zero_price_rules(db: Session) -> None:
    """Pricing-neutral setup for integration tests that exercise unrelated booking behavior."""
    db.add_all(
        [
            VenuePriceRule(
                name="测试工作日价格",
                day_type="weekday",
                time_start=time(0),
                time_end=time(23, 59, 59),
                price_per_court_hour=Decimal("0"),
            ),
            VenuePriceRule(
                name="测试周末价格",
                day_type="weekend",
                time_start=time(0),
                time_end=time(23, 59, 59),
                price_per_court_hour=Decimal("0"),
            ),
        ]
    )
    db.commit()


@pytest.fixture
def postgres_db() -> Generator[Session]:
    """Real PostgreSQL fixture for transaction/concurrency tests that opt into it."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine") as postgres:
        pg_engine = create_engine(postgres.get_connection_url())
        Base.metadata.create_all(pg_engine)
        maker = sessionmaker(bind=pg_engine, expire_on_commit=False)
        with maker() as session:
            yield session
            session.rollback()
        Base.metadata.drop_all(pg_engine)


@pytest.fixture
def client(db: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin(db: Session) -> SystemUser:
    user = SystemUser(
        username="owner1", display_name="聂老板", password_hash=hash_password("password123")
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def authenticated(client: TestClient, admin: SystemUser) -> tuple[TestClient, dict[str, str]]:
    response = client.post(
        "/api/v1/session/login", json={"username": admin.username, "password": "password123"}
    )
    assert response.status_code == 200
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}
