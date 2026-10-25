import sys
import argparse
from .config import find_config, load_config, HOSTS
from .repo import cmd_sync, cmd_status, cmd_pull, cmd_push
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

    sub.add_parser("repos", help="Discover drift between .pgit and the filesystem")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

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
        "sync":   lambda: cmd_sync(config, base, jobs=jobs),
        "status": lambda: cmd_status(config, base, json_output=args.json, only=only_platform, jobs=jobs),
        "pull":   lambda: cmd_pull(config, base, dry_run=args.dry_run, only=only_platform, jobs=jobs),
        "push":   lambda: cmd_push(config, base, mode=args.push_mode, dry_run=args.dry_run, only=only_platform, jobs=jobs),
        "repos":  lambda: cmd_repos(config, base, config_path),
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
