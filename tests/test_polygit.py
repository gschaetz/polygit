import subprocess
import tempfile
import pytest
from pathlib import Path
from polygit.config import find_config, load_config, write_config
from polygit.repos import parse_remote_url, del_nested, _add_to_config
from polygit.repo import walk, _pull_one, cmd_push


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


# ── _add_to_config ──────────────────────────────────────────────────────────

def test_add_to_config_plain():
    config = {}
    _add_to_config(config, "github", "gschaetz/mousehat", "git@github.com:gschaetz/mousehat.git")
    assert config == {"github": {"gschaetz": {"mousehat": None}}}

def test_add_to_config_cross_namespace_override():
    # Local dir lives under a namespace unrelated to the remote org — must
    # nest under the local namespace, not silently fall back to the remote's.
    config = {}
    _add_to_config(config, "github", "community/modelrelay", "git@github.com:ellipticmarketing/modelrelay.git")
    assert config == {"github": {"community": {"modelrelay": {"remote": "ellipticmarketing/modelrelay"}}}}

def test_add_to_config_no_remote():
    config = {}
    _add_to_config(config, "github", "gschaetz/scratch", None)
    assert config == {"github": {"gschaetz": {"scratch": None}}}


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


# ── dry-run pull / push ──────────────────────────────────────────────────────

def _git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


def _commit(d, name):
    (d / name).write_text(name)
    _git(d, "add", ".")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qm", name)


def _make_clone(tmp, ahead=0, behind=0):
    """Clone of a bare origin, `ahead` commits ahead and `behind` behind it."""
    origin = tmp / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True, capture_output=True)
    _commit(seed, "init")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    d = tmp / "github" / "r"
    d.parent.mkdir()
    subprocess.run(["git", "clone", "-q", str(origin), str(d)], check=True, capture_output=True)
    for i in range(behind):
        _commit(seed, f"b{i}")
    if behind:
        _git(seed, "push", "-q", "origin", "HEAD:main")
        _git(d, "fetch", "-q")
    for i in range(ahead):
        _commit(d, f"a{i}")
    return d


def test_pull_dry_run_shows_ahead_behind(capsys, tmp_path):
    d = _make_clone(tmp_path, ahead=2, behind=1)
    _pull_one("github", "r", d, dry_run=True)
    assert "2 ahead, 1 behind" in capsys.readouterr().out


def test_pull_dry_run_up_to_date(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _pull_one("github", "r", d, dry_run=True)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "ahead" not in out and "behind" not in out


def test_pull_dry_run_no_upstream(capsys, tmp_path):
    d = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    _pull_one("github", "r", d, dry_run=True)
    assert "no upstream" in capsys.readouterr().out


def test_pull_dry_run_leaves_dirty_tree_alone(tmp_path):
    d = _make_clone(tmp_path)
    (d / "init").write_text("edited")
    (d / "new.txt").write_text("x")
    _pull_one("github", "r", d, dry_run=True)
    assert (d / "init").read_text() == "edited"
    assert (d / "new.txt").exists()
    stash = subprocess.run(["git", "-C", str(d), "stash", "list"],
                           capture_output=True, text=True).stdout
    assert stash == ""


def test_push_dry_run_lists_dirty_without_committing(capsys, tmp_path):
    d = _make_clone(tmp_path)
    (d / "dirty.txt").write_text("x")
    cmd_push({"github": {"r": None}}, tmp_path, dry_run=True)
    out = capsys.readouterr().out
    assert "Would commit and push" in out
    assert "github/r" in out
    assert (d / "dirty.txt").exists()
    log = subprocess.run(["git", "-C", str(d), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert len(log.splitlines()) == 1
