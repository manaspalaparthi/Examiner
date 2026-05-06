from __future__ import annotations

from voice.speech_normalizer import normalize_for_speech


def test_removes_markdown_emphasis_without_losing_words() -> None:
    text = 'There are three bars: **Apples** at 50%, **Bananas** at 30%, and **Oranges** at 20%.'

    assert normalize_for_speech(text) == (
        "There are three bars: Apples at 50%, Bananas at 30%, and Oranges at 20%."
    )


def test_keeps_link_labels_and_drops_visual_markers() -> None:
    text = """
    ## Next steps
    - Read [the rubric](https://example.com/rubric)
    - Try `describe_chart()` out loud
    """

    assert normalize_for_speech(text) == "Next steps Read the rubric Try describe_chart() out loud"


def test_strips_tags_and_markdown_escapes() -> None:
    text = r"<speech>Say \*hello\* to <strong>students</strong>.</speech>"

    assert normalize_for_speech(text) == "Say hello to students."


def test_converts_standalone_urls_to_speakable_domains() -> None:
    assert normalize_for_speech("Open https://www.example.com/path?q=1.") == "Open example dot com."
