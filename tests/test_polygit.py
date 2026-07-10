import tempfile
import pytest
from pathlib import Path
from polygit.config import find_config, load_config, write_config
from polygit.repos import parse_remote_url, del_nested
from polygit.repo import walk


# ── parse_remote_url ──────────────────────────────────────────────────────────

def test_parse_github_ssh():
    platform, path = parse_remote_url("git@github.com:gschaetz/mousehat.git")
    assert platform == "github"
    assert path == "gschaetz/mousehat"

def test_parse_gitlab_ssh_nested():
    platform, path = parse_remote_url("git@gitlab.com:gary.schaetz/private/dev-setup.git")
    assert platform == "gitlab"
    assert path == "gary.schaetz/private/dev-setup"

def test_parse_https():
    platform, path = parse_remote_url("https://github.com/openclaw/openclaw")
    assert platform == "github"
    assert path == "openclaw/openclaw"

def test_parse_none():
    platform, path = parse_remote_url(None)
    assert platform is None
    assert path is None


# ── walk ──────────────────────────────────────────────────────────────────────

def test_walk_null():
    results = list(walk(None, "ns/repo"))
    assert results == [("ns/repo", "ns/repo")]

def test_walk_remote_override():
    results = list(walk({"remote": "other/repo"}, "ns/local"))
    assert results == [("ns/local", "other/repo")]

def test_walk_nested():
    node = {"a": None, "b": {"c": None}}
    results = list(walk(node, "ns"))
    assert ("ns/a", "ns/a") in results
    assert ("ns/b/c", "ns/b/c") in results


# ── del_nested ────────────────────────────────────────────────────────────────

def test_del_nested_simple():
    d = {"a": {"b": None}}
    del_nested(d, ["a", "b"])
    assert d == {}

def test_del_nested_preserves_siblings():
    d = {"a": {"b": None, "c": None}}
    del_nested(d, ["a", "b"])
    assert d == {"a": {"c": None}}


# ── find_config / write_config / load_config ──────────────────────────────────

def test_find_config_in_cwd():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / ".pgit"
        config_path.write_text("github:\n  org:\n    repo:\n")
        found = find_config(start=tmp)
        assert found == config_path

def test_find_config_walks_up():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / ".pgit"
        config_path.write_text("github:\n  org:\n    repo:\n")
        subdir = Path(tmp) / "sub" / "dir"
        subdir.mkdir(parents=True)
        found = find_config(start=subdir)
        assert found == config_path

def test_find_config_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        found = find_config(start=tmp)
        assert found is None

def test_write_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".pgit"
        data = {
            "github": {
                "gschaetz": {"mousehat": None, "dotfiles": None},
                "community": {"openclaw": {"remote": "openclaw/openclaw"}},
            }
        }
        write_config(data, path)
        loaded = load_config(path)
        assert loaded["github"]["gschaetz"]["mousehat"] is None
        assert loaded["github"]["community"]["openclaw"] == {"remote": "openclaw/openclaw"}
