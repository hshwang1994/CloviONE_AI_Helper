"""문서 태깅 백업 (분류 구조 개편 전 원본 보존 — 되돌림용).

현재 "문서" DB 110개의 제목·유형·카테고리·프로젝트·작성자·소유자·상태를 그대로 JSON으로
떠서 docs/migration_backups/team_docs_tagging_backup.json 에 저장한다. 개편이 잘못되면
이 파일로 각 문서의 원래 relation을 복원할 수 있다.
"""

import os
import json
from pathlib import Path

import httpx

# 토큰은 환경변수로만 읽는다(하드코딩 금지). 예: NOTION_DOCS_TOKEN=ntn_... python team_docs_tagging_backup.py
TOKEN = os.environ.get("NOTION_DOCS_TOKEN", "")
H = {"Authorization": "Bearer " + TOKEN, "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
BASE = "https://api.notion.com/v1"
DOCS = "55efc3c0b58341a5b8d17f31fc2b152c"
OUT = Path(__file__).with_name("team_docs_tagging_backup.json")


def query_all(dbid):
    rows, cursor = [], None
    while True:
        b = {"page_size": 100}
        if cursor:
            b["start_cursor"] = cursor
        r = httpx.post(f"{BASE}/databases/{dbid}/query", headers=H, json=b, timeout=30).json()
        rows += r.get("results", [])
        if not r.get("has_more"):
            break
        cursor = r.get("next_cursor")
    return rows


def title_of(page):
    for v in page.get("properties", {}).values():
        if v.get("type") == "title":
            return "".join(s.get("plain_text", "") for s in v.get("title", []))
    return ""


schema = httpx.get(f"{BASE}/databases/{DOCS}", headers=H, timeout=30).json()["properties"]


def reldb(name):
    p = schema.get(name, {})
    return p.get("relation", {}).get("database_id") if p.get("type") == "relation" else None


def titles(dbid):
    return {pg["id"]: title_of(pg).strip() for pg in query_all(dbid)} if dbid else {}


type_map = titles(reldb("유형"))
cat_map = titles(reldb("카테고리"))
proj_map = titles(reldb("프로젝트"))

docs = query_all(DOCS)
backup = []
for d in docs:
    p = d["properties"]
    tids = [r["id"] for r in p.get("유형", {}).get("relation", [])]
    cids = [r["id"] for r in p.get("카테고리", {}).get("relation", [])]
    pids = [r["id"] for r in p.get("프로젝트", {}).get("relation", [])]
    backup.append({
        "page_id": d["id"],
        "title": title_of(d),
        "url": d.get("url"),
        "type_ids": tids, "type_names": [type_map.get(i, "") for i in tids],
        "category_ids": cids, "category_names": [cat_map.get(i, "") for i in cids],
        "project_ids": pids, "project_names": [proj_map.get(i, "") for i in pids],
        "author_names": [x.get("name") for x in p.get("작성자", {}).get("people", []) if x.get("name")],
        "owner": "".join(s.get("plain_text", "") for s in p.get("소유자", {}).get("rich_text", [])),
        "status": (p.get("상태", {}).get("select") or {}).get("name"),
    })

OUT.write_text(json.dumps({
    "database_id": DOCS,
    "type_options": type_map, "category_options": cat_map, "project_options": proj_map,
    "documents": backup,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"BACKUP_OK {len(backup)} docs -> {OUT}")
print(f"type options: {len(type_map)}, category options: {len(cat_map)}, project options: {len(proj_map)}")
