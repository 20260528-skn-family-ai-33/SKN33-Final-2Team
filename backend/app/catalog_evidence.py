"""Bounded model evidence selected from the full stored course description/outline."""
import re
from html import unescape
from html.parser import HTMLParser


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
        entry = {k: excerpt(str(row.get(k) or ''), 180) for k in ('title', 'section', 'description') if row.get(k)}
        size = sum(len(v) for v in entry.values())
        if len(selected) >= 16 or used + size > 1800:
            continue
        if row.get('suspended'):
            entry['suspended'] = True
        selected.append((index, entry))
        used += size
    content = str(r.get('content') or '')
    lines = content.splitlines()
    if len(content) > 1000:
        # Reserve an overview and relevant lines, rather than silently keeping a 600-char prefix.
        chosen = sorted(enumerate(lines), key=lambda pair: (-score(pair[1]), pair[0]))
        fragments, remaining = [(0, content[:350])], 650
        for index, line in chosen:
            if not score(line) or remaining <= 0:
                continue
            fragment = excerpt(line, min(300, remaining))
            fragments.append((index + 1, fragment))
            remaining -= len(fragment)
        content = '\n'.join(text for _, text in sorted(fragments))[:1000]
    return {'content': content, 'contentTruncated': len(content) < len(str(r.get('content') or '')),
            'audience': str(r.get('audience') or '')[:300], 'prereq': str(r.get('prereq') or '')[:300],
            'curriculum': [entry for _, entry in sorted(selected)], 'curriculumCount': len(rows),
            'curriculumOmitted': len(rows) - len(selected), 'curriculumCoverage': outline.get('coverage', 'description_only'),
            'timeStatus': r.get('timeStatus'), 'timeNote': r.get('timeNote'),
            'platform': r.get('platform'), 'url': r.get('url')}
