from __future__ import annotations

import html
import re
import textwrap
from urllib.parse import urlparse


_FENCED_CODE_RE = re.compile(r"```(?:[A-Za-z0-9_+.-]+)?\n?(.*?)```", re.DOTALL)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*)?>")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
_URL_RE = re.compile(r"\bhttps?://[^\s<>()]+")
_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_BLOCKQUOTE_RE = re.compile(r"(?m)^\s{0,3}>\s?")
_LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:[-+*]|\d+[.)])\s+")
_TASK_MARKER_RE = re.compile(r"(?i)\[[ x]\]\s+")
_EMPHASIS_RE = re.compile(r"(?<!\w)([*_]{1,3})(\S(?:.*?\S)?)\1(?!\w)")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MARKDOWN_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>])")
_XMLISH_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_.:-]*\s*/?>")


def normalize_for_speech(text: str) -> str:
    """Convert display-oriented Markdown into text that is safer for TTS.

    The UI should keep the original Markdown. This function is only for the
    speech path, where visual formatting characters are likely to be read
    aloud by TTS models.
    """
    if not text:
        return ""

    speech = textwrap.dedent(html.unescape(text))
    speech = _FENCED_CODE_RE.sub(lambda m: _clean_code_block(m.group(1)), speech)
    speech = _IMAGE_RE.sub(lambda m: m.group(1), speech)
    speech = _LINK_RE.sub(lambda m: m.group(1), speech)
    speech = _AUTOLINK_RE.sub(lambda m: _url_to_speech(m.group(1)), speech)
    speech = _URL_RE.sub(lambda m: _url_to_speech(m.group(0)), speech)
    speech = _HEADING_RE.sub("", speech)
    speech = _BLOCKQUOTE_RE.sub("", speech)
    speech = _LIST_MARKER_RE.sub("", speech)
    speech = _TASK_MARKER_RE.sub("", speech)
    speech = _INLINE_CODE_RE.sub(lambda m: m.group(1), speech)
    speech = _MARKDOWN_ESCAPE_RE.sub(r"\1", speech)
    speech = _strip_emphasis(speech)
    speech = speech.replace("~~", "")
    speech = speech.replace("|", ", ")
    speech = _HTML_TAG_RE.sub("", speech)
    speech = _XMLISH_TAG_RE.sub("", speech)
    speech = _remove_visual_markers(speech)
    return _normalize_space(speech)


def _strip_emphasis(text: str) -> str:
    previous = None
    current = text
    while previous != current:
        previous = current
        current = _EMPHASIS_RE.sub(lambda m: m.group(2), current)
    return current


def _remove_visual_markers(text: str) -> str:
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"(?<!\w)_{1,3}|_{1,3}(?!\w)", "", text)
    text = re.sub(r"(?m)^\s*-{3,}\s*$", "", text)
    text = re.sub(r"(?m)^\s*={3,}\s*$", "", text)
    return text


def _clean_code_block(code: str) -> str:
    lines = [line.strip() for line in code.splitlines()]
    return " ".join(line for line in lines if line)


def _url_to_speech(url: str) -> str:
    trailing = ""
    while url and url[-1] in ".,;:!?":
        trailing = url[-1] + trailing
        url = url[:-1]
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    if host.startswith("www."):
        host = host[4:]
    return f"{host.replace('.', ' dot ')}{trailing}" if host else trailing


def _normalize_space(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?]){2,}", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
