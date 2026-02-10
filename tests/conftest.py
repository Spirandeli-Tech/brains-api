import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, String, event
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_user
from app.core.db import Base, get_db
from app.main import app
from app.models.user import User


# Make PostgreSQL UUID type work with SQLite in tests:
# 1. Compile UUID as VARCHAR(36) for SQLite DDL
@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


# 2. Override the UUID bind/result processors for SQLite so it stores/returns strings
_orig_pg_uuid_bind = PG_UUID.bind_processor
_orig_pg_uuid_result = PG_UUID.result_processor


def _uuid_bind_processor_sqlite(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is not None:
                return str(value) if isinstance(value, uuid.UUID) else value
            return value
        return process
    return _orig_pg_uuid_bind(self, dialect)


def _uuid_result_processor_sqlite(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is not None:
                return uuid.UUID(value) if self.as_uuid else value
            return value
        return process
    return _orig_pg_uuid_result(self, dialect, coltype)


PG_UUID.bind_processor = _uuid_bind_processor_sqlite
PG_UUID.result_processor = _uuid_result_processor_sqlite


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


class FakeUser:
    """Lightweight user stub that avoids SQLAlchemy descriptor issues."""
    def __init__(self, user_id: uuid.UUID):
        self.id = user_id
        self.email = f"{user_id}@test.com"
        self.first_name = "Test"
        self.last_name = "User"
        self.firebase_id = str(user_id)


def _make_user(user_id: uuid.UUID):
    return FakeUser(user_id)


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
