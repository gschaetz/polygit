import sys
import argparse
from importlib.metadata import version
from .config import find_config, load_config, HOSTS
from .repo import cmd_sync, cmd_status, cmd_pull, cmd_push, cmd_branches, cmd_commit, cmd_merge, cmd_review, cmd_checkout, valid_branch_name
from .repos import cmd_repos


def _positive_int(value):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {n}")
    return n


def _add_jobs(subparser):
    subparser.add_argument("--jobs", type=_positive_int, default=None, metavar="N",
                           help="Number of repos to process in parallel (default: 8)")


def main():
    parser = argparse.ArgumentParser(
        prog="pgit",
        description="Manage multiple git repos defined in a .pgit config file."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('polygit')}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    sync_p = sub.add_parser("sync",   help="Clone missing repos and fetch all")
    _add_jobs(sync_p)
    status_p = sub.add_parser("status", help="Show repos with uncommitted changes")
    status_p.add_argument("--json", action="store_true",
                          help="Print dirty repos as a JSON list")
    status_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(status_p)
    pull_p = sub.add_parser("pull",   help="Pull all repos, auto-stashing local changes")
    pull_p.add_argument("--dry-run", action="store_true",
                        help="Show ahead/behind vs. last-fetched upstream; changes nothing")
    pull_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(pull_p)

    push_p = sub.add_parser("push", help="Commit and push dirty repos")
    mode_g = push_p.add_mutually_exclusive_group()
    mode_g.add_argument("--interactive", dest="push_mode", action="store_const",
                        const="interactive", help="Prompt per repo (default)")
    mode_g.add_argument("--all", dest="push_mode", action="store_const",
                        const="all", help="One commit message for all dirty repos")
    mode_g.add_argument("--wip", dest="push_mode", action="store_const",
                        const="wip", help='Auto-commit with "WIP <timestamp>"')
    push_p.set_defaults(push_mode="interactive")
    push_p.add_argument("--dry-run", action="store_true",
                        help="Show the commit/push plan without committing or pushing")
    push_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(push_p)

    commit_p = sub.add_parser("commit", help="Commit dirty repos (without pushing)")
    commit_mode_g = commit_p.add_mutually_exclusive_group()
    commit_mode_g.add_argument("--interactive", dest="commit_mode", action="store_const",
                               const="interactive", help="Prompt per repo (default)")
    commit_mode_g.add_argument("--all", dest="commit_mode", action="store_const",
                               const="all", help="One commit message for all dirty repos")
    commit_mode_g.add_argument("--wip", dest="commit_mode", action="store_const",
                               const="wip", help='Auto-commit with "WIP <timestamp>"')
    commit_p.set_defaults(commit_mode="interactive")
    commit_p.add_argument("--dry-run", action="store_true",
                          help="Show the commit plan without committing")
    commit_p.add_argument("--json", action="store_true",
                          help="Print commit results as a JSON list")
    commit_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(commit_p)

    merge_p = sub.add_parser("merge", help="Merge a target branch into each repo's current branch")
    merge_p.add_argument("target", metavar="BRANCH", help="Branch to merge in (e.g. main)")
    merge_strategy = merge_p.add_mutually_exclusive_group()
    merge_strategy.add_argument("--no-ff", action="store_true", help="Force a merge commit")
    merge_strategy.add_argument("--squash", action="store_true", help="Stage the merged changes without committing")
    merge_p.add_argument("--dry-run", action="store_true", help="Show what would happen without changing repos")
    merge_p.add_argument("--json", action="store_true", help="Print merge results as a JSON list")
    merge_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(merge_p)

    review_p = sub.add_parser("review", help="Open PRs for pushed branches ahead of the default branch")
    review_mode_g = review_p.add_mutually_exclusive_group()
    review_mode_g.add_argument("--all", dest="review_mode", action="store_const",
                               const="all", help="One PR title/body for all eligible repos")
    review_mode_g.add_argument("--auto", dest="review_mode", action="store_const",
                               const="auto", help='Auto-generate PR title from branch name')
    review_p.set_defaults(review_mode="interactive")
    review_p.add_argument("--base", dest="review_base", metavar="BRANCH",
                          help="Base branch for the PR (default: remote default)")
    review_p.add_argument("--dry-run", action="store_true",
                          help="Show what would be reviewed without creating PRs")
    review_p.add_argument("--json", action="store_true",
                          help="Print review results as a JSON list")
    review_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(review_p)

    checkout_p = sub.add_parser("checkout", help="Switch every repo to a branch, or create it with -b")
    checkout_p.add_argument("branch", metavar="BRANCH", help="Local branch to switch to (or create with -b)")
    checkout_p.add_argument("-b", dest="create", action="store_true", help="Create the branch instead of switching to it")
    checkout_p.add_argument("--from", dest="start", metavar="REF",
                            help="With -b, create the branch at this ref instead of the current HEAD")
    checkout_p.add_argument("--dry-run", action="store_true", help="Show what would happen without changing repos")
    checkout_p.add_argument("--json", action="store_true", help="Print checkout results as a JSON list")
    checkout_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(checkout_p)

    branches_p = sub.add_parser("branches", help="Show current branch and tracking status per repo (as of last fetch)")
    branches_p.add_argument("--json", action="store_true",
                            help="Print branch status for every repo as a JSON list")
    branches_p.add_argument("--only", dest="only_platform", help="Limit to a single platform (e.g. github)")
    _add_jobs(branches_p)

    sub.add_parser("repos", help="Discover drift between .pgit and the filesystem")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Reject --json in interactive commit mode (before config lookup)
    if args.command == "commit" and getattr(args, "json", False) and getattr(args, "commit_mode", None) == "interactive":
        print("Error: --json requires --all or --wip.", file=sys.stderr)
        sys.exit(2)

    # Reject --json in interactive review mode (before config lookup)
    if args.command == "review" and getattr(args, "json", False) and getattr(args, "review_mode", None) == "interactive":
        print("Error: --json requires --all or --auto.", file=sys.stderr)
        sys.exit(2)

    # Reject bad checkout arguments (before config lookup)
    if args.command == "checkout":
        if args.start and not args.create:
            print("Error: --from requires -b.", file=sys.stderr)
            sys.exit(2)
        if not valid_branch_name(args.branch):
            print(f"Error: '{args.branch}' is not a valid branch name.", file=sys.stderr)
            sys.exit(2)

    config_path = find_config()
    if config_path is None:
        print("Error: no .pgit config file found in this directory or any parent.", file=sys.stderr)
        print("Create a .pgit file in your repos root directory.", file=sys.stderr)
        sys.exit(1)

    base   = config_path.parent
    config = load_config(config_path)

    only_platform = getattr(args, "only_platform", None)
    if only_platform is not None and only_platform not in HOSTS:
        print(f"Error: unknown platform '{only_platform}'. "
              f"Available: {', '.join(sorted(HOSTS))}", file=sys.stderr)
        sys.exit(1)

    jobs = getattr(args, "jobs", None)

    commands = {
        "sync":     lambda: cmd_sync(config, base, jobs=jobs),
        "status":   lambda: cmd_status(config, base, json_output=args.json, only=only_platform, jobs=jobs),
        "pull":     lambda: cmd_pull(config, base, dry_run=args.dry_run, only=only_platform, jobs=jobs),
        "push":     lambda: cmd_push(config, base, mode=args.push_mode, dry_run=args.dry_run, only=only_platform, jobs=jobs),
        "commit":   lambda: cmd_commit(config, base, mode=args.commit_mode, dry_run=args.dry_run, only=only_platform, jobs=jobs, json_output=args.json),
        "merge":    lambda: cmd_merge(config, base, args.target, no_ff=args.no_ff, squash=args.squash, dry_run=args.dry_run, only=only_platform, jobs=jobs, json_output=args.json),
        "review":   lambda: cmd_review(config, base, mode=args.review_mode, base_branch=args.review_base, dry_run=args.dry_run, only=only_platform, jobs=jobs, json_output=args.json),
        "checkout": lambda: cmd_checkout(config, base, args.branch, create=args.create, start=args.start, dry_run=args.dry_run, only=only_platform, jobs=jobs, json_output=args.json),
        "branches": lambda: cmd_branches(config, base, json_output=args.json, only=only_platform, jobs=jobs),
        "repos":    lambda: cmd_repos(config, base, config_path),
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
