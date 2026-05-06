from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from voice.sentencizer import sentencize


async def _from_list(tokens: list[str]) -> AsyncIterator[str]:
    for t in tokens:
        yield t


async def _collect(tokens: list[str], **kw) -> list[str]:
    return [s async for s in sentencize(_from_list(tokens), **kw)]


@pytest.mark.asyncio
async def test_simple_two_sentences():
    out = await _collect(["Hello there. ", "How are you today?"])
    assert out == ["Hello there.", "How are you today?"]


@pytest.mark.asyncio
async def test_split_across_tokens():
    out = await _collect(list("This is a long sentence. And another one!"))
    assert out == ["This is a long sentence.", "And another one!"]


@pytest.mark.asyncio
async def test_abbreviation_guard_keeps_sentence_intact():
    out = await _collect(["Dr. Smith arrived early today. ", "He was tired."])
    assert out == ["Dr. Smith arrived early today.", "He was tired."]


@pytest.mark.asyncio
async def test_min_chars_avoids_tiny_fragments():
    # "OK." is shorter than min_chars (12) so it must be glued to next sentence.
    out = await _collect(["OK. ", "That makes sense to me."])
    assert out == ["OK. That makes sense to me."]


@pytest.mark.asyncio
async def test_paragraph_break_splits():
    out = await _collect(["First paragraph here\n\n", "Second paragraph here"])
    assert out == ["First paragraph here", "Second paragraph here"]


@pytest.mark.asyncio
async def test_unterminated_tail_is_flushed():
    out = await _collect(["Halfway through a thought"])
    assert out == ["Halfway through a thought"]


@pytest.mark.asyncio
async def test_empty_stream():
    out = await _collect([])
    assert out == []


@pytest.mark.asyncio
async def test_skips_empty_tokens():
    out = await _collect(["", "Hello there. ", "", "Another one."])
    assert out == ["Hello there.", "Another one."]
