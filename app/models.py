from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Publication:
    title: str
    kind: str
    number: str | None
    summary: str | None
    published_date: date
    source_url: str
    fingerprint: str

