"""Shared whole-word/phrase matching, used anywhere we keyword-match free
text. Plain substring checks (`tag in text`) false-positive on short words
embedded in unrelated words -- "eat" inside "heat", "now" inside "unknown",
"run" inside "running". Word-boundary matching avoids that."""
import re


def whole_word_match(phrase: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None
