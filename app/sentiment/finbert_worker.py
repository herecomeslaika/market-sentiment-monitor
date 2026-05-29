from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_pipeline = None

# Chinese-friendly multilingual sentiment model
# Options:
#   "lxyuan/distilbert-base-multilingual-cased-sentiments-student" — 3-class (pos/neg/neu), multilingual
#   "uer/roberta-base-finetuned-jd-binary-chinese" — 2-class Chinese sentiment
#   "IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment" — Chinese financial sentiment
DEFAULT_MODEL = "lxyuan/distilbert-base-multilingual-cased-sentiments-student"


def init_model(model_name: str | None = None):
    """Called once per subprocess by ProcessPoolExecutor initializer."""
    global _pipeline
    model_name = model_name or DEFAULT_MODEL
    from transformers import pipeline as hf_pipeline

    _pipeline = hf_pipeline(
        "text-classification",
        model=model_name,
        top_k=1,
        device="cpu",
        truncation=True,
        max_length=512,
    )
    logger.info("Sentiment model loaded in subprocess: %s", model_name)


def score_text(title: str) -> tuple[float, str, float]:
    """Score a single text. Returns (score, label, confidence).

    Maps model labels to continuous score:
      positive -> +confidence
      negative -> -confidence
      neutral  -> 0.0
    """
    if _pipeline is None:
        return 0.0, "error", 0.0

    try:
        result = _pipeline(title)
        # Result format: [{"label": "POSITIVE", "score": 0.98}]
        if isinstance(result, list) and len(result) > 0:
            best = result[0]
            if isinstance(best, list):
                best = best[0]
            label = best.get("label", "").lower()
            confidence = best.get("score", 0.0)
        else:
            return 0.0, "error", 0.0

        if "pos" in label:
            score = confidence
            label = "positive"
        elif "neg" in label:
            score = -confidence
            label = "negative"
        else:
            score = 0.0
            label = "neutral"

        return score, label, confidence
    except Exception as e:
        logger.error("Scoring error: %s", e, exc_info=True)
        return 0.0, "error", 0.0
