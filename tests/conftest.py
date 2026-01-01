"""Shared pytest fixtures for serendipity tests."""

import tempfile
from pathlib import Path

import pytest

from serendipity.storage import StorageManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_storage(temp_dir):
    """Create a temporary StorageManager."""
    storage = StorageManager(base_dir=temp_dir)
    storage.ensure_dirs()
    return storage


@pytest.fixture
def temp_storage_with_taste(temp_storage):
    """Create a temporary StorageManager with a taste profile."""
    temp_storage.save_taste("I love jazz and science fiction.")
    return temp_storage
