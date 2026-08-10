# Python Testing — Reference

## Core Concepts

### Test Types

- **Unit Tests**: Test individual functions/classes in isolation
- **Integration Tests**: Test interaction between components
- **Functional Tests**: Test complete features end-to-end
- **Performance Tests**: Measure speed and resource usage

### Test Structure (AAA Pattern)

- **Arrange**: Set up test data and preconditions
- **Act**: Execute the code under test
- **Assert**: Verify the results

### Test Coverage

- Measure what code is exercised by tests
- Identify untested code paths
- Aim for meaningful coverage, not just high percentages

### Test Isolation

- Tests should be independent
- No shared state between tests
- Each test should clean up after itself

## Quick Start

```python
# test_example.py
def add(a, b):
    return a + b

def test_add():
    result = add(2, 3)
    assert result == 5

def test_add_negative():
    assert add(-1, 1) == 0

# Run with: pytest test_example.py
```

## Test Organization

```
tests/
  __init__.py
  conftest.py           # Shared fixtures
  test_unit/            # Unit tests
    test_models.py
    test_utils.py
  test_integration/     # Integration tests
    test_api.py
    test_database.py
  test_e2e/            # End-to-end tests
    test_workflows.py
```

## Test Naming Convention

A common pattern: `test_<unit>_<scenario>_<expected_outcome>`. Adapt to your team's preferences.

```python
def test_create_user_with_valid_data_returns_user():
    ...

def test_create_user_with_duplicate_email_raises_conflict():
    ...

def test_get_user_with_unknown_id_returns_none():
    ...

# Good test names - clear and descriptive
def test_user_creation_with_valid_data():
    """Clear name describes what is being tested."""
    pass

def test_login_fails_with_invalid_password():
    """Name describes expected behavior."""
    pass

# Bad test names - avoid these
def test_1():       # Not descriptive
    pass
def test_user():    # Too vague
    pass
def test_function():  # Doesn't explain what's tested
    pass
```

## Testing Retry Behavior

```python
from unittest.mock import Mock

def test_retries_on_transient_error():
    """Test that service retries on transient failures."""
    client = Mock()
    client.request.side_effect = [
        ConnectionError("Failed"),
        ConnectionError("Failed"),
        {"status": "ok"},
    ]
    service = ServiceWithRetry(client, max_retries=3)
    result = service.fetch()
    assert result == {"status": "ok"}
    assert client.request.call_count == 3

def test_gives_up_after_max_retries():
    client = Mock()
    client.request.side_effect = ConnectionError("Failed")
    service = ServiceWithRetry(client, max_retries=3)
    with pytest.raises(ConnectionError):
        service.fetch()
    assert client.request.call_count == 3

def test_does_not_retry_on_permanent_error():
    client = Mock()
    client.request.side_effect = ValueError("Invalid input")
    service = ServiceWithRetry(client, max_retries=3)
    with pytest.raises(ValueError):
        service.fetch()
    # Only called once - no retry for ValueError
    assert client.request.call_count == 1
```

## Mocking Time with Freezegun

```python
from freezegun import freeze_time
from datetime import datetime, timedelta

@freeze_time("2026-01-15 10:00:00")
def test_token_expiry():
    token = create_token(expires_in_seconds=3600)
    assert token.expires_at == datetime(2026, 1, 15, 11, 0, 0)

def test_with_time_travel():
    with freeze_time("2026-01-01") as frozen_time:
        item = create_item()
        assert item.created_at == datetime(2026, 1, 1)
        frozen_time.move_to("2026-01-15")
        assert item.age_days == 14
```

## Test Markers

```python
import pytest

@pytest.mark.slow
def test_slow_operation():
    import time
    time.sleep(2)

@pytest.mark.integration
def test_database_integration():
    pass

@pytest.mark.skip(reason="Feature not implemented yet")
def test_future_feature():
    pass

@pytest.mark.skipif(os.name == "nt", reason="Unix only test")
def test_unix_specific():
    pass

@pytest.mark.xfail(reason="Known bug #123")
def test_known_bug():
    assert False

# Run with:
# pytest -m slow          # Run only slow tests
# pytest -m "not slow"    # Skip slow tests
# pytest -m integration   # Run integration tests
```

## Coverage Reporting

```bash
pip install pytest-cov
pytest --cov=myapp tests/
pytest --cov=myapp --cov-report=html tests/
pytest --cov=myapp --cov-fail-under=80 tests/
pytest --cov=myapp --cov-report=term-missing tests/
```

## Testing Async Code

```python
# test_async.py
import pytest
import asyncio

async def fetch_data(url: str) -> dict:
    await asyncio.sleep(0.1)
    return {"url": url, "data": "result"}

@pytest.mark.asyncio
async def test_fetch_data():
    result = await fetch_data("https://api.example.com")
    assert result["url"] == "https://api.example.com"
    assert "data" in result

@pytest.mark.asyncio
async def test_concurrent_fetches():
    urls = ["url1", "url2", "url3"]
    tasks = [fetch_data(url) for url in urls]
    results = await asyncio.gather(*tasks)
    assert len(results) == 3
    assert all("data" in r for r in results)

@pytest.fixture
async def async_client():
    client = {"connected": True}
    yield client
    client["connected"] = False

@pytest.mark.asyncio
async def test_with_async_fixture(async_client):
    assert async_client["connected"] is True
```

## Monkeypatch for Testing

```python
# test_environment.py
import os
import pytest

def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///:memory:")

def test_database_url_custom(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    assert get_database_url() == "postgresql://localhost/test"

def test_database_url_not_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == "sqlite:///:memory:"

class Config:
    def __init__(self):
        self.api_key = "production-key"
    def get_api_key(self):
        return self.api_key

def test_monkeypatch_attribute(monkeypatch):
    config = Config()
    monkeypatch.setattr(config, "api_key", "test-key")
    assert config.get_api_key() == "test-key"
```

## Temporary Files and Directories

```python
# test_file_operations.py
from pathlib import Path

def save_data(filepath: Path, data: str):
    filepath.write_text(data)

def load_data(filepath: Path) -> str:
    return filepath.read_text()

def test_file_operations(tmp_path):
    """tmp_path is a pathlib.Path object provided by pytest."""
    test_file = tmp_path / "test_data.txt"
    save_data(test_file, "Hello, World!")
    assert test_file.exists()
    assert load_data(test_file) == "Hello, World!"

def test_multiple_files(tmp_path):
    files = {"file1.txt": "Content 1", "file2.txt": "Content 2", "file3.txt": "Content 3"}
    for filename, content in files.items():
        save_data(tmp_path / filename, content)
    assert len(list(tmp_path.iterdir())) == 3
```

## Custom Fixtures and Conftest

```python
# conftest.py
"""Shared fixtures for all tests."""
import pytest

@pytest.fixture(scope="session")
def database_url():
    return "postgresql://localhost/test_db"

@pytest.fixture(autouse=True)
def reset_database(database_url):
    """Auto-use fixture that runs before each test."""
    print(f"Clearing database: {database_url}")
    yield
    print("Test completed")

@pytest.fixture
def sample_user():
    return {"id": 1, "name": "Test User", "email": "test@example.com"}

# Parametrized fixture
@pytest.fixture(params=["sqlite", "postgresql", "mysql"])
def db_backend(request):
    return request.param

def test_with_db_backend(db_backend):
    """This test will run 3 times with different backends."""
    assert db_backend in ["sqlite", "postgresql", "mysql"]
```

## Property-Based Testing

```python
# test_properties.py
from hypothesis import given, strategies as st

def reverse_string(s: str) -> str:
    return s[::-1]

@given(st.text())
def test_reverse_twice_is_original(s):
    assert reverse_string(reverse_string(s)) == s

@given(st.integers(), st.integers())
def test_addition_commutative(a, b):
    assert a + b == b + a

@given(st.lists(st.integers()))
def test_sorted_list_properties(lst):
    sorted_lst = sorted(lst)
    assert len(sorted_lst) == len(lst)
    assert set(sorted_lst) == set(lst)
    for i in range(len(sorted_lst) - 1):
        assert sorted_lst[i] <= sorted_lst[i + 1]
```

## Testing Database Code

```python
# test_database_models.py
import pytest
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    email = Column(String(100), unique=True)

@pytest.fixture(scope="function")
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()

def test_create_user(db_session):
    user = User(name="Test User", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None

def test_unique_email_constraint(db_session):
    from sqlalchemy.exc import IntegrityError
    user1 = User(name="User 1", email="same@example.com")
    user2 = User(name="User 2", email="same@example.com")
    db_session.add(user1)
    db_session.commit()
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
```

## CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - run: |
          pip install -e ".[dev]"
          pip install pytest pytest-cov
      - run: pytest --cov=myapp --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

## Configuration Files

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
    --cov=myapp
    --cov-report=term-missing
markers =
    slow: marks tests as slow
    integration: marks integration tests
    unit: marks unit tests
    e2e: marks end-to-end tests
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = ["-v", "--cov=myapp", "--cov-report=term-missing"]

[tool.coverage.run]
source = ["myapp"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```
