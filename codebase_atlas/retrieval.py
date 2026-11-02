"""Retrieval over code: tokenized index of symbols, lines, paths, and docs.

Grounded or silent: `ask` only returns evidence that exists in the repo,
and refuses when the question's terms are not supported by the code.
"""
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .analysis.summaries import first_sentence

NOT_SUPPORTED = "Not supported by this codebase."

STOPWORDS = {
    "a", "about", "after", "all", "an", "and", "any", "are", "as", "at", "be",
    "been", "before", "between", "but", "by", "can", "could", "did", "do",
    "does", "doing", "each", "for", "from", "get", "gets", "got", "had", "has",
    "have", "how", "i", "if", "in", "into", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "should", "so", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "up",
    "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "will", "with", "would", "you", "your", "tell", "show",
    "explain", "describe", "code", "codebase", "repo", "repository", "project",
    "function", "functions", "method", "methods", "file", "files", "module",
    "modules", "class", "classes", "work", "works", "happen", "happens",
    "handle", "handled", "handles", "implement", "implemented", "implements",
    "use", "used", "uses", "using", "defined", "define", "defines", "there",
    "way", "place", "part", "logic", "thing", "things", "does", "done", "make",
    "made", "need", "needs", "please", "list", "find", "located", "live",
    "lives", "responsible", "call", "called", "calls", "calling",
}

IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

WEIGHT_SYMBOL = 4.0
WEIGHT_PATH = 2.5
WEIGHT_LINE = 1.0
MIN_COVERAGE = 0.5


def stem(word):
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ied"):
        word = word[:-3] + "y"
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("es"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def tokenize(text, keep_stopwords=False):
    """Split text into stemmed, lowercased terms, including identifier parts."""
    terms = []
    for ident in IDENT_RE.findall(text):
        pieces = [p for part in ident.split("_") for p in CAMEL_RE.findall(part)]
        whole = ident.lower()
        if len(pieces) > 1:
            terms.append(whole)
        for piece in pieces:
            lower = piece.lower()
            if len(lower) < 2 or (not keep_stopwords and lower in STOPWORDS):
                continue
            terms.append(stem(lower))
    return terms


@dataclass
class Unit:
    path: str
    line: int
    kind: str  # symbol, line, path, doc
    weight: float
    terms: set
    symbol: object = None


@dataclass
class Evidence:
    path: str
    line: int
    snippet: str
    score: float
    matched: list
    kind: str


@dataclass
class Answer:
    question: str
    supported: bool
    terms: list
    matched_terms: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    facts: list = field(default_factory=list)  # (text, [citations])
    reason: str = ""


class CodeIndex:
    def __init__(self, atlas):
        self.atlas = atlas
        self.units = []
        self.postings = defaultdict(list)
        self.file_terms = defaultdict(set)
        self._build()
        total = max(1, len(self.file_terms))
        doc_freq = defaultdict(int)
        for terms in self.file_terms.values():
            for term in terms:
                doc_freq[term] += 1
        self.idf = {t: math.log(1 + total / df) for t, df in doc_freq.items()}

    def _add(self, unit):
        if not unit.terms:
            return
        index = len(self.units)
        self.units.append(unit)
        for term in unit.terms:
            self.postings[term].append(index)
        self.file_terms[unit.path].update(unit.terms)

    def _build(self):
        for path, module in self.atlas.modules.items():
            # Every unit is cited at a line whose text (or, for "path", file
            # name) contains its terms; doc comments are indexed as lines.
            self._add(Unit(path, 1, "path", WEIGHT_PATH, set(tokenize(path))))
            for symbol in module.symbols:
                self._add(Unit(path, symbol.line, "symbol", WEIGHT_SYMBOL,
                               set(tokenize(symbol.qualified_name)), symbol))
            for number, text in enumerate(self.atlas.sources.get(path, []), 1):
                self._add(Unit(path, number, "line", WEIGHT_LINE, set(tokenize(text))))
        for path, lines in self.atlas.docs.items():
            for number, text in enumerate(lines, 1):
                self._add(Unit(path, number, "doc", WEIGHT_LINE, set(tokenize(text))))

    def line_text(self, path, line):
        lines = self.atlas.sources.get(path) or self.atlas.docs.get(path) or []
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    def search(self, terms, limit=8, per_file=3):
        scores = defaultdict(float)
        matched = defaultdict(set)
        for term in terms:
            for index in self.postings.get(term, ()):
                scores[index] += self.idf.get(term, 0.0) * self.units[index].weight
                matched[index].add(term)
        ranked = sorted(scores, key=lambda i: (-scores[i] * len(matched[i]), self.units[i].path, self.units[i].line))
        results, seen, per_path = [], set(), defaultdict(int)
        for index in ranked:
            unit = self.units[index]
            key = (unit.path, unit.line)
            if key in seen or per_path[unit.path] >= per_file:
                continue
            seen.add(key)
            per_path[unit.path] += 1
            results.append(Evidence(unit.path, unit.line, self.line_text(unit.path, unit.line)[:160],
                                    round(scores[index] * len(matched[index]), 2),
                                    sorted(matched[index]), unit.kind))
            if len(results) >= limit:
                break
        return results


def question_terms(question):
    seen, terms = set(), []
    for term in tokenize(question):
        if term not in seen and term not in STOPWORDS:
            seen.add(term)
            terms.append(term)
    return terms


def ask(atlas, question, limit=8, index=None):
    """Answer from retrieved code evidence, or refuse when unsupported."""
    index = index or CodeIndex(atlas)
    terms = question_terms(question)
    answer = Answer(question, False, terms)
    if not terms:
        answer.reason = "the question has no searchable terms"
        return answer
    answer.matched_terms = [t for t in terms if t in index.postings]
    missing = [t for t in terms if t not in index.postings]
    best_file = max((len(set(terms) & ft) for ft in index.file_terms.values()), default=0)
    if len(answer.matched_terms) / len(terms) < MIN_COVERAGE or best_file / len(terms) < MIN_COVERAGE:
        answer.reason = "no code mentions: " + ", ".join(missing or terms) if missing \
            else "the terms never appear together in any file"
        return answer
    answer.evidence = _strongest(index.search(answer.matched_terms, limit * 2))[:limit]
    answer.facts = symbol_facts(atlas, question, answer.matched_terms)
    answer.supported = bool(answer.evidence)
    return answer


def _strongest(evidence):
    """Keep hits matching at least half as many terms as the best hit."""
    if not evidence:
        return evidence
    best = max(len(e.matched) for e in evidence)
    return [e for e in evidence if 2 * len(e.matched) >= best]


def _named_by_parts(symbol, terms):
    parts = [t for t in tokenize(symbol.name) if t != symbol.name.lower()]
    return len(parts) >= 2 and all(p in terms for p in parts)


def symbol_facts(atlas, question, terms, limit=5):
    """Statements about symbols the question names, each with citations."""
    named = {w.lower() for w in IDENT_RE.findall(question)}
    wanted = set(terms) | named
    facts = []
    for path in sorted(atlas.modules):
        for symbol in atlas.modules[path].symbols:
            if symbol.name.lower() not in wanted and symbol.qualified_name.lower() not in wanted \
                    and not _named_by_parts(symbol, wanted):
                continue
            if len(symbol.name) < 3:
                continue
            exact = symbol.name.lower() in named or symbol.qualified_name.lower() in named
            facts.append((exact,) + _describe_symbol(atlas, path, symbol))
    if any(exact for exact, _, _ in facts):
        facts = [f for f in facts if f[0]]
    facts.sort(key=lambda f: (not f[0], -len(f[2])))
    return [(text, citations) for _, text, citations in facts[:limit]]


def _describe_symbol(atlas, path, symbol):
    citation = f"{path}:{symbol.line}"
    text = f"`{symbol.qualified_name}` is a {symbol.kind} defined at {citation}"
    if symbol.end_line > symbol.line:
        text += f"-{symbol.end_line}"
    doc = first_sentence(symbol.doc)
    if doc:
        text += f': "{doc}"'
    citations = [citation]
    users = [u for u in atlas.graph.all_uses() if u.dst == path and u.symbol == symbol.name]
    users.sort(key=lambda u: (u.src, u.line))
    if users:
        shown = [f"{u.src}:{u.line} ({u.reason})" for u in users[:6]]
        text += ". Used at " + ", ".join(shown) + (f" and {len(users) - 6} more" if len(users) > 6 else "")
        citations += [f"{u.src}:{u.line}" for u in users[:6]]
    return text + ".", citations
