from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

APP_NAME = "Vibrato"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    workers: int = 2
    deterministic: bool = False
    frontend_dist: Path | None = None
    max_upload_bytes: int = 1024 * 1024 * 1024
    max_duration_s: float = 20 * 60.0
    min_duration_s: float = 0.25
    app_base_url: str | None = None
    allowed_origins: tuple[str, ...] = ()
    trusted_hosts: tuple[str, ...] = ()
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "vibrato.db"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.originals_dir,
            self.derived_dir,
            self.renders_dir,
            self.exports_dir,
            self.logs_dir,
            self.backups_dir,
            self.uploads_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    root = repo_root()
    data_dir = Path(os.environ.get("VIBRATO_DATA_DIR", str(root / "data"))).expanduser().resolve()
    dist_env = os.environ.get("VIBRATO_FRONTEND_DIST")
    dist = Path(dist_env).resolve() if dist_env else (root / "frontend" / "dist")
    return Settings(
        data_dir=data_dir,
        host=os.environ.get("VIBRATO_HOST", DEFAULT_HOST),
        port=_env_int("VIBRATO_PORT", DEFAULT_PORT),
        workers=max(1, _env_int("VIBRATO_WORKERS", 2)),
        deterministic=_env_bool("VIBRATO_DETERMINISTIC", False),
        frontend_dist=dist if dist.exists() else None,
        app_base_url=os.environ.get("VIBRATO_APP_BASE_URL") or None,
        allowed_origins=tuple(_env_list("VIBRATO_ALLOWED_ORIGINS")),
        trusted_hosts=tuple(_env_list("VIBRATO_TRUSTED_HOSTS")),
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
        _settings.ensure_dirs()
    return _settings


def configure(settings: Settings) -> Settings:
    global _settings
    settings.ensure_dirs()
    _settings = settings
    return settings


def with_overrides(**kwargs: Any) -> Settings:
    return configure(replace(get_settings(), **kwargs))
