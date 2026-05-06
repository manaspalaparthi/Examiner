from __future__ import annotations

import re
from collections.abc import AsyncIterator

# Match sentence-terminating punctuation followed by whitespace/end,
# OR a paragraph break.
_SENTENCE_END = re.compile(r"([.!?]+)(\s|$)|(\n{2,})")


async def sentencize(
    tokens: AsyncIterator[str],
    *,
    min_chars: int = 12,
) -> AsyncIterator[str]:
    """Coalesce a token stream into complete sentences.

    Yields each sentence as soon as a terminal `.!?` (followed by whitespace
    or end-of-stream) or a paragraph break is seen, with a small abbreviation
    guard so single-letter caps like ``Dr.`` don't trigger early splits.
    The `min_chars` floor avoids TTS-ing one-word fragments (``Yes.``).
    """
    buf = ""
    async for tok in tokens:
        if not tok:
            continue
        buf += tok
        while True:
            split = _find_split(buf, min_chars)
            if split is None:
                break
            sentence = buf[:split].strip()
            buf = buf[split:].lstrip()
            if sentence:
                yield sentence
    tail = buf.strip()
    if tail:
        yield tail


def _find_split(buf: str, min_chars: int) -> int | None:
    if len(buf) < min_chars:
        return None
    for m in _SENTENCE_END.finditer(buf):
        end = m.end()
        if end - 1 < min_chars:
            continue
        # Abbreviation guard: skip "X." where X is a single uppercase letter
        # preceded by a word boundary. Catches Dr., Mr., U., etc.
        if m.group(1) and m.group(1) == "." and m.start() >= 1:
            prev = buf[m.start() - 1]
            if prev.isupper():
                before_prev = buf[m.start() - 2] if m.start() >= 2 else " "
                if not before_prev.isalpha():
                    continue
        return end
    return None
