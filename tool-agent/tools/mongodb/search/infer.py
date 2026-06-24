from __future__ import annotations

import re

_DB_KEYWORDS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"market[_\s-]?data", re.I), "market_data", 3),
    (re.compile(r"\bam-trade\b|am\s+trade", re.I), "am-trade", 3),
    (re.compile(r"trade[_\s-]?management", re.I), "trade_management", 3),
    (re.compile(r"mutual[_\s-]?funds?", re.I), "mutual_funds", 3),
    (re.compile(r"\bportfolio\b", re.I), "portfolio", 2),
    (re.compile(r"\bsecurities\b", re.I), "portfolio", 1),
    (re.compile(r"\binstruments?\b", re.I), "market_data", 2),
    (re.compile(r"\btrades?\b", re.I), "am-trade", 2),
    (re.compile(r"\betfs?\b", re.I), "mutual_funds", 2),
]

_COLLECTION_KEYWORDS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"\bsecurities\b", re.I), "securities", 2),
    (re.compile(r"\bportfolios?\b", re.I), "portfolios", 2),
    (re.compile(r"\binstruments?\b", re.I), "instruments", 2),
    (re.compile(r"trade[_\s-]?details?", re.I), "trade_details", 2),
    (re.compile(r"portfolio[_\s-]?trades?", re.I), "portfolio_trades", 2),
    (re.compile(r"\btrades?\b", re.I), "trades", 1),
    (re.compile(r"\betfs?\b", re.I), "etfs", 2),
]


def _ranked(matches: list[tuple[str, int]]) -> list[str]:
    scores: dict[str, int] = {}
    for name, weight in matches:
        scores[name] = scores.get(name, 0) + weight
    return sorted(scores, key=lambda key: (-scores[key], key))


def infer(query: str) -> list[str]:
    db_hits = [(db, weight) for pattern, db, weight in _DB_KEYWORDS if pattern.search(query)]
    coll_hits = [(coll, weight) for pattern, coll, weight in _COLLECTION_KEYWORDS if pattern.search(query)]
    ranked = _ranked(db_hits + coll_hits)
    return ranked[:5]
