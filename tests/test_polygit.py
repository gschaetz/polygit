import json
import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from polygit.config import find_config, load_config, write_config
from polygit.repos import parse_remote_url, del_nested, _add_to_config
from polygit.repo import walk, _pull_one, cmd_push, cmd_status, cmd_pull, cmd_sync, cmd_branches, cmd_commit, cmd_merge


@pytest.fixture(autouse=True)
def _isolated_git_config(monkeypatch):
    """Keep the developer's global git config (e.g. merge.ff=only) out of the tests."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


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


# ── branches ──────────────────────────────────────────────────────────────────

def _make_repo_with_branch(tmp_path, branch="main", ahead=0, behind=0, upstream=True):
    """Create a repo with optional branch, ahead/behind commits, and upstream tracking."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True, capture_output=True)
    _commit(seed, "init")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    d = tmp_path / "github" / "r"
    d.parent.mkdir()
    subprocess.run(["git", "clone", "-q", str(origin), str(d)], check=True, capture_output=True)
    # Add behind commits
    for i in range(behind):
        _commit(seed, f"b{i}")
    if behind:
        _git(seed, "push", "-q", "origin", "HEAD:main")
        _git(d, "fetch", "-q")
    # Create/switch to branch
    if branch != "main":
        _git(d, "checkout", "-q", "-b", branch)
    # Add ahead commits
    for i in range(ahead):
        _commit(d, f"a{i}")
    # Set upstream if requested
    if upstream and branch != "main":
        _git(d, "branch", "-u", f"origin/{branch}")
    if not upstream:
        _git(d, "branch", "--unset-upstream")
    return d


def _git_out_for_test(d):
    return subprocess.run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_branches_up_to_date(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path)
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "main -> origin/main" in out
    assert "(up to date)" in out


def test_branches_ahead(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path, ahead=2)
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "2 ahead" in out
    assert "↑" in out
    assert "↓" not in out


def test_branches_behind(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path, behind=3)
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "3 behind" in out
    assert "↓" in out


def test_branches_ahead_and_behind(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path, ahead=1, behind=2)
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "1 ahead" in out
    assert "2 behind" in out
    assert "⚠" in out


def test_branches_no_upstream(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path, upstream=False)
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "(no upstream)" in out


def test_branches_non_default_branch_with_upstream(capsys, tmp_path):
    _make_repo_with_branch(tmp_path)
    d = tmp_path / "github" / "r"
    _git(d, "checkout", "-q", "-b", "feat")
    _commit(d, "f1")
    _git(d, "push", "-q", "-u", "origin", "feat")
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "feat -> origin/feat (up to date)" in out


def test_branches_upstream_gone(capsys, tmp_path):
    _make_repo_with_branch(tmp_path)
    d = tmp_path / "github" / "r"
    _git(d, "checkout", "-q", "-b", "feat")
    _commit(d, "f1")
    _git(d, "push", "-q", "-u", "origin", "feat")
    _git(d, "push", "-q", "origin", ":feat")
    _git(d, "fetch", "-q", "--prune")
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "feat -> origin/feat (upstream gone)" in out
    assert "no upstream" not in out


def test_branches_detached_head(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path)
    # Detach HEAD
    _git(d, "checkout", "-q", "HEAD~0")
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    sha = _git_out_for_test(d)
    assert f"detached HEAD at {sha}" in out


def test_branches_empty_repo(capsys, tmp_path):
    d = tmp_path / "github" / "r"
    d.parent.mkdir()
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    cmd_branches({"github": {"r": None}}, tmp_path)
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "(no upstream)" in out


def test_branches_json_lists_every_repo(capsys, tmp_path):
    _make_repo_with_branch(tmp_path, ahead=2, behind=1)
    cmd_branches({"github": {"r": None}}, tmp_path, json_output=True)
    payload = json.loads(capsys.readouterr().out)
    assert payload == [{
        "platform": "github", "path": "r", "branch": "main", "sha": None,
        "upstream": "origin/main", "ahead": 2, "behind": 1, "state": "tracking",
    }]


def test_branches_json_detached_has_sha_and_no_branch(capsys, tmp_path):
    d = _make_repo_with_branch(tmp_path)
    _git(d, "checkout", "-q", "--detach")
    cmd_branches({"github": {"r": None}}, tmp_path, json_output=True)
    [entry] = json.loads(capsys.readouterr().out)
    assert entry["state"] == "detached"
    assert entry["branch"] is None
    assert entry["sha"] == _git_out_for_test(d)


def test_branches_json_no_repos_is_empty_list(capsys, tmp_path):
    cmd_branches({"github": {"r": None}}, tmp_path, json_output=True)
    assert json.loads(capsys.readouterr().out) == []


def test_branches_only_limits_to_platform(capsys, tmp_path):
    github = _make_repo_with_branch(tmp_path)
    _gitlab_clone(tmp_path)
    cmd_branches({"github": {"r": None}, "gitlab": {"gl": None}}, tmp_path, only="github")
    out = capsys.readouterr().out
    assert "github/r" in out
    assert "gitlab/gl" not in out


def test_branches_uses_jobs(pool_sizes, tmp_path):
    _make_repo_with_branch(tmp_path)
    cmd_branches({"github": {"r": None}}, tmp_path, jobs=3)
    assert pool_sizes == [3]


def test_branches_default_pool_size_is_max_workers(pool_sizes, tmp_path):
    from polygit.repo import MAX_WORKERS
    _make_repo_with_branch(tmp_path)
    cmd_branches({"github": {"r": None}}, tmp_path)
    assert pool_sizes == [MAX_WORKERS]


# ── commit ───────────────────────────────────────────────────────────────────

CFG = {"github": {"r": None}}


def _head(d):
    return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _commit_count(d):
    return len(subprocess.run(["git", "-C", str(d), "log", "--oneline"],
                              capture_output=True, text=True).stdout.splitlines())


def test_commit_nothing_dirty(capsys, tmp_path):
    _make_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip")
    assert "No dirty repos to commit." in capsys.readouterr().out


def test_commit_wip_commits_without_pushing(capsys, tmp_path):
    d = _dirty_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip")
    assert "committed" in capsys.readouterr().out
    assert _commit_count(d) == 2
    assert not is_dirty_for_test(d)
    ahead = subprocess.run(["git", "-C", str(d), "rev-list", "--count", "@{u}..HEAD"],
                           capture_output=True, text=True).stdout.strip()
    assert ahead == "1"


def is_dirty_for_test(d):
    from polygit.repo import is_dirty
    return is_dirty(d)


def test_commit_all_uses_one_message(tmp_path, monkeypatch):
    d = _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "shared msg")
    cmd_commit(CFG, tmp_path, mode="all")
    msg = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    assert msg == "shared msg"


def test_commit_all_blank_aborts(capsys, tmp_path, monkeypatch):
    d = _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    cmd_commit(CFG, tmp_path, mode="all")
    assert "Aborted." in capsys.readouterr().out
    assert _commit_count(d) == 1


def test_commit_interactive_blank_skips(capsys, tmp_path, monkeypatch):
    d = _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    cmd_commit(CFG, tmp_path, mode="interactive")
    assert "Skipped." in capsys.readouterr().out
    assert _commit_count(d) == 1


def test_commit_interactive_commits(tmp_path, monkeypatch):
    d = _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "by hand")
    cmd_commit(CFG, tmp_path, mode="interactive")
    assert _commit_count(d) == 2


def test_commit_includes_untracked_files(tmp_path):
    d = _dirty_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip")
    tracked = subprocess.run(["git", "-C", str(d), "ls-files"],
                             capture_output=True, text=True).stdout.split()
    assert "x.txt" in tracked


def test_commit_hook_failure_reports_commit_failed(capsys, tmp_path):
    d = _dirty_clone(tmp_path)
    hook = d / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'hook says no'\nexit 1\n")
    hook.chmod(0o755)
    cmd_commit(CFG, tmp_path, mode="wip")
    assert "commit failed" in capsys.readouterr().out
    assert _commit_count(d) == 1


def test_commit_dry_run_changes_nothing(capsys, tmp_path):
    d = _dirty_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip", dry_run=True)
    assert "github/r" in capsys.readouterr().out
    assert _commit_count(d) == 1
    assert (d / "x.txt").exists()


def test_commit_wip_uses_jobs(pool_sizes, tmp_path):
    _dirty_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip", jobs=3)
    assert pool_sizes == [3]


def test_commit_json(capsys, tmp_path):
    d = _dirty_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip", json_output=True)
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 1
    assert out[0]["status"] == "committed"
    assert out[0]["platform"] == "github" and out[0]["path"] == "r"
    assert out[0]["message"].startswith("WIP ")
    assert _head(d).startswith(out[0]["sha"])


def test_commit_json_failure_has_error(capsys, tmp_path):
    d = _dirty_clone(tmp_path)
    hook = d / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'hook says no'\nexit 1\n")
    hook.chmod(0o755)
    cmd_commit(CFG, tmp_path, mode="wip", json_output=True)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["status"] == "failed"
    assert "commit failed" in out[0]["error"]


def test_commit_json_empty(capsys, tmp_path):
    _make_clone(tmp_path)
    cmd_commit(CFG, tmp_path, mode="wip", json_output=True)
    assert json.loads(capsys.readouterr().out) == []


def test_commit_json_all_keeps_stdout_clean(capsys, tmp_path, monkeypatch):
    _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "msg")
    cmd_commit(CFG, tmp_path, mode="all", json_output=True)
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["message"] == "msg"
    assert "Commit message" in captured.err


def test_commit_json_all_abort_prints_empty_array(capsys, tmp_path, monkeypatch):
    _dirty_clone(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    cmd_commit(CFG, tmp_path, mode="all", json_output=True)
    assert json.loads(capsys.readouterr().out) == []


def test_commit_json_interactive_is_usage_error(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .pgit: must fail before config lookup
    assert _run_main(monkeypatch, "commit", "--json") == 2
    assert "--json requires --all or --wip" in capsys.readouterr().err


def test_push_wip_still_commits_and_pushes(capsys, tmp_path):
    d = _dirty_clone(tmp_path)
    cmd_push(CFG, tmp_path, mode="wip")
    assert "pushed" in capsys.readouterr().out
    ahead = subprocess.run(["git", "-C", str(d), "rev-list", "--count", "@{u}..HEAD"],
                           capture_output=True, text=True).stdout.strip()
    assert ahead == "0"


# ── merge ────────────────────────────────────────────────────────────────────

def _merge_repo(tmp_path):
    """Clone on `feature`, with `main` one commit ahead of where feature branched."""
    d = _make_clone(tmp_path)
    _git(d, "checkout", "-qb", "feature")
    _git(d, "checkout", "-q", "main")
    _commit(d, "m1")
    _git(d, "checkout", "-q", "feature")
    return d


def _merge_json(capsys, tmp_path, *args, **kw):
    cmd_merge(CFG, tmp_path, "main", *args, json_output=True, **kw)
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 1
    return out[0]


def test_merge_fast_forward(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    cmd_merge(CFG, tmp_path, "main")
    assert "merged (fast-forward)" in capsys.readouterr().out
    assert _head(d) == _git_rev(d, "main")


def _git_rev(d, ref):
    return subprocess.run(["git", "-C", str(d), "rev-parse", ref],
                          capture_output=True, text=True).stdout.strip()


def test_merge_commit_when_diverged(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    _commit(d, "f1")
    cmd_merge(CFG, tmp_path, "main")
    assert "merged (commit " in capsys.readouterr().out
    parents = subprocess.run(["git", "-C", str(d), "rev-list", "--parents", "-n", "1", "HEAD"],
                             capture_output=True, text=True).stdout.split()
    assert len(parents) == 3


def test_merge_no_ff_creates_merge_commit(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    cmd_merge(CFG, tmp_path, "main", no_ff=True)
    assert "merged (commit " in capsys.readouterr().out
    parents = subprocess.run(["git", "-C", str(d), "rev-list", "--parents", "-n", "1", "HEAD"],
                             capture_output=True, text=True).stdout.split()
    assert len(parents) == 3


def test_merge_squash_stages_without_committing(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    before = _head(d)
    cmd_merge(CFG, tmp_path, "main", squash=True)
    assert "squashed (staged)" in capsys.readouterr().out
    assert _head(d) == before
    staged = subprocess.run(["git", "-C", str(d), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True).stdout.split()
    assert "m1" in staged


def test_merge_squash_json_status_is_merged(capsys, tmp_path):
    _merge_repo(tmp_path)
    entry = _merge_json(capsys, tmp_path, squash=True)
    assert entry["status"] == "merged" and entry["strategy"] == "squash"


def test_merge_conflict_reports_files_and_leaves_state(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _git(d, "checkout", "-qb", "feature")
    _git(d, "checkout", "-q", "main")
    (d / "init").write_text("main side")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qam", "m")
    _git(d, "checkout", "-q", "feature")
    (d / "init").write_text("feature side")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qam", "f")
    cmd_merge(CFG, tmp_path, "main")
    assert "conflict: 1 file(s)" in capsys.readouterr().out
    merging = subprocess.run(["git", "-C", str(d), "rev-parse", "-q", "--verify", "MERGE_HEAD"],
                             capture_output=True)
    assert merging.returncode == 0


def test_merge_conflict_json_lists_files(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _git(d, "checkout", "-qb", "feature")
    _git(d, "checkout", "-q", "main")
    (d / "init").write_text("main side")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qam", "m")
    _git(d, "checkout", "-q", "feature")
    (d / "init").write_text("feature side")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qam", "f")
    entry = _merge_json(capsys, tmp_path)
    assert entry["status"] == "conflict"
    assert entry["conflict_files"] == ["init"]


def test_merge_up_to_date(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _git(d, "checkout", "-qb", "feature")
    cmd_merge(CFG, tmp_path, "main")
    assert "up to date" in capsys.readouterr().out


def test_merge_target_equals_current_is_up_to_date(capsys, tmp_path):
    _make_clone(tmp_path)  # on main
    cmd_merge(CFG, tmp_path, "main")
    assert "up to date" in capsys.readouterr().out


def test_merge_detached_head_skipped(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    _git(d, "checkout", "-q", "--detach")
    cmd_merge(CFG, tmp_path, "main")
    assert "skipped: detached HEAD" in capsys.readouterr().out


def test_merge_missing_target_skipped(capsys, tmp_path):
    _make_clone(tmp_path)
    cmd_merge(CFG, tmp_path, "nope")
    assert "skipped: target branch 'nope' not found" in capsys.readouterr().out


def test_merge_remote_only_branch_is_not_local(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _git(d, "checkout", "-qb", "feature")
    cmd_merge(CFG, tmp_path, "origin/main")
    assert "not found" in capsys.readouterr().out


def test_merge_dirty_tree_skipped(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    (d / "wip.txt").write_text("x")
    before = _head(d)
    cmd_merge(CFG, tmp_path, "main")
    assert "skipped: dirty working tree" in capsys.readouterr().out
    assert _head(d) == before


def test_merge_in_progress_skipped(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _git(d, "checkout", "-qb", "feature")
    _git(d, "checkout", "-q", "main")
    (d / "init").write_text("m")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qam", "m")
    _git(d, "checkout", "-q", "feature")
    (d / "init").write_text("f")
    _git(d, "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-qam", "f")
    subprocess.run(["git", "-C", str(d), "merge", "main"], capture_output=True)
    cmd_merge(CFG, tmp_path, "main")
    assert "skipped: merge in progress" in capsys.readouterr().out


def test_merge_other_git_error_is_failed(capsys, tmp_path):
    d = _make_clone(tmp_path)
    _git(d, "checkout", "--orphan", "other")
    _git(d, "rm", "-rqf", ".")
    _commit(d, "unrelated")
    _git(d, "checkout", "-q", "main")
    entry = _merge_json_for(capsys, tmp_path, "other")
    assert entry["status"] == "failed"
    assert "unrelated histories" in entry["detail"]


def _merge_json_for(capsys, tmp_path, target):
    cmd_merge(CFG, tmp_path, target, json_output=True)
    return json.loads(capsys.readouterr().out)[0]


def test_merge_dry_run_changes_nothing(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    before = _head(d)
    cmd_merge(CFG, tmp_path, "main", dry_run=True)
    assert "would merge" in capsys.readouterr().out
    assert _head(d) == before
    assert not (d / "m1").exists()


def test_merge_dry_run_reports_skips(capsys, tmp_path):
    d = _merge_repo(tmp_path)
    (d / "wip.txt").write_text("x")
    cmd_merge(CFG, tmp_path, "main", dry_run=True)
    assert "skipped: dirty working tree" in capsys.readouterr().out


def test_merge_dry_run_json_uses_planned(capsys, tmp_path):
    _merge_repo(tmp_path)
    entry = _merge_json(capsys, tmp_path, dry_run=True)
    assert entry["status"] == "planned"


def test_merge_json_shape(capsys, tmp_path):
    _merge_repo(tmp_path)
    entry = _merge_json(capsys, tmp_path)
    assert entry == {"platform": "github", "path": "r", "status": "merged",
                     "strategy": "default", "detail": "fast-forward"}


def test_merge_json_empty(capsys, tmp_path):
    cmd_merge({}, tmp_path, "main", json_output=True)
    assert json.loads(capsys.readouterr().out) == []


def test_merge_uses_jobs(pool_sizes, tmp_path):
    _merge_repo(tmp_path)
    cmd_merge(CFG, tmp_path, "main", jobs=4)
    assert pool_sizes == [4]


def test_merge_requires_branch_argument(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _run_main(monkeypatch, "merge") == 2


def test_merge_no_ff_and_squash_are_exclusive(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _run_main(monkeypatch, "merge", "main", "--no-ff", "--squash") == 2
