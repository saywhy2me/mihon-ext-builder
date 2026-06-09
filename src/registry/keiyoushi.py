"""Coverage lookup against the keiyoushi extension repository.

Before scaffolding a brand-new extension it is worth knowing whether the site
is *already* supported by keiyoushi/extensions-source — its sources are almost
always more complete than an auto-generated scaffold, and the user can install
them from the repo with one tap. This module fetches the published extension
index and answers "is this domain already covered?".
"""

from __future__ import annotations

import json
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

INDEX_URL = "https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.min.json"
REPO_URL = "https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.min.json"

_CACHE_PATH = Path(tempfile.gettempdir()) / "mihon_ext_keiyoushi_index.json"
_CACHE_TTL_SECONDS = 24 * 60 * 60  # refresh at most once a day


@dataclass
class Coverage:
    """One source within an installed keiyoushi extension that matches a domain."""
    ext_name: str
    pkg: str
    version: str
    version_code: int
    nsfw: bool
    source_name: str
    base_url: str
    lang: str

    @property
    def repo_hint(self) -> str:
        return (f"{self.source_name} (v{self.version}) — already in keiyoushi; "
                f"install it from the repo instead of building.")


def normalize_host(url: str) -> str:
    """Reduce a URL or bare domain to a comparable host (lowercase, no www)."""
    raw = (url or "").strip().lower()
    if raw and "://" not in raw:
        raw = "https://" + raw
    host = urlparse(raw).netloc or urlparse(raw).path
    host = host.split("/")[0].split(":")[0]  # drop path / port if any slipped in
    if host.startswith("www."):
        host = host[4:]
    return host


class IndexUnavailable(RuntimeError):
    """Raised when the extension index cannot be fetched and isn't cached."""


def fetch_index(force: bool = False, timeout: int = 30) -> list[dict]:
    """Return the parsed keiyoushi index, using a 1-day on-disk cache.

    Raises IndexUnavailable if the network fails and no cache exists.
    """
    if not force and _CACHE_PATH.exists():
        age = time.time() - _CACHE_PATH.stat().st_mtime
        if age < _CACHE_TTL_SECONDS:
            try:
                return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass  # corrupt cache — fall through and refetch

    try:
        req = urllib.request.Request(INDEX_URL, headers={"User-Agent": "mihon-ext-builder"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        try:
            _CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass  # caching is best-effort
        return data
    except Exception as exc:  # network error, JSON error, etc.
        if _CACHE_PATH.exists():  # serve stale cache rather than nothing
            try:
                return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        raise IndexUnavailable(str(exc)) from exc


def find_coverage(url: str, index: Optional[list[dict]] = None,
                  timeout: int = 30) -> list[Coverage]:
    """Return every keiyoushi source whose baseUrl host matches `url`'s host.

    An empty list means the domain is not covered. Raises IndexUnavailable if
    the index can't be loaded.
    """
    target = normalize_host(url)
    if not target:
        return []
    if index is None:
        index = fetch_index(timeout=timeout)

    matches: list[Coverage] = []
    for ext in index:
        for src in ext.get("sources", []):
            base = src.get("baseUrl") or ""
            if base and normalize_host(base) == target:
                matches.append(Coverage(
                    ext_name=ext.get("name", "").removeprefix("Tachiyomi: "),
                    pkg=ext.get("pkg", ""),
                    version=str(ext.get("version", "")),
                    version_code=int(ext.get("code", 0) or 0),
                    nsfw=bool(ext.get("nsfw", 0)),
                    source_name=src.get("name", ext.get("name", "")),
                    base_url=base,
                    lang=src.get("lang", ext.get("lang", "")),
                ))
    return matches


def covered_hosts(index: Optional[list[dict]] = None, timeout: int = 30) -> set[str]:
    """Return the set of all normalized hosts covered by the repo (for bulk checks)."""
    if index is None:
        index = fetch_index(timeout=timeout)
    hosts: set[str] = set()
    for ext in index:
        for src in ext.get("sources", []):
            h = normalize_host(src.get("baseUrl") or "")
            if h:
                hosts.add(h)
    return hosts
