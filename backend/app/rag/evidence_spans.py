"""Resolve whitespace-only excerpts to source spans without fuzzy text matching."""
import re

_NUMBER = re.compile(r'\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?')


def diagnose_excerpt(excerpt: str, body: str) -> dict:
    """Content-free rejection metadata; never used to accept or repair quotes.

    Prefix locations are heuristic candidates, not proof of intended source.
    Work is bounded by a 128-character prefix per candidate location.
    Offsets refer to original strings, while prefix lengths ignore whitespace.
    """
    span = find_excerpt_span(excerpt, body)
    quote_positions = [i for i, c in enumerate(excerpt) if not c.isspace()]
    positions = [i for i, c in enumerate(body) if not c.isspace()]
    needle = ''.join(excerpt[i] for i in quote_positions)
    compact = ''.join(body[i] for i in positions)
    result = {'reason': 'matched' if span else 'empty_excerpt' if not needle else 'text_mismatch',
              'excerpt_chars': len(excerpt), 'body_chars': len(body)}
    if span or not needle:
        return result
    if needle in compact:
        result['reason'] = 'numeric_boundary_or_token_mismatch'
        offset = compact.find(needle)
        result['body_offset'] = positions[offset]
        return result
    best, start = 0, None
    for offset, char in enumerate(compact):
        if char != needle[0]:
            continue
        length = 0
        while length < min(128, len(needle), len(compact)-offset) and needle[length] == compact[offset+length]:
            length += 1
        if length > best:
            best, start = length, offset
    result.update(common_prefix_chars=best, prefix_limit=128,
                  excerpt_offset=quote_positions[best] if best < len(quote_positions) else len(excerpt),
                  body_offset=positions[start+best] if start is not None and start+best < len(positions) else len(body) if start is not None else None)
    return result


def find_excerpt_span(excerpt: str, body: str) -> tuple[int, int] | None:
    """Return [start, end) in the original body; never rewrite evidence.

    Only Unicode whitespace is ignored. Numbers must retain their original
    token boundaries, so PDF letter spacing is tolerated but '1 0' != '10'.
    No case, punctuation, Unicode compatibility or semantic normalization.
    """
    needle = ''.join(c for c in excerpt if not c.isspace())
    if not needle:
        return None
    positions = [i for i, c in enumerate(body) if not c.isspace()]
    compact = ''.join(body[i] for i in positions)
    quote_numbers = _NUMBER.findall(excerpt)
    body_numbers = list(_NUMBER.finditer(body))
    offset = compact.find(needle)
    while offset >= 0:
        start, end = positions[offset], positions[offset + len(needle) - 1] + 1
        # A literal substring inside 110, 1.0 or 1e3 is not a different number.
        cuts_number = any(m.start() < start < m.end() or m.start() < end < m.end()
                          for m in body_numbers)
        if not cuts_number and _NUMBER.findall(body[start:end]) == quote_numbers:
            return start, end
        offset = compact.find(needle, offset + 1)
    return None
