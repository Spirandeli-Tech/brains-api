import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.db import Base, get_db
from app.main import app
from app.models.user import User


# In-memory SQLite for tests
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()


def _make_user(user_id: uuid.UUID) -> User:
    user = User.__new__(User)
    user.id = user_id
    user.email = f"{user_id}@test.com"
    user.first_name = "Test"
    user.last_name = "User"
    user.firebase_id = str(user_id)
    return user


def make_override_current_user(user_id: uuid.UUID):
    def override():
        return _make_user(user_id)
    return override


@pytest.fixture()
def client_a() -> TestClient:
    """Test client authenticated as User A."""
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = make_override_current_user(USER_A_ID)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def client_b() -> TestClient:
    """Test client authenticated as User B."""
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = make_override_current_user(USER_B_ID)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def unauthenticated_client() -> TestClient:
    """Test client with no auth (dependency overrides only for DB)."""
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
