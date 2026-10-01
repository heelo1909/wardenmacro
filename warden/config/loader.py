"""Load, validate and save YAML config with human-readable errors."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from warden import paths
from warden.config.schema import AppConfig, Preset


class ConfigError(Exception):
    """A config file could not be read or failed validation.

    ``str(err)`` is meant to be shown to the user as-is.
    """

    def __init__(self, source: Path | str, problems: list[str]):
        self.source = str(source)
        self.problems = problems
        body = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"Problem(s) in {self.source}:\n{body}")


def _format_validation(err: ValidationError) -> list[str]:
    problems = []
    for item in err.errors():
        where = ".".join(str(part) for part in item["loc"]) or "(top level)"
        msg = item["msg"].removeprefix("Value error, ")
        if item["type"] == "extra_forbidden":
            msg = "unknown setting (typo?)"
        elif item["type"] == "missing":
            msg = "required setting is missing"
        problems.append(f"{where}: {msg}")
    return problems


def _read_yaml(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(path, ["file not found"]) from None
    except OSError as exc:
        raise ConfigError(path, [f"cannot read file: {exc}"]) from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError(path, [f"{where}invalid YAML ({problem})"]) from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(path, ["top level must be a mapping of settings"])
    return data


def _validate(model: type[BaseModel], data: dict, source: Path | str):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(source, _format_validation(exc)) from None


def load_app_config(path: Path) -> AppConfig:
    return _validate(AppConfig, _read_yaml(Path(path)), path)


def load_preset(path: Path) -> Preset:
    return _validate(Preset, _read_yaml(Path(path)), path)


def save_model(model: BaseModel, path: Path) -> None:
    """Write YAML atomically (temp file + rename) so a crash never leaves half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = model.model_dump(mode="json", exclude_none=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- user data folder


def user_config_path() -> Path:
    return paths.data_home() / "config.yaml"


def user_presets_dir() -> Path:
    return paths.data_home() / "presets"


def seed_user_config() -> None:
    """First run: copy bundled defaults into the user data folder. Never overwrites."""
    home = paths.data_home()
    home.mkdir(parents=True, exist_ok=True)
    bundled = paths.bundled_config_dir()
    if not user_config_path().exists():
        shutil.copyfile(bundled / "default.yaml", user_config_path())
    presets = user_presets_dir()
    presets.mkdir(exist_ok=True)
    for src in (bundled / "presets").glob("*.yaml"):
        dst = presets / src.name
        if not dst.exists():
            shutil.copyfile(src, dst)


def list_presets(directory: Path | None = None) -> dict[str, Path]:
    directory = directory or user_presets_dir()
    return {p.stem: p for p in sorted(Path(directory).glob("*.yaml"))}


@dataclass
class LoadedConfig:
    app: AppConfig
    preset: Preset
    preset_id: str
    app_path: Path
    preset_path: Path


def load_all(app_path: Path | None = None, presets_dir: Path | None = None) -> LoadedConfig:
    """Load config.yaml plus its active preset. Raises ConfigError with readable messages."""
    if app_path is None:
        seed_user_config()
        app_path = user_config_path()
    app = load_app_config(app_path)
    presets = list_presets(presets_dir or Path(app_path).parent / "presets")
    if app.active_preset not in presets:
        known = ", ".join(presets) or "(none found)"
        raise ConfigError(app_path, [f"active_preset: '{app.active_preset}' not found; available: {known}"])
    for queued in app.contract_queue:
        if queued not in presets:
            raise ConfigError(app_path, [f"contract_queue: preset '{queued}' not found"])
    preset_path = presets[app.active_preset]
    return LoadedConfig(app, load_preset(preset_path), app.active_preset, Path(app_path), preset_path)
