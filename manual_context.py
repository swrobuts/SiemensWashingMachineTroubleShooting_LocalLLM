"""Verified procedure boundaries for the bundled manual's flat OCR headings.

This is curated metadata for this manual, not a general PDF hierarchy parser.
Original text is retained. Safety paragraphs and numbered subheadings travel
with their procedure when a fragment is retrieved.
"""
from pathlib import Path
from functools import lru_cache
import re

MANUAL = Path(__file__).resolve().parent / 'siemens_wissen.md'
BOUNDARIES = (
    ('pump', 'Laugenpumpe verstopft, Notentleerung', 'Ablaufschlauch am Siphon verstopft'),
    ('door', 'S t r ö n u , e g w a . ? s Notentriegelung', 'Hinweise im Anzeigefeld'),
    ('first_wash', 'Vor dem 1. Waschen', 'Transportieren'),
    ('transport', 'Transportieren', 'Aquastop-Garantie'),
)


@lru_cache(maxsize=4)
def groups_from_text(raw):
    groups = {}
    for group_id, start, end in BOUNDARIES:
        opening = re.search(r'^## ' + re.escape(start) + r'\s*$', raw, re.M)
        closing = re.search(r'^## ' + re.escape(end) + r'\s*$', raw, re.M)
        if opening and closing and opening.start() < closing.start():
            groups[group_id] = {'title': start, 'text': raw[opening.start():closing.start()].strip()}
    return groups


def get_groups():
    return groups_from_text(MANUAL.read_text(encoding='utf-8'))


def group_for_text(text, groups):
    text = text.strip()
    if not text:
        return None
    return next((key for key, group in groups.items() if text in group['text']), None)


def expand_sources(sources):
    """Return complete procedure evidence, once per group, in retrieval order."""
    groups, result, seen = get_groups(), [], set()
    for source in sources:
        group_id = source.get('context_group') or group_for_text(source.get('text', ''), groups)
        if group_id in groups:
            if group_id in seen:
                continue
            seen.add(group_id)
            group = groups[group_id]
            source = {**source, 'id': 'procedure-' + group_id, 'section': group['title'],
                      'text': group['text'], 'context_group': group_id}
        result.append(source)
    return result
