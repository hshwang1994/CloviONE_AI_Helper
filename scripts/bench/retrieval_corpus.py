# -*- coding: utf-8 -*-
"""S10 — 융합 가중치를 재려면 먼저 **실 한국어 본문과 정답이 있는 질의**가 있어야 한다.

    python scripts/bench/retrieval_corpus.py <출력 디렉터리> [--docs docs]

## 왜 미러(`web.sqlite3`)를 안 쓰는가 — 그 본문이 **없다**

S1 의 Corpus 는 `search_documents`(제목 + 부제 + 짧은 본문)였고 중앙값이 96자였다.
S10 이 재야 하는 것은 **긴 본문에서의 융합**이라 그 Corpus 로는 못 잰다. 그리고 실제로
본문이 없다 — 실측(2026-08-23):

    개발 사본  document_cache 본문 0건 · ticket_cache 본문 1건(38자)
    운영 서버  document_cache 본문 0건 · ticket_cache 본문 31건(7,630자)

Notion 동기화 셋이 전부 실패 상태이고, 본문이 실려 오는 것은 **S13** 이다. 그래서
「실 본문으로 쟀다」고 적을 수 없는 축은 적지 않고, 잴 수 있는 축만 잰다.

## 그래서 무엇으로 재는가 — 이 저장소의 한국어 문서

`docs/**/*.md` 는 **사람이 쓴 진짜 한국어 산문**이고 길다. 조사·접미가 어절에 붙는
성질도, 어절 내부 부분일치가 기본인 성질도 그대로다 — D-209 가 재는 것이 정확히 그
성질이다. 합성 문장이 아니라는 것이 중요하다(`scripts/bench/README.md` 의 R5 주석).

**한계는 결과 JSON 에 적는다**: 이 글은 업무 기록이 아니라 기술 문서다. 어휘 분포가
티켓·회의록과 다르므로 **모델 사이 · 가중치 사이의 비교**로만 읽고 절대값으로 읽지 않는다.

## 질의 세 종류 — 하나만 쓰면 한 레인만 이긴다

* **`span`(어절 경계 부분구간)** — chunk 안의 연속 구간을 어절 경계에서 딴다. 사람이
  문장을 복사해 넣는 모양이다.
* **`infix`(어절 **내부** 부분구간)** — 어절 중간에서 시작하거나 끝나는 연속 구간이다.
  🔴 **D-209 가 재고 결론을 낸 바로 그 질의군**이다: 한국어는 조사·접미가 어절에 붙어서
  어절 내부 부분일치가 예외가 아니라 기본이고, PG 전문검색은 그것을 사실상 못 한다
  (recall 0.083). 이 종류를 빼면 「FTS 가 이긴다」는 잘못된 결론이 나온다 — S10 이
  실제로 한 번 그렇게 뽑았다.
* **`recall`(기억나는 대로)** — 한 문장에서 어절을 절반쯤 버리고 순서를 섞는다. 연속
  구간이 깨져 트라이그램의 통짜 가지가 안 걸린다.

정답은 셋 다 **그 chunk 하나**다.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.ai import chunking  # noqa: E402  (제품의 chunk 규칙을 그대로 쓴다)
from app.ai.models import ANCHOR_TEXT  # noqa: E402
from app.ai.parsing.base import ParsedUnit  # noqa: E402

SEED = 20260823
#: 질의 종류마다 이만큼. 둘 합쳐 400개면 recall 의 표준오차가 2.5%p 아래다.
QUERIES_PER_KIND = 200
#: 부분구간 질의의 글자 수. 3자 미만은 트라이그램 인덱스를 못 타서 다른 것을 재게 된다.
SPAN_MIN_CHARS = 8
SPAN_MAX_CHARS = 24
#: 「기억나는 대로」 질의가 남기는 어절 비율.
RECALL_KEEP = 0.5

_CODE_FENCE = re.compile(r"^```", re.M)
_HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_MD_NOISE = re.compile(r"[`*_>#|\[\]()]+")
_TABLE_ROW = re.compile(r"^\s*\|")
_HANGUL = re.compile(r"[가-힣]")


def _plain(markdown: str) -> list[str]:
    """마크다운 → 문단 목록. **표와 코드 블록은 버린다.**

    표는 한 줄에 서로 관계없는 낱말이 몰려 있어 질의를 뽑으면 사람이 절대 안 치는 글이
    나온다. 코드 블록은 한국어가 아니다 — 그것으로 한국어 검색을 재면 안 된다.
    """
    body = _HTML_COMMENT.sub("", markdown)
    out: list[str] = []
    buffer: list[str] = []
    in_code = False
    for line in body.splitlines():
        if _CODE_FENCE.match(line):
            in_code = not in_code
            continue
        if in_code or _TABLE_ROW.match(line):
            continue
        clean = _MD_NOISE.sub(" ", line).strip()
        if not clean:
            if buffer:
                out.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(clean)
    if buffer:
        out.append(" ".join(buffer))
    # 한글이 거의 없는 문단(경로 목록·영문 로그)은 이 측정의 대상이 아니다.
    return [p for p in out if len(_HANGUL.findall(p)) >= max(10, len(p) * 0.2)]


def build_chunks(doc_root: Path) -> list[dict]:
    """문서 하나 = 파일 하나. chunk 는 **제품 chunker** 가 만든다."""
    rows: list[dict] = []
    for path in sorted(doc_root.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        paragraphs = _plain(path.read_text(encoding="utf-8"))
        if not paragraphs:
            continue
        units = [
            ParsedUnit(
                anchor_kind=ANCHOR_TEXT, anchor_ref=str(index), anchor_label="",
                text=text, ordinal=index,
            )
            for index, text in enumerate(paragraphs)
        ]
        for ordinal, chunk in enumerate(chunking.chunk_units(units, merge_anchors=True)):
            rows.append({
                "id": f"{rel}#{ordinal}",
                "document": rel,
                "title": path.stem,
                "ordinal": ordinal,
                "text": chunk.text,
            })
    return rows


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。？！])\s+|(?<=다)\.\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def make_span_query(rng: random.Random, text: str) -> str | None:
    """chunk 안의 연속 구간. 어절 경계에서 자른다 — 글자 중간에서 자르면 사람이 안 치는 글이다."""
    words = text.split()
    if len(words) < 4:
        return None
    for _ in range(8):
        start = rng.randrange(0, len(words) - 1)
        picked: list[str] = []
        for word in words[start:]:
            picked.append(word)
            if len(" ".join(picked)) >= SPAN_MIN_CHARS:
                break
        query = " ".join(picked)
        if SPAN_MIN_CHARS <= len(query) <= SPAN_MAX_CHARS and _HANGUL.search(query):
            return query
    return None


def make_infix_query(rng: random.Random, text: str) -> str | None:
    """🔴 **어절 중간에서 시작하거나 끝나는** 연속 구간 (D-209 가 재는 그 질의군).

    양끝이 둘 다 어절 경계면 `span` 과 같은 것을 재게 되므로, 적어도 한쪽은 어절
    안쪽이어야 한다. 앞뒤 문자가 공백이 아닌지로 확인한다.
    """
    body = " ".join(text.split())
    if len(body) < SPAN_MIN_CHARS + 4:
        return None
    for _ in range(24):
        length = rng.randint(SPAN_MIN_CHARS, min(SPAN_MAX_CHARS, len(body) - 2))
        start = rng.randrange(1, len(body) - length)
        query = body[start:start + length]
        if query != query.strip():
            continue
        inside_left = body[start - 1] != " "
        inside_right = body[start + length] != " " if start + length < len(body) else False
        if not (inside_left or inside_right):
            continue
        if not _HANGUL.search(query):
            continue
        return query
    return None


def make_recall_query(rng: random.Random, text: str) -> str | None:
    """한 문장에서 어절 절반을 버리고 순서를 섞는다. **연속 구간이 깨지는 것이 요점이다.**"""
    for sentence in rng.sample(_sentences(text), min(4, len(_sentences(text)) or 1)) or []:
        words = [w for w in sentence.split() if _HANGUL.search(w)]
        if len(words) < 5:
            continue
        keep = max(3, int(len(words) * RECALL_KEEP))
        picked = rng.sample(words, keep)
        rng.shuffle(picked)
        query = " ".join(picked)
        if SPAN_MIN_CHARS <= len(query) <= SPAN_MAX_CHARS * 2:
            return query
    return None


def build_queries(rng: random.Random, chunks: list[dict]) -> list[dict]:
    """질의 목록. **정답이 유일한 것만 남긴다.**

    같은 문장이 두 chunk 에 있으면 「맞았다」가 애매해진다 — 그런 질의는 버린다.
    측정이 애매한 표본을 안고 가면 그 애매함이 그대로 가중치가 된다.
    """
    pool = [c for c in chunks if len(c["text"]) >= 120]
    #: 부분구간 질의는 chunk 안에 그대로 들어 있으므로, 원문에 그 글자열이 있는 chunk 를
    #: 세어 **정답이 하나인 것만** 남긴다. 어절 사이 공백은 chunk 마다 다를 수 있어
    #: 정규화한 본문에서 센다.
    flat = {c["id"]: " ".join(c["text"].split()) for c in chunks}
    out: list[dict] = []
    makers = (
        ("span", make_span_query),
        ("infix", make_infix_query),
        ("recall", make_recall_query),
    )
    for kind, maker in makers:
        made: dict[str, dict] = {}
        for chunk in rng.sample(pool, len(pool)):
            if len(made) >= QUERIES_PER_KIND:
                break
            query = maker(rng, chunk["text"])
            if not query or query in made:
                continue
            if kind in ("span", "infix"):
                hits = [key for key, body in flat.items() if query in body]
                if hits != [chunk["id"]]:
                    # 부분구간이 두 곳에 있으면 정답이 하나가 아니다.
                    continue
            made[query] = {"kind": kind, "query": query, "gold": chunk["id"]}
        out.extend(made.values())
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    parser.add_argument("--docs", default="docs")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    chunks = build_chunks(ROOT / args.docs)
    queries = build_queries(rng, chunks)

    _write(out_dir / "chunks.jsonl", chunks)
    _write(out_dir / "queries.jsonl", queries)

    lengths = sorted(len(c["text"]) for c in chunks)
    summary = {
        "seed": SEED,
        "chunks": len(chunks),
        "documents": len({c["document"] for c in chunks}),
        "chunk_chars": {
            "min": lengths[0], "p50": lengths[len(lengths) // 2],
            "p90": lengths[int(len(lengths) * 0.9)], "max": lengths[-1],
            "sum": sum(lengths),
        },
        "queries": {
            kind: sum(1 for q in queries if q["kind"] == kind)
            for kind in ("span", "infix", "recall")
        },
    }
    (out_dir / "corpus_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for sample in queries[:2] + queries[-2:]:
        print(f"  [{sample['kind']}] {sample['query']}  <- {sample['gold']}")
    return 0


def _write(path: Path, rows) -> None:
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
