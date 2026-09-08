"""Constants used by the shared retrieval package."""

USER_AGENT = "Principia-Retrieval/0.1 (local research workspace)"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "use",
    "using",
    "via",
    "we",
    "with",
    "within",
    "without",
    "would",
}

RELATION_ORDER = {"direct": 3, "background": 2, "methodological": 1, "out_of_scope": 0}
