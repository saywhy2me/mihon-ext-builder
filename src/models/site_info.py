from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class SiteType(Enum):
    MADARA = "madara"               # WordPress + Madara theme (most common)
    MANGADEX = "mangadex"           # MangaDex API v5
    COMICK = "comick"               # ComicK API
    MANGA_READER = "manga_reader"   # Generic manga reader CMSes
    WEBTOON = "webtoon"             # Webtoon-style vertical strip
    CUSTOM = "custom"               # Unique structure — needs manual work
    UNKNOWN = "unknown"             # Could not determine


class HealthStatus(Enum):
    ALIVE = "alive"
    DEGRADED = "degraded"           # Reachable but key endpoints failing
    DEAD = "dead"                   # Unreachable / 4xx/5xx on homepage
    CLOUDFLARE_BLOCKED = "cloudflare_blocked"
    RATE_LIMITED = "rate_limited"


@dataclass
class DetectedFeature:
    name: str
    confidence: float               # 0.0 – 1.0
    evidence: str                   # Short human-readable explanation


@dataclass
class SiteInfo:
    url: str
    site_type: SiteType
    health: HealthStatus
    name: Optional[str] = None
    language: Optional[str] = None
    base_url: Optional[str] = None
    api_base: Optional[str] = None
    has_cloudflare: bool = False
    has_login_wall: bool = False
    features: List[DetectedFeature] = field(default_factory=list)
    recommended_template: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    http_status: Optional[int] = None
    response_time_ms: Optional[int] = None

    @property
    def confidence(self) -> float:
        if not self.features:
            return 0.0
        return max(f.confidence for f in self.features)

    def summary(self) -> str:
        lines = [
            f"URL          : {self.url}",
            f"Type         : {self.site_type.value}",
            f"Health       : {self.health.value}",
            f"Confidence   : {self.confidence:.0%}",
            f"Template     : {self.recommended_template or 'none'}",
            f"Cloudflare   : {'yes' if self.has_cloudflare else 'no'}",
        ]
        if self.response_time_ms:
            lines.append(f"Response     : {self.response_time_ms}ms")
        if self.notes:
            lines.append("Notes:")
            for n in self.notes:
                lines.append(f"  - {n}")
        return "\n".join(lines)
