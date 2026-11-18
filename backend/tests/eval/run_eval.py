"""Offline matching-quality evaluation.

Runs the exact production pipeline minus the database: rule-based extraction -> embedding ->
score_pair -> rank. Reports recall@1 / recall@3 / MRR on queries whose item is in the pool,
and the false-notification rate on queries whose item is NOT in the pool.

    python -m tests.eval.run_eval                       # hashing embedder
    python -m tests.eval.run_eval --embedder sentence_transformers
    python -m tests.eval.run_eval --min-recall-at-3 0.85  # CI quality gate (exit 1 if below)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.extraction import embedding_text, extract_brand, extract_colors, extract_item
from app.domain.matching import GeoPoint, MatchConfig, MatchSubject, ScoreResult, rank
from app.integrations.embeddings import get_embedder

BASE = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
CASES = Path(__file__).with_name("cases.json")


@dataclass
class Metrics:
    recall_at_1: float
    recall_at_3: float
    mrr: float
    false_notify_rate: float
    notify_precision: float
    n_positive: int
    n_negative: int


def _subject(sid: str, text: str, loc: dict[str, float] | None, loc_id: str | None,
             start: datetime, end: datetime, vec: list[float]) -> MatchSubject:
    category, item_type, _ = extract_item(text)
    return MatchSubject(
        id=sid, category=category, item_type=item_type,
        colors=tuple(extract_colors(text)), brand=extract_brand(text), embedding=vec,
        location_id=loc_id, geo=GeoPoint(loc["lat"], loc["lng"]) if loc else None,
        occurred_from=start, occurred_to=end,
    )


def evaluate(embedder_name: str, notify_threshold: float, verbose: bool) -> Metrics:
    data = json.loads(CASES.read_text())
    locs = data["locations"]
    emb = get_embedder(embedder_name)
    cfg = MatchConfig(calibration=emb.calibration)

    def etext(text: str) -> str:
        cat, typ, _ = extract_item(text)
        return embedding_text(title=None, description=text, item_type=typ, category=cat,
                              colors=extract_colors(text), brand=extract_brand(text))

    found_texts = [f"{f['title']}. {f['description']}" for f in data["found"]]
    found_vecs = emb.embed([etext(t) for t in found_texts])
    pool = []
    for f, text, vec in zip(data["found"], found_texts, found_vecs, strict=True):
        at = BASE + timedelta(hours=f["t"])
        # Finders choose a location from a list, so items carry both id and geo.
        pool.append(_subject(f["id"], text, locs[f["loc"]], f["loc"], at, at, vec))

    lost_vecs = emb.embed([etext(q["text"]) for q in data["lost"]])
    hits1 = hits3 = 0
    rr = 0.0
    pos = neg = false_notify = notified = notified_correct = 0
    for q, vec in zip(data["lost"], lost_vecs, strict=True):
        # Owners often only know the area, not the exact room: give them geo, no location id.
        lost = _subject(q["id"], q["text"], locs.get(q["loc"]), None,
                        BASE + timedelta(hours=q["from"]), BASE + timedelta(hours=q["to"]), vec)
        ranked: list[ScoreResult] = rank(lost, pool, cfg, min_score=0.0, limit=10)
        top_ids = [r.found_id for r in ranked]
        top = ranked[0] if ranked else None
        if top and top.total >= notify_threshold:
            notified += 1
            notified_correct += int(top.found_id == q["expected"])
        if q["expected"] is None:
            neg += 1
            if top and top.total >= notify_threshold:
                false_notify += 1
        else:
            pos += 1
            if top_ids[:1] == [q["expected"]]:
                hits1 += 1
            if q["expected"] in top_ids[:3]:
                hits3 += 1
            if q["expected"] in top_ids:
                rr += 1 / (top_ids.index(q["expected"]) + 1)
        if verbose:
            mark = "  " if q["expected"] in top_ids[:1] or (q["expected"] is None and not (
                top and top.total >= notify_threshold)) else "XX"
            show = ", ".join(f"{r.found_id}:{r.total:.2f}" for r in ranked[:3])
            print(f"{mark} {q['id']} expected={q['expected']!s:5} top3=[{show}]  {q['text']}")

    return Metrics(
        recall_at_1=hits1 / pos, recall_at_3=hits3 / pos, mrr=rr / pos,
        false_notify_rate=false_notify / neg if neg else 0.0,
        notify_precision=notified_correct / notified if notified else 1.0,
        n_positive=pos, n_negative=neg,
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--embedder", default="hashing")
    p.add_argument("--notify-threshold", type=float, default=0.70)
    p.add_argument("--min-recall-at-3", type=float, default=None)
    p.add_argument("-q", "--quiet", action="store_true")
    args = p.parse_args()

    m = evaluate(args.embedder, args.notify_threshold, verbose=not args.quiet)
    print(
        f"\nembedder={args.embedder} positives={m.n_positive} negatives={m.n_negative}\n"
        f"recall@1={m.recall_at_1:.3f}  recall@3={m.recall_at_3:.3f}  MRR={m.mrr:.3f}\n"
        f"notify precision={m.notify_precision:.3f}  "
        f"false-notify rate (item not in pool)={m.false_notify_rate:.3f}"
    )
    if args.min_recall_at_3 is not None and m.recall_at_3 < args.min_recall_at_3:
        print(f"FAIL: recall@3 {m.recall_at_3:.3f} < {args.min_recall_at_3}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
