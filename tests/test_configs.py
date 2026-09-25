"""The copy/paste client configs start the published image in a way that keeps the paper ledger."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VOLUME = "readytrader-forex-data:/app/data"


def _args():
    desktop = json.loads((ROOT / "configs" / "claude_desktop.mcp-server-config.json").read_text())
    agent_zero = yaml.safe_load((ROOT / "configs" / "agent_zero.mcp.yaml").read_text())
    return [
        desktop["mcpServers"]["readytrader_forex"]["args"],
        agent_zero["mcp_servers"]["readytrader_forex"]["args"],
    ]


def test_every_docker_config_mounts_the_data_volume():
    for args in _args():
        assert args[:2] == ["run", "-i"] and args[-1] == "readytrader-forex"
        assert args[args.index("-v") + 1] == VOLUME, args


def test_the_readme_examples_match_the_config_files():
    readme = (ROOT / "README.md").read_text()
    assert readme.count(VOLUME) >= 4
    assert "docker run --rm -i readytrader-forex" not in readme


def test_the_image_never_bakes_in_local_state():
    ignored = {line.strip().rstrip("/") for line in (ROOT / ".dockerignore").read_text().splitlines() if line.strip() and not line.startswith("#")}
    # frontend/ as a whole (node_modules included); .env files and databases in any folder.
    assert {"data", ".venv", ".git", "uat", "frontend", "**/.env*", "**/*.db"} <= ignored