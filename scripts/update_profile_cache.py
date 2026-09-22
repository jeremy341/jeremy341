"""Update GitHub profile SVG cache versions and README fallback text."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ASSETS = ROOT / "assets"
PROFILE_URL = "https://raw.githubusercontent.com/jeremy341/jeremy341/main/assets/"
_DIGEST = re.compile(r"[0-9a-f]{12}\Z")


def update_cache_versions(readme: str, desktop_digest: str, mobile_digest: str) -> str:
    """Replace only the desktop and mobile profile SVG cache query versions."""
    for name, digest in (("desktop", desktop_digest), ("mobile", mobile_digest)):
        if not _DIGEST.fullmatch(digest):
            raise ValueError(f"{name} digest must be 12 lowercase hexadecimal characters")

    updated = readme
    for filename, digest in (
        ("profile-dark.svg", desktop_digest),
        ("profile-mobile-dark.svg", mobile_digest),
    ):
        url = re.escape(PROFILE_URL + filename)
        pattern = re.compile(url + r"\?v=[^\s\"']*")
        matches = list(pattern.finditer(updated))
        if len(matches) != 1:
            raise ValueError(f"Expected {filename} URL exactly once; found {len(matches)}")
        updated = pattern.sub(PROFILE_URL + filename + "?v=" + digest, updated, count=1)
    return updated


def main() -> None:
    desktop_digest = hashlib.sha256((ASSETS / "profile-dark.svg").read_bytes()).hexdigest()[:12]
    mobile_digest = hashlib.sha256((ASSETS / "profile-mobile-dark.svg").read_bytes()).hexdigest()[:12]
    original = README.read_text(encoding="utf-8")
    updated = update_cache_versions(original, desktop_digest, mobile_digest)
    if updated != original:
        README.write_text(updated, encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
