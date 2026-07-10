import yaml
from pathlib import Path

HOSTS = {
    "github": "git@github.com",
    "gitlab": "git@gitlab.com",
}

CONFIG_FILE = ".pgit"


def find_config(start=None):
    """Walk up from start (default: cwd) to find a .pgit config file."""
    current = Path(start or Path.cwd())
    for path in [current] + list(current.parents):
        candidate = path / CONFIG_FILE
        if candidate.exists():
            return candidate
    return None


def load_config(path):
    """Load and return the .pgit YAML config."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_config(data, path):
    """Write .pgit config using only stdlib — preserves null and inline-remote styles."""
    def _lines(node, indent):
        prefix = "  " * indent
        out = []
        for key, value in node.items():
            if value is None:
                out.append(f"{prefix}{key}:")
            elif isinstance(value, dict) and set(value.keys()) == {"remote"}:
                out.append(f'{prefix}{key}: {{remote: "{value["remote"]}"}}'  )
            elif isinstance(value, dict):
                out.append(f"{prefix}{key}:")
                out.extend(_lines(value, indent + 1))
            else:
                out.append(f"{prefix}{key}: {value}")
        return out

    with open(path, "w") as f:
        f.write("\n".join(_lines(data, 0)) + "\n")
