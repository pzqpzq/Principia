"""Constants used by the shared retrieval package."""

USER_AGENT = "Principia/1.3.3 (academic metadata retrieval; https://github.com/pzqpzq/Principia)"

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
    "like",
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
