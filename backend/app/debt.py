"""
Decision debt: detect when a newly-logged decision is really the same
unresolved question as one already logged (possibly worded differently),
so repeated indecision can be surfaced as a pattern instead of looking like
unrelated one-off entries.

Only ever matches against decisions that are still open (no outcome
recorded). A routine choice that gets decided each time it comes up (e.g.
"skip breakfast" most mornings, each with its own outcome) is not the same
thing as a standing question that never gets answered -- matching against
resolved decisions was conflating the two and silently merging unrelated
daily choices into fake "debt" topics.
"""
import re

from . import models

_STOPWORDS = {
    "i", "a", "an", "the", "to", "do", "does", "should", "is", "it", "this",
    "that", "my", "on", "in", "for", "of", "or", "and", "yes", "no", "about",
    "today", "tonight", "still", "again", "me", "with", "so", "just",
    # Decision-framing words: every entry in this app is phrased as a
    # decision, so words describing the *act of deciding* (rather than what
    # the decision is about) carry no topic-identifying signal and only
    # dilute the similarity score against the one or two words that do.
    "deciding", "decide", "decided", "thinking", "wondering", "considering",
    "go", "going", "get", "getting", "want", "wanted",
}

SIMILARITY_THRESHOLD = 0.5


def _stem(word: str) -> str:
    """Crude suffix-stripping so "skip"/"skipping"/"skipped" match."""
    if word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        word = word[:-1]
    if len(word) >= 2 and word[-1] == word[-2] and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def _normalize(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def find_matching_topic(decision_type: str, text: str) -> int | None:
    """Return the topic_id this decision belongs to, or None if it's new."""
    candidates = models.get_open_decisions_by_type(decision_type)
    new_words = _normalize(text)
    if not new_words:
        return None

    best_candidate = None
    best_score = 0.0
    for candidate in candidates:
        score = _similarity(new_words, _normalize(candidate["text"]))
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_candidate and best_score >= SIMILARITY_THRESHOLD:
        return best_candidate["topic_id"] or best_candidate["id"]
    return None
