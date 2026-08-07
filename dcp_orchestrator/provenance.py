"""Provider-neutral provenance/history reference seam.

Entire is intentionally not installed or called. DCP remains the runtime state
authority; these nullable references can point at a future explicit provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class HistoryRefs:
    provider: str = "none"
    session: Optional[str] = None
    checkpoint: Optional[str] = None
    commit: Optional[str] = None
    digest: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> dict[str, Optional[str]]:
        return asdict(self)
