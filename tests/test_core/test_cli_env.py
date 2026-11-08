"""Tests for CLI environment-file loading order."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path


def test_explicit_env_is_loaded_before_settings(tmp_path):
    env_file = tmp_path / "custom.env"
    env_file.write_text("LLM_MODEL=explicit-env-marker\n", encoding="utf-8")
    script = """
import json
import claxcode.cli as module

class FakeCLI:
    def __init__(self, **kwargs):
        pass

    async def one_shot(self, prompt):
        print(json.dumps({'model': module.settings.llm_model}))

module.InteractiveCLI = FakeCLI
module.main()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, "--env", str(env_file), "--print", "test"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"model": "explicit-env-marker"}


def test_version_flag():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    expected = pyproject["project"]["version"]
    result = subprocess.run(
        [sys.executable, "-m", "claxcode.cli", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
