from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])|\n+")
_WORD = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
_PUNCTUATION = "，。！？；：、,.!?;:—（）()《》“”\"'"


def split_sentences(text: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE_SPLIT.split(text) if piece.strip()]


def split_paragraphs(text: str) -> list[str]:
    return [piece.strip() for piece in re.split(r"\n\s*\n", text) if piece.strip()]


def _quantile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _WORD.findall(text)]


def _character_ngrams(text: str, n: int = 3) -> Counter[str]:
    cleaned = re.sub(r"\s+", "", text)
    cleaned = re.sub(f"[{re.escape(_PUNCTUATION)}]", "", cleaned)
    return Counter(cleaned[index : index + n] for index in range(max(0, len(cleaned) - n + 1)))


def extract_style_features(text: str) -> dict[str, object]:
    sentences = split_sentences(text)
    paragraphs = split_paragraphs(text)
    lengths = [len(re.sub(r"\s+", "", sentence)) for sentence in sentences]
    paragraph_lengths = [len(split_sentences(paragraph)) for paragraph in paragraphs]
    punctuation = {mark: text.count(mark) for mark in _PUNCTUATION if text.count(mark)}
    token_counts = Counter(_tokens(text))
    ngrams = _character_ngrams(text)
    repeated_ngrams = [{"text": gram, "count": count} for gram, count in ngrams.most_common(20) if count >= 2][:10]
    question_count = sum(sentence.endswith(("？", "?")) for sentence in sentences)
    imperative_count = sum(sentence.startswith(("请", "必须", "不要", "记住", "先", "务必")) for sentence in sentences)
    return {
        "characters": len(re.sub(r"\s+", "", text)),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "sentence_length": {
            "min": min(lengths, default=0),
            "p25": round(_quantile(lengths, 0.25), 2),
            "p50": round(_quantile(lengths, 0.50), 2),
            "p75": round(_quantile(lengths, 0.75), 2),
            "max": max(lengths, default=0),
            "mean": round(sum(lengths) / len(lengths), 2) if lengths else 0,
        },
        "paragraph_sentence_count": {"p50": round(_quantile(paragraph_lengths, 0.5), 2), "max": max(paragraph_lengths, default=0)},
        "punctuation": punctuation,
        "question_ratio": round(question_count / len(sentences), 4) if sentences else 0,
        "imperative_ratio": round(imperative_count / len(sentences), 4) if sentences else 0,
        "top_tokens": [{"text": token, "count": count} for token, count in token_counts.most_common(15) if len(token) > 1],
        "repeated_ngrams": repeated_ngrams,
    }


def aggregate_features(texts: Iterable[str]) -> dict[str, object]:
    material = list(texts)
    if not material:
        raise ValueError("at least one text is required")
    snapshot = extract_style_features("\n\n".join(material))
    snapshot["document_count"] = len(material)
    snapshot["per_document"] = [extract_style_features(text) for text in material]
    return snapshot
