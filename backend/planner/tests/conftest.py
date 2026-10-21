import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Provider results, throttles and the weather budget all live in the cache."""
    cache.clear()
    yield
    cache.clear()
