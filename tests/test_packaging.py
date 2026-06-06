from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_declares_hermes_entry_points():
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert data["project"]["name"] == "voxvey"
    entry_points = data["project"]["entry-points"]["hermes_agent.plugins"]
    assert entry_points == {
        "voxvey": "voxvey.auth_plugin",
        "voxvey-model-provider": "voxvey.model_provider",
        "voxvey-image-gen": "voxvey.image_gen",
        "voxvey-video-gen": "voxvey.video_gen",
        "voxvey-search": "voxvey.search",
    }
    assert data["project"]["scripts"]["voxvey"] == "voxvey.auth_cli:main"
    assert data["project"]["scripts"]["voxvey-auth"] == "voxvey.oauth:run_login_cli"
