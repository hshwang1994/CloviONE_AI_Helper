# -*- coding: utf-8 -*-
"""S1 / P-03 — 벤치 Corpus 를 JSONL 로 뽑는다.

정본은 `search_documents`(검색이 실제로 보는 평평한 사본)이고, 본문이 캐시된 티켓·문서는
`*_cache.body_markdown` 에서 이어 붙인다. **실 데이터다** — 합성 문장으로 재면 한국어
부분일치 성능을 못 잰다(R5).
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys

db = sys.argv[1] if len(sys.argv) > 1 else "var/web.sqlite3"
out = sys.argv[2] if len(sys.argv) > 2 else "corpus.jsonl"

con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
con.text_factory = str

ticket_body = {r[0]: r[1] for r in con.execute(
    "select notion_page_id, body_markdown from ticket_cache "
    "where body_markdown is not null and body_markdown <> ''")}
doc_body = {r[0]: r[1] for r in con.execute(
    "select notion_page_id, body_markdown from document_cache "
    "where body_markdown is not null and body_markdown <> ''")}

rows = []
for (sid, kind, ref_id, title, subtitle, body, route) in con.execute(
        "select id, kind, ref_id, title, subtitle, body, route from search_documents"):
    extra = ticket_body.get(ref_id) or doc_body.get(ref_id) or ""
    text = "\n".join(x for x in (title or "", subtitle or "", body or "", extra) if x).strip()
    rows.append({"id": sid, "kind": kind, "title": title or "",
                 "subtitle": subtitle or "", "body": (body or ""),
                 "extra_len": len(extra), "text": text, "route": route or ""})

with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")

lens = sorted(len(r["text"]) for r in rows)
by_kind: dict[str, int] = {}
for r in rows:
    by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
print("rows=%d  kinds=%s" % (len(rows), by_kind))
print("본문 이어붙인 행: %d" % sum(1 for r in rows if r["extra_len"]))
print("text 길이 — min=%d p50=%d p90=%d max=%d 합계=%d"
      % (lens[0], lens[len(lens) // 2], lens[int(len(lens) * 0.9)], lens[-1], sum(lens)))
