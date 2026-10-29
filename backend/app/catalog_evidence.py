"""Bounded model evidence selected from the full stored course description/outline."""
import json
import re
from html import unescape
from html.parser import HTMLParser

CATALOG_BYTES = 12_000
EVIDENCE_COURSES = 4
DESCRIPTION_CHARS = 240
OUTLINE_CHARS = 240


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if not self.hidden and tag in ('p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'section'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in ('p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'section'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def content_text(value):
    value = str(value or '')
    if re.search(r'</?(?:div|p|br|section|article|table|h[1-6]|span|script|style)\b', value, re.I):
        parser = _Text()
        parser.feed(value)
        value = ''.join(parser.parts)
    value = re.sub(r'^\s*id="course"\s+class="[^"]*">\s*', '', value)
    return '\n'.join(line for raw in unescape(value).splitlines() if (line := ' '.join(raw.split())))


def terms(texts):
    return {word.lower() for word in re.findall(r'[A-Za-z0-9+#.]{2,}|[가-힣]{2,}', ' '.join(texts or []))}


def evidence(r: dict, texts: list[str] | None = None) -> dict:
    outline = r.get('curriculum') or {}
    rows = outline.get('items') or []
    want = terms(texts)

    def score(text):
        return sum(word in text.lower() for word in want)

    def excerpt(text, limit):
        if len(text) <= limit:
            return text
        matches = [text.lower().find(word) for word in sorted(want) if word in text.lower()]
        start = max(0, min(matches) - limit // 3) if matches else 0
        return text[start:start + limit]

    # Relevant later chapters must survive the budget; show selected rows in source order.
    ranked = sorted(enumerate(rows), key=lambda pair: (-score(' '.join(str(pair[1].get(k) or '') for k in ('title', 'section', 'description'))), pair[0]))
    selected, used = [], 0
    for index, row in ranked:
        entry = {k: excerpt(str(row.get(k) or ''), 40 if k == 'section' else 80)
                 for k in ('title', 'section', 'description') if row.get(k)}
        size = sum(len(v) for v in entry.values())
        if len(selected) >= 3 or used + size > OUTLINE_CHARS:
            continue
        if row.get('suspended'):
            entry['suspended'] = True
        selected.append((index, entry))
        used += size
    content = str(r.get('content') or '')
    lines = content.splitlines()
    if len(content) > DESCRIPTION_CHARS:
        # Reserve an overview and relevant lines, rather than silently keeping a 600-char prefix.
        chosen = sorted(enumerate(lines), key=lambda pair: (-score(pair[1]), pair[0]))
        fragments, remaining = [(0, content[:80])], DESCRIPTION_CHARS - 80
        for index, line in chosen:
            if not score(line) or remaining <= 0:
                continue
            fragment = excerpt(line, min(120, remaining))
            fragments.append((index + 1, fragment))
            remaining -= len(fragment)
        content = '\n'.join(text for _, text in sorted(fragments))[:DESCRIPTION_CHARS]
    return {'content': content, 'contentTruncated': len(content) < len(str(r.get('content') or '')),
            'curriculum': [entry for _, entry in sorted(selected)], 'curriculumCount': len(rows),
            'curriculumOmitted': len(rows) - len(selected), 'curriculumCoverage': outline.get('coverage', 'description_only'),
            'timeStatus': r.get('timeStatus'), 'timeNote': str(r.get('timeNote') or '')[:120]}


def entry(r: dict, *, skill_names: bool = True) -> dict:
    """Compact candidate identity; restore the original four-skill contract."""
    return {'id': r['id'], 'title': r['title'][:120], 'kind': r['kind'], 'format': (r.get('format') or '')[:40],
            'hours': r.get('hours'), 'timeStatus': r.get('timeStatus'),
            'cost': r.get('cost'), 'stage': r.get('stage'), 'real': r.get('real'),
            'skills': [str(s)[:80] for s in r.get('skills', [])[:4]] if skill_names else []}


def packed_bytes(value: list[dict]) -> int:
    # Match runtime.llm_json's JSON spacing and UTF-8, including keys and escaping.
    return len(json.dumps(value, ensure_ascii=False, default=str).encode('utf-8'))


def pack(records: list[dict], texts: list[str] | None = None) -> list[dict]:
    """Bound the whole catalog, not each candidate multiplied by 28.

    Keep compact candidates first; enrich at most the first four courses only
    when the complete serialized catalog still fits. This byte budget is not
    a token count or a guarantee about the rest of the model prompt.
    """
    result, kept = [], []
    for r in records:
        compact = entry(r)
        if packed_bytes(result + [compact]) > CATALOG_BYTES:
            continue
        result.append(compact)
        kept.append(r)
    enriched = 0
    for index, r in enumerate(kept):
        if enriched >= EVIDENCE_COURSES:
            break
        if r.get('type') != 'course':
            continue
        detailed = dict(result[index], **evidence(r, texts))
        candidate = result[:index] + [detailed] + result[index + 1:]
        if packed_bytes(candidate) <= CATALOG_BYTES:
            result[index] = detailed
            enriched += 1
    return result
