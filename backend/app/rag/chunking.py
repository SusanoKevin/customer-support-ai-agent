"""Heading-aware chunking for policy markdown.

Policies are short and sectioned, so each `## ` section is one chunk (one rule).
Long sections fall back to a word window with overlap. Tier tags come from a
`Tiers:` line in each section; no line means every tier.
"""

import re
from dataclasses import dataclass

MAX_WORDS = 180
OVERLAP_WORDS = 30
ALL_TIERS = ("free", "pro", "enterprise")
TIERS_LINE = re.compile(r"^Tiers:\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class RawChunk:
    chunk_id: str
    doc: str
    heading: str
    text: str
    tiers: tuple[str, ...]


def _parse_tiers(section: str) -> tuple[str, ...]:
    match = TIERS_LINE.search(section)
    if not match:
        return ALL_TIERS
    named = [t.strip().lower() for t in match.group(1).split(",")]
    return tuple(t for t in named if t in ALL_TIERS) or ALL_TIERS


def _windows(words: list[str]) -> list[str]:
    """Overlapping windows; a section of MAX_WORDS or fewer stays one chunk."""
    step = MAX_WORDS - OVERLAP_WORDS
    starts = range(0, max(len(words) - OVERLAP_WORDS, 1), step)
    return [" ".join(words[i : i + MAX_WORDS]) for i in starts]


def chunk_markdown(doc: str, markdown: str) -> list[RawChunk]:
    sections = re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]  # [0] is the title
    chunks = []
    for s_idx, section in enumerate(sections):
        heading, _, body = section.partition("\n")
        tiers = _parse_tiers(body)
        text = TIERS_LINE.sub("", body).strip()
        chunks.extend(
            RawChunk(chunk_id=f"{doc}:{s_idx}:{w_idx}", doc=doc, heading=heading.strip(), text=window, tiers=tiers)
            for w_idx, window in enumerate(_windows(text.split()))
        )
    return chunks
