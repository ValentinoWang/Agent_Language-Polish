from __future__ import annotations

from pathlib import Path

import pytest

from styleos.service import StyleOSPaths, StyleOSService


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).parents[1]


@pytest.fixture
def service(repository_root: Path, tmp_path: Path) -> StyleOSService:
    return StyleOSService(StyleOSPaths.resolve(repository=repository_root, home=tmp_path / "state"))
