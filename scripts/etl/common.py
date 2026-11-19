"""Shared helpers for Tier-1 enrichment ETL modules."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "store" / "annotations" / "raw"
OUT = ROOT / "store" / "annotations"
META = OUT / "meta"


def ensure_dirs():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)


def fetch(url, filename, min_bytes=1000):
    dest = RAW / filename
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(
        ["curl", "-sL", "--fail", "--retry", "3", "--retry-delay", "5",
         "--max-time", "600", "-o", str(tmp), url],
        check=True,
    )
    if tmp.stat().st_size < min_bytes:
        raise RuntimeError(f"{url}: downloaded only {tmp.stat().st_size} bytes")
    tmp.replace(dest)
    return dest


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_meta(module, sources, notes=""):
    ensure_dirs()
    payload = {
        "module": module,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "notes": notes,
        "sources": {},
    }
    for name, (url, path) in sources.items():
        path = Path(path)
        payload["sources"][name] = {
            "url": url,
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    target = META / f"{module}.json"
    target.write_text(json.dumps(payload, indent=2))
    print(f"[meta] {target}")
