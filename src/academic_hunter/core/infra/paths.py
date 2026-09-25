import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_ENV = "ACADEMIC_HUNTER_CONFIG"
DATA_ENV = "ACADEMIC_HUNTER_DATA_DIR"
PROJECT_ENV = "CLAUDE_PROJECT_DIR"

CONFIG_FILENAME = "config.json"
DATA_DIRNAME = ".academic_hunter"
RESULTS_DIRNAME = "results"
PACKAGED_DEFAULT = "config.default.json"
APP_DIRNAME = "academic-hunter"

ORIGIN_ENV = "env"
ORIGIN_CWD = "cwd"
ORIGIN_CLAUDE_PROJECT = "claude_project_dir"
ORIGIN_USER_CONFIG = "user_config"
ORIGIN_CHECKOUT = "checkout"
ORIGIN_PACKAGED = "packaged_default"
ORIGIN_USER_DATA = "user_data"
ORIGIN_EXPLICIT = "explicit"

ORIGINS = (
    ORIGIN_ENV,
    ORIGIN_CWD,
    ORIGIN_CLAUDE_PROJECT,
    ORIGIN_USER_CONFIG,
    ORIGIN_CHECKOUT,
    ORIGIN_PACKAGED,
    ORIGIN_USER_DATA,
    ORIGIN_EXPLICIT,
)


@dataclass(frozen=True)
class Resolution:
    path: Path
    origin: str

    @property
    def is_default(self) -> bool:
        return self.origin == ORIGIN_PACKAGED


@dataclass(frozen=True)
class Location:
    base: Path
    data_dir: Path
    results_dir: Path
    origin: str

    @classmethod
    def of(cls, base: Path, origin: str) -> "Location":
        return cls(
            base=base,
            data_dir=base / DATA_DIRNAME,
            results_dir=base / RESULTS_DIRNAME,
            origin=origin,
        )

    @property
    def history_db(self) -> Path:
        return self.data_dir / "mcp_history.db"


def _xdg(env_var: str, fallback: str) -> Path:
    value = os.environ.get(env_var, "")
    if value and os.path.isabs(value):
        return Path(value)
    return Path(fallback).expanduser()


def user_config_file() -> Path:
    return _xdg("XDG_CONFIG_HOME", "~/.config") / APP_DIRNAME / CONFIG_FILENAME


def user_data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", "~/.local/share") / APP_DIRNAME


def checkout_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def project_marker(directory: Path) -> bool:
    return (directory / DATA_DIRNAME).is_dir() or (directory / CONFIG_FILENAME).is_file()


def packaged_default_path() -> Path:
    return Path(__file__).resolve().parent / PACKAGED_DEFAULT


def is_inside_package(path: Path) -> bool:
    try:
        return path.resolve() == packaged_default_path().resolve()
    except OSError:
        return False


def resolve_config_path() -> Resolution:
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"{CONFIG_ENV} is set to '{path}', which is not a file. "
                "Point it at a readable config, or unset it to use the search order."
            )
        return Resolution(path, ORIGIN_ENV)

    cwd = Path.cwd()
    for candidate in (cwd / CONFIG_FILENAME, cwd / DATA_DIRNAME / CONFIG_FILENAME):
        if candidate.is_file():
            return Resolution(candidate, ORIGIN_CWD)

    project = os.environ.get(PROJECT_ENV)
    if project:
        candidate = Path(project).expanduser() / CONFIG_FILENAME
        if candidate.is_file():
            return Resolution(candidate, ORIGIN_CLAUDE_PROJECT)

    user = user_config_file()
    if user.is_file():
        return Resolution(user, ORIGIN_USER_CONFIG)

    checkout = checkout_root()
    if checkout is not None:
        candidate = checkout / CONFIG_FILENAME
        if candidate.is_file():
            return Resolution(candidate, ORIGIN_CHECKOUT)

    return Resolution(packaged_default_path(), ORIGIN_PACKAGED)


def resolve_location() -> Location:
    explicit = os.environ.get(DATA_ENV)
    if explicit:
        base = Path(explicit).expanduser()
        if base.exists() and not base.is_dir():
            raise NotADirectoryError(
                f"{DATA_ENV} is set to '{base}', which is a file. It names the "
                "project directory that holds .academic_hunter and results, "
                "not a file inside it."
            )
        return Location.of(base, ORIGIN_ENV)

    cwd = Path.cwd()
    if project_marker(cwd):
        return Location.of(cwd, ORIGIN_CWD)

    project = os.environ.get(PROJECT_ENV)
    if project:
        base = Path(project).expanduser()
        if project_marker(base):
            return Location.of(base, ORIGIN_CLAUDE_PROJECT)

    checkout = checkout_root()
    if checkout is not None:
        return Location.of(checkout, ORIGIN_CHECKOUT)

    return Location.of(user_data_dir(), ORIGIN_USER_DATA)


def ensure_data_dir() -> Path:
    data_dir = resolve_location().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def describe() -> dict:
    described: dict = {}
    for name, resolver in (("config", resolve_config_path), ("data", resolve_location)):
        try:
            found = resolver()
        except Exception as exc:
            described[name] = {"error": str(exc)}
            continue
        if isinstance(found, Location):
            described[name] = {
                "path": str(found.base),
                "data_dir": str(found.data_dir),
                "results_dir": str(found.results_dir),
                "origin": found.origin,
            }
        else:
            described[name] = {
                "path": str(found.path),
                "origin": found.origin,
                "is_default": found.is_default,
            }
    return described
