"""Core helpers for the Cescopedia edit system: config, paths, file IO, locking, hashing.
Python standard library only."""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ADMIN_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ADMIN_DIR / "config.json"


class Cfg:
    """Configuration + resolved paths. Everything the system touches hangs off this object, so tests can point
    the whole system at a copy of the site and content store with CESCO_ADMIN_CONFIG=/path/config.json."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path or os.environ.get("CESCO_ADMIN_CONFIG") or DEFAULT_CONFIG).resolve()
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        base = self.path.parent
        self.site_dir = (base / self.data["site_dir"]).resolve()      # relative paths are relative to the config file
        self.content_dir = (base / self.data["content_dir"]).resolve()
        self.secrets_dir = (base / self.data.get("secrets_dir", "secrets")).resolve()
        self.port = int(self.data.get("port", 8767))
        self.approvers = list(self.data.get("approvers", ["Meth", "EA"]))
        self.public_viewer = self.data.get("public_viewer", "http://127.0.0.1:8766/")
        # content store layout
        self.articles = self.content_dir / "articles"
        self.versions = self.content_dir / "versions"
        self.pending = self.content_dir / "pending"
        self.resolved = self.content_dir / "resolved"
        self.drafts = self.content_dir / "drafts"
        self.staging = self.content_dir / "staging" / "uploads"
        self.changelog_dir = self.content_dir / "changelog"
        self.site_json = self.content_dir / "site.json"
        self.changelog_json = self.content_dir / "changelog.json"
        self.history_log = self.content_dir / "history.jsonl"
        self.lockfile = self.content_dir / ".lock"
        self.home_template = self.content_dir / "home-template.html"

    def save(self):
        write_json(self.path, self.data)

    def ensure_dirs(self):
        for d in (self.articles, self.versions, self.pending, self.resolved, self.drafts, self.staging,
                  self.changelog_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.secrets_dir, 0o700)


def atomic_write(path: Path, data: bytes | str, mode: int | None = None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-" + path.name + ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        elif path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: Path, obj, mode: int | None = None):
    atomic_write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n", mode)


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise


@contextmanager
def store_lock(cfg: Cfg):
    """Exclusive lock over the whole content store (approve/reject/submit/build serialise on this)."""
    cfg.content_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.lockfile, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def new_id(prefix: str = "") -> str:
    return prefix + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def valid_slug(s: str) -> bool:
    return bool(SLUG_RE.match(s or ""))


# ---- passphrase hashing (scrypt; only the hash is stored) -------------------------------------------------------
def hash_secret(secret: str, salt: bytes | None = None) -> dict:
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return {"algo": "scrypt", "n": 16384, "r": 8, "p": 1, "salt": salt.hex(), "hash": h.hex()}


def verify_secret(secret: str, rec: dict | None) -> bool:
    if not rec or not secret:
        return False
    try:
        h = hashlib.scrypt(secret.encode("utf-8"), salt=bytes.fromhex(rec["salt"]), n=rec["n"], r=rec["r"],
                           p=rec["p"], dklen=32)
        return hmac.compare_digest(h.hex(), rec["hash"])
    except Exception:
        return False


def grok_token_path(cfg: Cfg) -> Path:
    return cfg.secrets_dir / "grok-submit-token"


def ensure_grok_token(cfg: Cfg) -> Path:
    """Create the Grok submit-only token file (mode 600) if it does not exist. Never prints the token."""
    cfg.ensure_dirs()
    p = grok_token_path(cfg)
    if not p.exists():
        atomic_write(p, secrets.token_urlsafe(32) + "\n", 0o600)
    else:
        os.chmod(p, 0o600)
    return p


def read_grok_token(cfg: Cfg) -> str:
    try:
        return grok_token_path(cfg).read_text().strip()
    except FileNotFoundError:
        return ""
