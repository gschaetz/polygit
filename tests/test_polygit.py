import json
import subprocess
import tempfile
import pytest
from pathlib import Path
from polygit.config import find_config, load_config, write_config
from polygit.repos import parse_remote_url, del_nested, _add_to_config
from polygit.repo import walk, _pull_one, cmd_push, cmd_status, cmd_pull, cmd_sync


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


def test_push_commit_failed_reports_error(capsys, tmp_path):
    d = _make_clone(tmp_path)
    (d / "dirty.txt").write_text("x")
    hook = d / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'pre-commit hook failed'\nexit 1\n")
    hook.chmod(0o755)

    from polygit.repo import _commit_and_push
    _commit_and_push(d, "github/r", "WIP test")

    out = capsys.readouterr().out
    assert "commit failed" in out
    assert "pushed" not in out


def test_push_nothing_to_commit_reports_error(capsys, tmp_path):
    """A repo with no staged changes must not crash and must not push."""
    d = _make_clone(tmp_path)
    # No changes staged — git commit will refuse.

    from polygit.repo import _commit_and_push
    _commit_and_push(d, "github/r", "WIP test")

    out = capsys.readouterr().out
    assert "commit failed" in out
    assert "pushed" not in out


# ── --jobs parallelism ───────────────────────────────────────────────────────

def _run_main(monkeypatch, *argv):
    import sys
    from polygit.cli import main
    monkeypatch.setattr(sys, "argv", ["pgit", *argv])
    with pytest.raises(SystemExit) as exc:
        main()
    return exc.value.code


@pytest.mark.parametrize("value, message", [
    ("0", "positive integer"),
    ("-3", "positive integer"),
    ("lots", "invalid int value"),
])
@pytest.mark.parametrize("command", ["sync", "status", "pull", "push"])
def test_jobs_invalid_exits_2_before_config_lookup(capsys, tmp_path, monkeypatch,
                                                   command, value, message):
    # No .pgit here: argparse must reject the value before the config is read.
    monkeypatch.chdir(tmp_path)
    assert _run_main(monkeypatch, command, "--jobs", value) == 2
    err = capsys.readouterr().err
    assert "--jobs" in err and message in err


@pytest.fixture
def pool_sizes(monkeypatch):
    """Record the max_workers of every ThreadPoolExecutor the commands create."""
    from concurrent.futures import ThreadPoolExecutor
    sizes = []

    class Spy(ThreadPoolExecutor):
        def __init__(self, max_workers=None, *a, **kw):
            sizes.append(max_workers)
            super().__init__(max_workers, *a, **kw)

    monkeypatch.setattr("polygit.repo.ThreadPoolExecutor", Spy)
    return sizes


def _dirty_clone(tmp_path):
    d = _make_clone(tmp_path)
    (d / "x.txt").write_text("x")
    return d


def test_sync_uses_jobs(pool_sizes, tmp_path):
    _make_clone(tmp_path)
    cmd_sync({"github": {"r": None}}, tmp_path, jobs=3)
    assert pool_sizes == [3]


def test_status_uses_jobs(pool_sizes, tmp_path):
    _dirty_clone(tmp_path)
    cmd_status({"github": {"r": None}}, tmp_path, jobs=4)
    assert pool_sizes == [4]


def test_pull_uses_jobs(pool_sizes, tmp_path):
    _make_clone(tmp_path)
    cmd_pull({"github": {"r": None}}, tmp_path, dry_run=True, jobs=2)
    assert pool_sizes == [2]


def test_push_wip_uses_jobs(pool_sizes, tmp_path):
    _dirty_clone(tmp_path)
    cmd_push({"github": {"r": None}}, tmp_path, mode="wip", jobs=5)
    assert pool_sizes == [5]


def test_push_all_uses_jobs(pool_sizes, tmp_path, monkeypatch):
    _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "msg")
    cmd_push({"github": {"r": None}}, tmp_path, mode="all", jobs=6)
    assert pool_sizes == [6]


@pytest.mark.parametrize("run", [
    lambda tp: cmd_sync({"github": {"r": None}}, tp),
    lambda tp: cmd_status({"github": {"r": None}}, tp),
    lambda tp: cmd_pull({"github": {"r": None}}, tp, dry_run=True),
])
def test_default_pool_size_is_max_workers(pool_sizes, tmp_path, run):
    from polygit.repo import MAX_WORKERS
    _make_clone(tmp_path)
    run(tmp_path)
    assert pool_sizes == [MAX_WORKERS]


def test_push_wip_default_pool_size_is_max_workers(pool_sizes, tmp_path):
    from polygit.repo import MAX_WORKERS
    _dirty_clone(tmp_path)
    cmd_push({"github": {"r": None}}, tmp_path, mode="wip")
    assert pool_sizes == [MAX_WORKERS]


def test_push_interactive_creates_no_pool(pool_sizes, tmp_path, monkeypatch):
    # Interactive mode prompts per repo, so it must stay sequential even with --jobs.
    _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "")
    cmd_push({"github": {"r": None}}, tmp_path, mode="interactive", jobs=4)
    assert pool_sizes == []


# ── status --json ────────────────────────────────────────────────────────────

def test_status_json_lists_dirty_repos(capsys, tmp_path):
    d = _make_clone(tmp_path)
    (d / "init").write_text("edited")
    (d / "a.txt").write_text("a")
    (d / "b.txt").write_text("b")

    cmd_status({"github": {"r": None}}, tmp_path, json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload == [{"platform": "github", "path": "r", "changed_files": 3}]


def test_status_json_empty_when_clean(capsys, tmp_path):
    _make_clone(tmp_path)
    cmd_status({"github": {"r": None}}, tmp_path, json_output=True)
    assert json.loads(capsys.readouterr().out) == []


def test_status_json_omits_clean_repos(capsys, tmp_path):
    _make_clone(tmp_path)
    dirty = tmp_path / "github" / "other"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(dirty)],
                   check=True, capture_output=True)
    (dirty / "x.txt").write_text("x")

    cmd_status({"github": {"r": None, "other": None}}, tmp_path, json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload == [{"platform": "github", "path": "other", "changed_files": 1}]


def test_status_default_output_unchanged(capsys, tmp_path):
    d = _make_clone(tmp_path)
    (d / "dirty.txt").write_text("x")

    cmd_status({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out

    assert "github/r" in out
    assert "dirty.txt" in out
    assert out.strip()[0] != "["
    with pytest.raises(ValueError):
        json.loads(out)


def test_status_default_clean_message(capsys, tmp_path):
    _make_clone(tmp_path)
    cmd_status({"github": {"r": None}}, tmp_path)
    assert "All repos are clean." in capsys.readouterr().out


# ── --only platform filter ───────────────────────────────────────────────────

def _gitlab_clone(tmp_path, name="gl", commit=True):
    d = tmp_path / "gitlab" / name
    d.parent.mkdir()
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(d)],
                   check=True, capture_output=True)
    if commit:
        _commit(d, "seed")
        _git(d, "push", "-q", "origin", "HEAD:main")
    return d


def test_status_only_limits_to_platform(capsys, tmp_path):
    github = _make_clone(tmp_path)
    (github / "x.txt").write_text("x")
    _gitlab_clone(tmp_path)
    (tmp_path / "gitlab" / "gl" / "y.txt").write_text("y")

    cmd_status({"github": {"r": None}, "gitlab": {"gl": None}}, tmp_path, only="github")

    out = capsys.readouterr().out
    assert "github/r" in out
    assert "gitlab/gl" not in out


def test_status_only_json(capsys, tmp_path):
    github = _make_clone(tmp_path)
    (github / "x.txt").write_text("x")
    _gitlab_clone(tmp_path)
    (tmp_path / "gitlab" / "gl" / "y.txt").write_text("y")

    cmd_status({"github": {"r": None}, "gitlab": {"gl": None}}, tmp_path,
               json_output=True, only="github")

    assert json.loads(capsys.readouterr().out) == [
        {"platform": "github", "path": "r", "changed_files": 1}
    ]


def test_pull_only_limits_to_platform(capsys, tmp_path):
    _make_clone(tmp_path, ahead=2)
    _gitlab_clone(tmp_path)
    _commit(tmp_path / "gitlab" / "gl", "ahead")
    _git(tmp_path / "gitlab" / "gl", "push", "-q", "origin", "HEAD:main")

    cmd_pull({"github": {"r": None}, "gitlab": {"gl": None}}, tmp_path,
             dry_run=True, only="github")

    out = capsys.readouterr().out
    assert "github/r" in out
    assert "gitlab/gl" not in out


def test_push_only_limits_to_platform(capsys, tmp_path):
    github = _make_clone(tmp_path)
    (github / "g.txt").write_text("x")
    _gitlab_clone(tmp_path)
    (tmp_path / "gitlab" / "gl" / "l.txt").write_text("x")

    cmd_push({"github": {"r": None}, "gitlab": {"gl": None}}, tmp_path,
             dry_run=True, only="github")

    out = capsys.readouterr().out
    assert "github/r" in out
    assert "gitlab/gl" not in out


def test_status_unknown_platform_errors(capsys, tmp_path, monkeypatch):
    import sys
    from polygit.cli import main

    _make_clone(tmp_path)
    (tmp_path / ".pgit").write_text("github:\n  r:\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["pgit", "status", "--only", "bitbucket"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "bitbucket" in err
    assert "github" in err
