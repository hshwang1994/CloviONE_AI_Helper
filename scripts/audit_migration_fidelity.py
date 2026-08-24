"""이관이 끝났는가를 **행 수가 아니라 내용**으로 판정한다 (S14 수락 증거).

## 왜 행 수로는 안 되는가

`documents` 110행과 `document_versions` 110행은 이관 보고서가 자랑하던 숫자다. 그런데
그 110건의 본문에는 표 93개와 이미지 49개가 있던 자리에 `[원본에서 확인: table]` 이라는
한 줄이 대신 들어 있었고, 문서 34건의 프로젝트 관계는 아예 옮겨 오지 않았다. 행 수는
110 = 110 이라 초록이었다. **행 수는 「무엇이 들어 있는가」를 묻지 않는다.**

그래서 이 도구는 원본 캐시(`var/migration-cache/cache/`)와 대상 데이터베이스를 **축마다**
세어, 「원본에 값이 있는데 우리 쪽에 없는 것」만 손실로 낸다.

## 세 가지 판정만 낸다

| 판정 | 뜻 |
|---|---|
| `ok` | 원본에 값이 있고 우리 쪽에도 같은 값이 있다 |
| `lost` | 원본에 값이 있는데 우리 쪽에 없거나 다르다 |
| `by_design` | 우리가 **알고 다르게** 만든 것이다. 이름이 붙어 있고 실패로 세지 않는다 |
| `not_audited` | 원본에 그 축의 자료가 없어 **비교 자체를 못 했다**. 조용히 통과시키지 않는다 |

**원본이 비어 있으면 우리도 비어 있는 것이 정답이다.** 그래서 모든 축은 「원본에 값이
있던 행」만 `checked` 로 세고, 그 수를 출력에 반드시 싣는다 — 0건을 훑고 초록을 찍는
것이 이 도구가 낼 수 있는 가장 나쁜 답이기 때문이다.

## 설계상 차이는 데이터로 판정한다. 예외 목록을 믿지 않는다

「다중 상위 작업」은 이관 보고서에 예외로 적혀 있다는 이유로 봐주는 것이 아니라,
**원본의 부모가 둘 이상이었다는 사실**을 이 도구가 직접 세어 봐 준다. 미매핑 작성자도
`user_notion_mappings` 의 검증된 목록에 그 Notion 사용자가 없다는 사실로 판정한다.
보고서를 근거로 삼으면 보고서에 한 줄 적는 것만으로 손실이 사라진다.

## 대상에는 **읽기만** 한다

대상 조회는 `SELECT` 한 문장이다(`build_target_query`). 붙는 경로가 둘인데 질의는
하나다 — 하나가 낡으면 두 판정이 갈리기 때문이다.

  * `--database-url` … SQLAlchemy 로 직접 붙는다. 트랜잭션을 읽기 전용으로 세우고
    커밋하지 않는다.
  * `--emit-target-sql` … 같은 문장을 psql 스크립트로 찍는다. 운영처럼 밖에서 못 붙는
    데이터베이스는 서버에서 이 문장만 돌려 JSON 을 받아 오고, `--target-json` 으로 먹인다.

## 쓰는 법

    python scripts/audit_migration_fidelity.py --database-url postgresql://...
    python scripts/audit_migration_fidelity.py --target-json snapshot.json
    python scripts/audit_migration_fidelity.py --emit-target-sql > q.sql
    python scripts/audit_migration_fidelity.py --target-json snapshot.json --json out.json
    python scripts/audit_migration_fidelity.py --source-only

판정을 내는 실행은 마지막 줄이 언제나 `FIDELITY_OK` 또는 `FIDELITY_FAILED` 이고 종료
코드가 그것을 따른다. `--emit-target-sql` 과 `--dump-target` 은 아무것도 안 세므로 그
줄을 찍지 않는다 — 세지 않고 찍은 초록은 나중에 증거로 읽힌다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# 한글 표를 찍으므로 콘솔 코드페이지에 맡기지 않는다. 저장소의 다른 검사 도구와 같은 관용이다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_CACHE = REPO / "var" / "migration-cache" / "cache"
DEFAULT_REPORT = REPO / "var" / "migration-cache" / "report" / "report.json"

__all__ = [
    "ST_OK", "ST_LOST", "ST_BY_DESIGN", "ST_NOT_AUDITED",
    "BD_SINGLE_PARENT", "BD_UNMAPPED_AUTHOR", "BD_ATTACHMENT_LIMIT",
    "BD_ATTACHMENT_EXTERNAL", "BD_SOURCE_MISSING",
    "AxisResult", "Report",
    "collect_source", "build_target_query", "emit_target_sql", "fetch_target",
    "audit", "render_table", "main",
]

# ── 판정 이름 ────────────────────────────────────────────────────────────────

ST_OK = "ok"
ST_LOST = "lost"
ST_BY_DESIGN = "by_design"
ST_NOT_AUDITED = "not_audited"

# 설계상 차이의 이름. **이름 없는 봐주기를 만들지 않는다** — 여기 없는 이유로는 어떤
# 손실도 면제되지 않는다.
BD_SINGLE_PARENT = "single_parent"
BD_UNMAPPED_AUTHOR = "unmapped_author"
BD_ATTACHMENT_LIMIT = "attachment_limit"
BD_ATTACHMENT_EXTERNAL = "attachment_external_link"
BD_SOURCE_MISSING = "source_missing"

BY_DESIGN_WHY = {
    BD_SINGLE_PARENT:
        "uq_trel_single_parent 가 하위 작업의 부모를 하나로 강제한다 (D8).",
    BD_UNMAPPED_AUTHOR:
        "포털 사용자와 이어지지 않은 Notion 사용자다. 이름으로 추측 매칭하지 않는다 (D9).",
    BD_ATTACHMENT_LIMIT:
        "제품의 업로드 상한(10MB)을 넘는 파일이다. 이관 때문에 상한을 넓히지 않는다.",
    BD_ATTACHMENT_EXTERNAL:
        "바깥 링크라 원본에도 바이트가 없다. 내려받을 것이 애초에 없다.",
    BD_SOURCE_MISSING:
        "우리에만 있는 행이다. 원본 응답에 없어 migration_exceptions 에 분류돼 있다.",
}

# 본문 글자가 이 비율보다 적으면 손실로 본다. 완전 일치를 요구하지 않는 이유는 마크다운
# 변환이 공백과 구분자를 다르게 놓기 때문이고, 그 차이는 낱말 글자 수에 안 잡힌다.
DEFAULT_BODY_RATIO = 0.90

# 자리표시자. `transform.notion_blocks_to_doc` 가 표현 못 하는 블록에 남기는 한 줄이다.
PLACEHOLDER_RE = re.compile(r"\[원본에서 확인: ?([A-Za-z0-9_]+)\]")

# 낱말 글자만 센다. 마크다운의 `#`·`-`·`|`·`[]()` 같은 구분자를 양쪽에서 함께 지워야
# 「본문이 얼마나 남았는가」가 서식 차이에 안 흔들린다.
_WORD_RE = re.compile(r"[^\W_]", re.UNICODE)

# 본문 노드로 계약에 있는 블록. 여기 있는 종류가 원본보다 적으면 **손실이다**.
# 나머지(컬럼·동기화 블록·하위 페이지 …)는 우리 스키마에 자리가 없어 자리표시자로
# 남고, 그 사실은 `*.placeholder` 축이 따로 센다.
CONTRACT_BLOCKS = {
    "image": "image",
    "table": "table",
    "table_row": "tableRow",
    "code": "codeBlock",
}


# ── 결과 ─────────────────────────────────────────────────────────────────────


@dataclass
class AxisResult:
    """축 하나의 판정.

    `checked` 를 필드로 들고 다니는 이유는 출력에서 뺄 수 없게 하려는 것이다.
    0 건을 비교하고 `lost=0` 을 내는 축은 초록이 아니라 **아무것도 안 본 축**이다.
    """

    key: str
    group: str
    label: str
    checked: int = 0
    lost: int = 0
    by_design: int = 0
    by_design_reasons: dict[str, int] = field(default_factory=dict)
    samples: list[str] = field(default_factory=list)
    note: str = ""
    audited: bool = True
    source_total: int | None = None
    target_total: int | None = None

    @property
    def ok(self) -> int:
        return self.checked - self.lost - self.by_design

    @property
    def status(self) -> str:
        if not self.audited:
            return ST_NOT_AUDITED
        if self.lost:
            return ST_LOST
        if self.by_design:
            return ST_BY_DESIGN
        return ST_OK

    def as_dict(self) -> dict:
        return {
            "key": self.key, "group": self.group, "label": self.label,
            "status": self.status, "checked": self.checked, "ok": self.ok,
            "lost": self.lost, "by_design": self.by_design,
            "by_design_reasons": dict(self.by_design_reasons),
            "samples": list(self.samples), "note": self.note,
            "source_total": self.source_total, "target_total": self.target_total,
        }


@dataclass
class Report:
    axes: list[AxisResult] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extras: dict = field(default_factory=dict)

    def add(self, axis: AxisResult) -> AxisResult:
        self.axes.append(axis)
        return axis

    @property
    def total_lost(self) -> int:
        return sum(axis.lost for axis in self.axes)

    @property
    def total_checked(self) -> int:
        return sum(axis.checked for axis in self.axes)

    @property
    def passed(self) -> bool:
        return self.total_lost == 0

    @property
    def verdict(self) -> str:
        return "FIDELITY_OK" if self.passed else "FIDELITY_FAILED"

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "passed": self.passed,
            "total_checked": self.total_checked,
            "total_lost": self.total_lost,
            "total_by_design": sum(axis.by_design for axis in self.axes),
            "not_audited": [a.key for a in self.axes if not a.audited],
            "axes": [axis.as_dict() for axis in self.axes],
            "blocks": list(self.blocks),
            "notes": list(self.notes),
            "extras": dict(self.extras),
        }


# ── 잔손 ─────────────────────────────────────────────────────────────────────


def _words(text: str | None) -> int:
    """낱말 글자 수. 자리표시자는 **빼고** 센다.

    자리표시자를 그대로 세면 「표가 사라진 문서」가 글자 수로는 멀쩡해 보인다.
    """
    if not text:
        return 0
    return len(_WORD_RE.findall(PLACEHOLDER_RE.sub(" ", text)))


def _norm_text(value) -> str:
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFC", str(value)).split())


def _norm_num(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _norm_date(value) -> str:
    if value in (None, ""):
        return ""
    return str(value)[:10]


def _norm_dt(value) -> str:
    """`2026-08-12T02:40:00.000Z` 와 `2026-08-12 02:40:00` 을 같은 글자로 만든다."""
    if value in (None, ""):
        return ""
    text = str(value).strip().replace("T", " ")
    text = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", "", text)
    return text[:19]


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _split_names(joined: str | None) -> list[str]:
    return [part for part in (joined or "").split("\x1f") if part.strip()]


def _node_census(node, out: dict[str, int] | None = None) -> dict[str, int]:
    """Block JSON 안의 노드 종류를 센다."""
    out = {} if out is None else out
    if isinstance(node, dict):
        kind = node.get("type")
        if isinstance(kind, str):
            out[kind] = out.get(kind, 0) + 1
        for value in node.values():
            _node_census(value, out)
    elif isinstance(node, list):
        for item in node:
            _node_census(item, out)
    return out


def _cell_words(node) -> int:
    """표 칸 안의 낱말 글자 수."""
    total = 0
    if isinstance(node, dict):
        if node.get("type") in ("tableCell", "tableHeader"):
            return _text_words_of_node(node)
        for value in node.values():
            total += _cell_words(value)
    elif isinstance(node, list):
        for item in node:
            total += _cell_words(item)
    return total


def _text_words_of_node(node) -> int:
    total = 0
    if isinstance(node, dict):
        if node.get("type") == "text":
            total += _words(node.get("text"))
        for value in node.values():
            total += _text_words_of_node(value)
    elif isinstance(node, list):
        for item in node:
            total += _text_words_of_node(item)
    return total


_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(")


def _md_census(markdown: str | None) -> dict[str, int]:
    """마크다운 본문의 이미지·표 세기.

    티켓 본문은 마크다운이라 노드 census 를 그대로 쓸 수 없다. 이미지는 문법으로,
    표는 `|` 로 시작하는 연속된 줄 묶음으로 센다.
    """
    text = markdown or ""
    rows = 0
    tables = 0
    run = 0
    fenced = False
    body_lines: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            if run >= 2:
                tables += 1
            run = 0
            continue
        if fenced:
            # 코드 블록 안의 `|` 로 시작하는 줄은 표가 아니다. 세면 보존율이 부풀고,
            # 부푼 보존율은 손실을 작아 보이게 만든다.
            continue
        body_lines.append(line)
        if line.strip().startswith("|"):
            run += 1
            rows += 1
        else:
            if run >= 2:
                tables += 1
            run = 0
    if run >= 2:
        tables += 1
    return {
        "image": len(_MD_IMAGE_RE.findall("\n".join(body_lines))),
        "table": tables,
        "tableRow": rows,
        "codeBlock": text.count("```") // 2,
    }


# ── 원본 ─────────────────────────────────────────────────────────────────────


def _md_table_words(markdown: str | None) -> int:
    """마크다운 표 칸의 낱말 글자 수. 코드 블록 안은 세지 않는다."""
    total = 0
    fenced = False
    for line in (markdown or "").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.strip().startswith("|"):
            total += _words(line)
    return total


def _walk_blocks(blocks):
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        yield block
        yield from _walk_blocks(block.get("_children"))


def _rich_words(parts) -> int:
    return sum(
        _words(seg.get("plain_text") or (seg.get("text") or {}).get("content"))
        for seg in (parts or [])
        if isinstance(seg, dict)
    )


def _block_words(block: dict) -> tuple[int, int]:
    """블록 하나의 (전체 낱말 글자, 표 칸 낱말 글자)."""
    kind = block.get("type") or ""
    holder = block.get(kind)
    holder = holder if isinstance(holder, dict) else {}
    total = _rich_words(holder.get("rich_text"))
    total += _rich_words(holder.get("caption"))
    cells = 0
    for row in holder.get("cells") or []:
        cells += _rich_words(row)
    return total + cells, cells


def _scan_blocks(blocks) -> dict:
    kinds: dict[str, int] = {}
    words = 0
    cell_words = 0
    for block in _walk_blocks(blocks):
        kind = block.get("type") or "?"
        kinds[kind] = kinds.get(kind, 0) + 1
        block_words, cells = _block_words(block)
        words += block_words
        cell_words += cells
    return {"kinds": kinds, "words": words, "cell_words": cell_words}


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_ledger(path: Path) -> dict[str, str]:
    """이관 보고서에서 **첨부 분류만** 꺼낸다: `{legacy_id: kind}`.

    보고서를 통째로 믿지 않으려고 읽는 범위를 여기서 좁힌다. 이 사전이 면제할 수 있는
    것은 「바이트가 왜 없는가」 하나뿐이고, 나머지 축은 보고서에 무엇이 적혀 있든 데이터로
    판정한다.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        payload = _load_json(path)
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for finding in payload.get("findings") or []:
        kind = finding.get("kind")
        ref = finding.get("ref")
        if ref and kind in ("attachment_rejected", "attachment_external_link"):
            out[ref] = kind
    return out


def load_target_json(path: Path):
    """psql 이 앞에 붙이는 안내 줄을 넘기고 JSON 한 덩이를 읽는다.

    `\\pset` 확인 줄과 `SET` 명령 태그가 앞에 섞여 들어오는 일이 흔하다. 그것 때문에
    스냅숏을 못 읽으면 사람이 파일을 손으로 자르게 되고, 손으로 자른 파일은 다음에 또
    다르게 잘린다.
    """
    text = Path(path).read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} 에 JSON 이 없습니다.")
    return json.loads(text[start:])


def collect_source(cache_dir: Path) -> dict:
    """원본 캐시 → 축마다 비교할 수 있는 납작한 사전.

    Notion 속성 이름을 여기서 다시 정하지 않고 `app.migration.transform` 을 쓴다 —
    이름은 실측으로 맞춰 둔 사실이고, 두 번째 정의를 만들면 그 둘이 갈린 날 어느 쪽이
    맞는지 아무도 모른다. 대신 **본문과 블록은 직접 센다**: 이관이 쓴 변환기로 기대값을
    만들면 「변환기가 버린 것」이 기대값에서도 함께 사라져 영원히 안 보인다.
    """
    from app.migration import transform  # 무거운 import 는 실제로 원본을 읽을 때만 한다.

    cache_dir = Path(cache_dir)
    documents = _load_json(cache_dir / "documents.json")
    tasks = _load_json(cache_dir / "tasks.json")
    taxonomy: dict[str, str] = {}
    for name in ("categories.json", "doc_types.json"):
        path = cache_dir / name
        if path.exists():
            taxonomy.update(transform.relation_titles(_load_json(path)))
    projects = _load_json(cache_dir / "projects.json") if (
        cache_dir / "projects.json").exists() else []

    blocks_dir = cache_dir / "blocks"
    scanned: dict[str, dict] = {}
    if blocks_dir.is_dir():
        for path in sorted(blocks_dir.glob("*.json")):
            payload = _load_json(path)
            raw = payload.get("blocks") if isinstance(payload, dict) else payload
            scanned[path.stem] = _scan_blocks(raw)

    def body_of(page_id: str) -> dict:
        # 캐시 파일 이름이 하이픈 있는 형태와 없는 형태로 섞여 있을 수 있다.
        return (
            scanned.get(page_id)
            or scanned.get(page_id.replace("-", ""))
            or {"kinds": {}, "words": 0, "cell_words": 0}
        )

    out_docs = []
    for raw in documents:
        parsed = transform.parse_document(raw)
        page_id = parsed["notion_page_id"] or ""
        body = body_of(page_id)
        out_docs.append({
            "page_id": page_id,
            "title": parsed["title"],
            "doc_type_names": [
                (taxonomy.get(tid) or "").strip()
                for tid in parsed["type_ids"] if (taxonomy.get(tid) or "").strip()
            ],
            "category_names": sorted({
                (taxonomy.get(cid) or "").strip()
                for cid in parsed["category_ids"] if (taxonomy.get(cid) or "").strip()
            }),
            "project_ids": parsed["project_ids"],
            "author_ids": parsed["author_notion_ids"],
            "author_names": parsed["author_names"],
            "created_time": _norm_dt(parsed["notion_created_time"]),
            "last_edited": _norm_dt(parsed["notion_last_edited"]),
            "attachments": [
                {"legacy_id": att.legacy_id, "name": att.name, "hosted": att.hosted}
                for att in transform.attachments_of(raw)
            ],
            "body_words": body["words"],
            "cell_words": body["cell_words"],
            "block_kinds": body["kinds"],
        })

    out_tickets = []
    for raw in tasks:
        parsed = transform.parse_task(raw)
        page_id = parsed["notion_page_id"] or ""
        body = body_of(page_id)
        relation = _prop_relations(raw, transform.TASK_PROPS["parent"])
        out_tickets.append({
            "page_id": page_id,
            "title": parsed["title"],
            "status": parsed["status"],
            "priority": parsed["priority"],
            "difficulty": parsed["difficulty"],
            "category": parsed["category"],
            "est_wd": parsed["est_wd"],
            "act_wd": parsed["act_wd"],
            "start_date": _norm_date(parsed["start_date"]),
            "due_date": _norm_date(parsed["due_date"]),
            "assignee_ids": parsed["assignee_notion_ids"],
            "project_ids": parsed["project_ids"],
            "created_time": _norm_dt(parsed["notion_created_time"]),
            "parent_ids": relation,
            "blocked_by": parsed["blocked_by_pages"],
            "blocks": parsed["blocks_pages"],
            "attachments": [
                {"legacy_id": att.legacy_id, "name": att.name, "hosted": att.hosted}
                for att in transform.attachments_of(raw)
            ],
            "body_words": body["words"],
            "cell_words": body["cell_words"],
            "block_kinds": body["kinds"],
        })

    return {
        "documents": out_docs,
        "tickets": out_tickets,
        "project_count": len(projects),
        "unread_properties": {
            "documents": _unread_properties(documents, transform.DOC_PROPS),
            "tasks": _unread_properties(tasks, transform.TASK_PROPS),
        },
    }


def _prop_relations(row: dict, name: str) -> list[str]:
    wanted = " ".join(unicodedata.normalize("NFC", name).split())
    for key, prop in (row.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        if " ".join(unicodedata.normalize("NFC", key).split()) != wanted:
            continue
        return [
            item["id"] for item in (prop.get("relation") or [])
            if isinstance(item, dict) and item.get("id")
        ]
    return []


def _unread_properties(rows: list[dict], mapped: dict[str, str]) -> list[dict]:
    """**우리가 안 읽는데 원본에는 값이 있는** 속성.

    문서 분류 110건이 조용히 비어 있던 원인이 정확히 이것이었다. 속성 이름이 안 맞으면
    Notion 은 오류를 내지 않고 그 키가 없는 응답을 준다. 손실로는 안 세지만 눈에는 띄게
    둔다 — 다음에 이름이 바뀌는 날 이 칸이 먼저 말한다.
    """
    known = {
        " ".join(unicodedata.normalize("NFC", name).split())
        for name in mapped.values()
    }
    counts: dict[str, int] = {}
    for row in rows:
        for key, prop in (row.get("properties") or {}).items():
            if not isinstance(prop, dict):
                continue
            norm = " ".join(unicodedata.normalize("NFC", key).split())
            if norm in known:
                continue
            kind = prop.get("type")
            # `files` 를 빼는 이유는 `attachments_of` 가 **이름을 안 보고 파일 속성을 전부**
            # 훑기 때문이다. 이름이 목록에 없다고 안 읽는 것이 아니다.
            if kind in (None, "files", "created_time", "last_edited_time",
                        "created_by", "last_edited_by", "unique_id", "formula",
                        "rollup", "button"):
                continue
            value = prop.get(kind)
            filled = bool(value) if isinstance(value, (list, dict)) else (
                value not in (None, "", False))
            if filled:
                counts[norm] = counts.get(norm, 0) + 1
    return [
        {"property": name, "filled_rows": count}
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


# ── 대상 ─────────────────────────────────────────────────────────────────────

_TARGET_PARTS: dict[str, str] = {
    # `to_jsonb(d)` 로 **행 전체**를 담는 이유는 스키마가 자라기 때문이다. 칸 이름을
    # 하나하나 적으면 새 칸이 생긴 날 감사기가 그 칸을 영원히 못 보고, 없는 칸을 적으면
    # 질의 자체가 선다. 파이썬 쪽은 없는 열쇠를 `None` 으로 읽는다.
    "documents": """
        SELECT to_jsonb(d) || jsonb_build_object(
                   'body', v.body,
                   'body_text', v.body_text,
                   'tag_names', (
                       SELECT coalesce(json_agg(tg.name ORDER BY tg.name), '[]'::json)
                         FROM document_tags dt JOIN tags tg ON tg.id = dt.tag_id
                        WHERE dt.document_id = d.id),
                   'attachment_count', (
                       SELECT count(*) FROM document_attachments da
                        WHERE da.document_id = d.id)
               ) AS row
          FROM documents d
          LEFT JOIN document_versions v ON v.id = d.current_version_id
    """,
    "tickets": """
        SELECT to_jsonb(t) || jsonb_build_object(
                   'comment_count', (
                       SELECT count(*) FROM ticket_comments c
                        WHERE c.ticket_uid = t.id AND c.deleted_at IS NULL),
                   'attachment_count', (
                       SELECT count(*) FROM ticket_attachments a
                        WHERE a.ticket_uid = t.id)
               ) AS row
          FROM tickets t
    """,
    "ticket_relations": """
        SELECT r.kind,
               f.notion_page_id AS from_page,
               o.notion_page_id AS to_page
          FROM ticket_relations r
          JOIN tickets f ON f.id = r.from_ticket_id
          JOIN tickets o ON o.id = r.to_ticket_id
    """,
    "spaces": """
        SELECT s.id, s.name, s.slug, s.owner_kind, s.owner_dept_id,
               s.owner_project_id, s.archived
          FROM knowledge_spaces s
    """,
    "user_notion_mappings": """
        SELECT m.notion_user_id, m.user_id, m.status FROM user_notion_mappings m
    """,
    "projects": """
        SELECT p.id, p.notion_page_id, p.name, p.code FROM projects p
    """,
    "files": """
        SELECT f.id, f.owner_ref, f.filename, f.size_bytes FROM files f
    """,
    "file_mappings": """
        SELECT lm.legacy_source_id, lm.target_id
          FROM legacy_mapping lm WHERE lm.target_type = 'file'
    """,
    "migration_exceptions": """
        SELECT e.ticket_id, e.reason, e.resolved_at::text AS resolved_at
          FROM migration_exceptions e
    """,
}

_TARGET_SCALARS: dict[str, str] = {
    "document_relations": "SELECT count(*) FROM document_relations",
    "folders": "SELECT count(*) FROM folders",
}


def build_target_query() -> str:
    """대상 전체를 **`SELECT` 한 문장**으로 뽑는다.

    한 문장인 이유는 두 가지다. 읽기 전용임을 눈으로 확인할 수 있고, psql 로 돌리든
    SQLAlchemy 로 돌리든 결과가 같은 JSON 하나라 판정 코드가 갈리지 않는다.
    """
    parts = []
    for name, sql in _TARGET_PARTS.items():
        # 이미 행 하나를 통째로 JSON 으로 만든 조각은 다시 감싸지 않는다.
        inner = "q.row" if "to_jsonb(" in sql else "row_to_json(q)"
        parts.append(
            f"'{name}', (SELECT coalesce(json_agg({inner}), '[]'::json) "
            f"FROM ({sql.strip()}) q)"
        )
    parts += [
        f"'{name}', ({sql})" for name, sql in _TARGET_SCALARS.items()
    ]
    return "SELECT json_build_object(\n  " + ",\n  ".join(parts) + "\n)::text"


def emit_target_sql() -> str:
    """psql 로 그대로 돌릴 수 있는 스크립트. 서버에서 읽기 전용으로 돌리는 길이다."""
    return (
        "-- 이관 정합성 감사기가 읽는 대상 스냅숏. SELECT 한 문장이고 아무것도 쓰지 않는다.\n"
        "-- 쓰는 법: psql -q -d <db> -At -f <이 파일> > snapshot.json\n"
        "\\set QUIET on\n"
        "\\pset format unaligned\n"
        "\\pset tuples_only on\n"
        "SET default_transaction_read_only = on;\n"
        f"{build_target_query()};\n"
    )


def _driver_url(database_url: str) -> str:
    """드라이버를 제품과 같게 맞춘다.

    `postgresql://` 로만 적힌 URL 을 SQLAlchemy 는 psycopg2 로 읽는데 이 제품은 psycopg3
    만 깐다. 정본은 `app.core.db.normalize_database_url` 이고, 저장소 밖에 이 파일만
    복사해 돌리는 경우를 위해 같은 규칙을 한 줄로 되풀이한다.
    """
    try:
        from app.core.db import normalize_database_url

        return normalize_database_url(database_url)
    except Exception:
        url = (database_url or "").strip()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


def fetch_target(database_url: str) -> dict:
    """대상 데이터베이스에 **읽기 전용으로** 붙어 스냅숏을 받는다."""
    import sqlalchemy as sa

    engine = sa.create_engine(_driver_url(database_url), future=True)
    try:
        with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            raw = conn.execute(sa.text(build_target_query())).scalar_one()
            conn.rollback()
    finally:
        engine.dispose()
    return json.loads(raw) if isinstance(raw, str) else raw


# ── 비교 ─────────────────────────────────────────────────────────────────────


def _brief(value, limit: int = 24) -> str:
    text = "(없음)" if not _present(value) else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _sample(axis: AxisResult, ref: str, limit: int) -> None:
    if len(axis.samples) < limit:
        axis.samples.append(ref)


def _mark_lost(axis: AxisResult, ref: str, limit: int) -> None:
    axis.lost += 1
    _sample(axis, ref, limit)


def _note_reason(axis: AxisResult, reason: str) -> None:
    """설계상 차이의 **까닭만** 적는다. 행 수는 안 움직인다.

    첨부 두 건이 같은 문서에 붙어 있으면 까닭은 두 번이지만 「그 문서 한 건」은 한 번이다.
    둘을 같은 칸에 더하면 `맞음 = 본 건수 - 손실 - 설계차` 가 음수로 간다.
    """
    axis.by_design_reasons[reason] = axis.by_design_reasons.get(reason, 0) + 1


def _mark_by_design(axis: AxisResult, reason: str) -> None:
    """행 하나를 설계상 차이로 센다."""
    axis.by_design += 1
    _note_reason(axis, reason)


def _scalar_axis(
    key: str, group: str, label: str, rows, *, source_of, target_of,
    normalize=_norm_text, samples: int = 5, note: str = "",
) -> AxisResult:
    """원본에 값이 있던 행만 비교하는 스칼라 축."""
    axis = AxisResult(key=key, group=group, label=label, note=note)
    for ref, source_row, target_row in rows:
        want = source_of(source_row)
        if not _present(want):
            continue
        axis.checked += 1
        got = target_of(target_row) if target_row is not None else None
        if normalize(want) != normalize(got):
            # 표본에 **두 값을 함께** 싣는다. id 만 있으면 무엇을 고쳐야 하는지 다시 캐야 한다.
            _mark_lost(axis, f"{ref} (원본 {_brief(want)} ≠ 대상 {_brief(got)})", samples)
    return axis


def _set_axis(
    key: str, group: str, label: str, rows, *, source_of, target_of,
    samples: int = 5, note: str = "", subset_ok: bool = False,
) -> AxisResult:
    """값이 여럿인 축. 원본 집합이 대상 집합에 **다 들어 있어야** 한다."""
    axis = AxisResult(key=key, group=group, label=label, note=note)
    for ref, source_row, target_row in rows:
        want = {_norm_text(v) for v in (source_of(source_row) or []) if _norm_text(v)}
        if not want:
            continue
        axis.checked += 1
        got = set()
        if target_row is not None:
            got = {_norm_text(v) for v in (target_of(target_row) or []) if _norm_text(v)}
        if subset_ok:
            if not (want & got):
                _mark_lost(axis, ref, samples)
        elif not want.issubset(got):
            _mark_lost(axis, ref, samples)
    return axis


def audit(
    source: dict, target: dict, *, ledger: dict | None = None, samples: int = 5,
    body_ratio: float = DEFAULT_BODY_RATIO,
) -> Report:
    """원본 사전과 대상 사전을 받아 판정한다. **순수 함수다** — DB 도 파일도 안 본다.

    `ledger` 는 이관 보고서가 남긴 `{첨부 legacy_id: 분류}` 다. **딱 한 자리에서만** 쓴다:
    바이트가 저장소에 없는 첨부가 「상한을 넘어 거절됐다」인지 「내려받다 실패했다」인지는
    원본만 봐서는 구별할 수 없고, 그 둘은 뜻이 정반대다. 없으면 전부 손실로 센다.
    """
    report = Report()
    ledger = dict(ledger or {})

    src_docs = list(source.get("documents") or [])
    src_tickets = list(source.get("tickets") or [])
    tgt_docs = {
        row.get("legacy_page_id"): row
        for row in (target.get("documents") or [])
        if row.get("legacy_page_id")
    }
    tgt_tickets = {
        row.get("notion_page_id"): row
        for row in (target.get("tickets") or [])
        if row.get("notion_page_id")
    }
    spaces = {row.get("id"): row for row in (target.get("spaces") or [])}
    verified_notion_users = {
        row.get("notion_user_id")
        for row in (target.get("user_notion_mappings") or [])
        if row.get("status") == "verified" and row.get("notion_user_id")
    }
    exception_reason = {
        row.get("ticket_id"): row.get("reason")
        for row in (target.get("migration_exceptions") or [])
    }
    file_by_legacy = {
        row.get("legacy_source_id"): row.get("target_id")
        for row in (target.get("file_mappings") or [])
    }

    doc_pairs = [(doc["page_id"], doc, tgt_docs.get(doc["page_id"])) for doc in src_docs]
    ticket_pairs = [
        (tk["page_id"], tk, tgt_tickets.get(tk["page_id"])) for tk in src_tickets
    ]

    _audit_documents(
        report, doc_pairs, spaces=spaces,
        verified=verified_notion_users, file_by_legacy=file_by_legacy,
        ledger=ledger, target=target, samples=samples, body_ratio=body_ratio,
    )
    _audit_tickets(
        report, ticket_pairs, target=target, file_by_legacy=file_by_legacy,
        ledger=ledger, samples=samples, body_ratio=body_ratio,
    )
    # 우리에만 있는 행. 손실은 아니지만 「원본 1,125 대상 1,133」이 설명 없이 남지 않게 한다.
    extra_tickets = [
        page for page in tgt_tickets
        if page not in {tk["page_id"] for tk in src_tickets}
    ]
    extra_axis = report.add(AxisResult(
        key="ticket.extra_rows", group="티켓", label="우리에만 있는 티켓",
        checked=len(extra_tickets),
        note="원본 응답에 없는 행이다. 손실이 아니라 분류된 예외인지 확인한다.",
        source_total=len(src_tickets), target_total=len(tgt_tickets),
    ))
    for page in extra_tickets:
        row = tgt_tickets[page]
        if exception_reason.get(row.get("id")) or row.get("notion_missing_at"):
            _mark_by_design(extra_axis, BD_SOURCE_MISSING)
        else:
            _mark_lost(extra_axis, page, samples)

    _audit_blocks(report, src_docs, src_tickets, tgt_docs, tgt_tickets)

    report.extras["unread_properties"] = source.get("unread_properties") or {}
    report.extras["counts"] = {
        "source_documents": len(src_docs),
        "source_tickets": len(src_tickets),
        "target_documents": len(target.get("documents") or []),
        "target_tickets": len(target.get("tickets") or []),
        "target_document_relations": target.get("document_relations"),
        "target_folders": target.get("folders"),
        "target_files": len(target.get("files") or []),
    }
    return report


def _audit_documents(
    report: Report, pairs, *, spaces, verified, file_by_legacy, ledger, target,
    samples: int, body_ratio: float,
) -> None:
    group = "문서"

    row_axis = report.add(AxisResult(
        key="doc.row", group=group, label="문서 행",
        checked=len(pairs),
        note="원본 문서 한 건마다 `documents.legacy_page_id` 로 짝을 찾는다.",
        source_total=len(pairs), target_total=len(target.get("documents") or []),
    ))
    for ref, _src, tgt in pairs:
        if tgt is None:
            _mark_lost(row_axis, ref, samples)

    report.add(_scalar_axis(
        "doc.title", group, "제목", pairs,
        source_of=lambda d: d["title"], target_of=lambda t: t.get("title"),
        samples=samples,
    ))

    # 본문. 「비었다」와 「줄었다」를 나눈다 — 둘은 고치는 방법이 다르다.
    empty_axis = report.add(AxisResult(
        key="doc.body_nonempty", group=group, label="본문 있음",
        note="원본에 글자가 있는 문서의 본문이 우리 쪽에서 0자가 아닌가.",
    ))
    shrink_axis = report.add(AxisResult(
        key="doc.body_chars", group=group, label="본문 글자",
        note=f"자리표시자를 뺀 낱말 글자가 원본의 {int(body_ratio * 100)}% 이상인가.",
    ))
    src_words = tgt_words = 0
    for ref, src, tgt in pairs:
        want = src["body_words"]
        if want <= 0:
            continue
        got = _words((tgt or {}).get("body_text"))
        src_words += want
        tgt_words += got
        empty_axis.checked += 1
        shrink_axis.checked += 1
        if got <= 0:
            _mark_lost(empty_axis, ref, samples)
        if got < want * body_ratio:
            _mark_lost(shrink_axis, ref, samples)
    shrink_axis.source_total = src_words
    shrink_axis.target_total = tgt_words

    # 작성자. 이어지지 않은 Notion 사용자는 **설계상 차이**다 (D9).
    author_axis = report.add(AxisResult(
        key="doc.author", group=group, label="작성자",
        note="검증된 Notion 사용자 매핑이 있는 작성자만 손실로 센다 (D9).",
    ))
    for ref, src, tgt in pairs:
        want = src["author_ids"]
        if not want:
            continue
        author_axis.checked += 1
        if not any(nid in verified for nid in want):
            _mark_by_design(author_axis, BD_UNMAPPED_AUTHOR)
        elif not (tgt or {}).get("created_by"):
            _mark_lost(author_axis, ref, samples)

    # 칸 이름을 하나로 못 박지 않는다. `legacy_created_at` 이 정본이고, 옛 이름도 함께
    # 본다 — 이름이 바뀌었다는 이유로 「값이 사라졌다」고 말하면 그것이 위양성이다.
    report.add(_scalar_axis(
        "doc.created_time", group, "원본 생성일", pairs,
        source_of=lambda d: d["created_time"],
        target_of=lambda t: _norm_dt(
            t.get("legacy_created_at") or t.get("notion_created_time")),
        samples=samples,
        note="`documents.legacy_created_at` 에 원본 생성 시각이 있어야 한다.",
    ))
    report.add(_scalar_axis(
        "doc.last_edited", group, "원본 수정일", pairs,
        source_of=lambda d: d["last_edited"],
        target_of=lambda t: _norm_dt(
            t.get("legacy_updated_at") or t.get("notion_last_edited")),
        samples=samples,
        note="`documents.legacy_updated_at` 에 원본 수정 시각이 있어야 한다.",
    ))

    # 프로젝트 관계. `document_relations` 는 문서끼리의 변이라 프로젝트를 못 담는다.
    project_axis = report.add(AxisResult(
        key="doc.project", group=group, label="프로젝트 관계",
        note="문서를 프로젝트에 잇는 자리가 대상 스키마에 없다.",
        target_total=target.get("document_relations"),
    ))
    for ref, src, tgt in pairs:
        if not src["project_ids"]:
            continue
        project_axis.checked += 1
        if not (tgt or {}).get("project_ids"):
            _mark_lost(project_axis, ref, samples)

    report.add(_set_axis(
        "doc.category", group, "분류(태그)", pairs,
        source_of=lambda d: d["category_names"],
        target_of=lambda t: t.get("tag_names") or [],
        samples=samples,
        note="원본 카테고리 이름이 `tags` 에 다 들어 있는가. 사용자가 더 붙인 태그는 안 따진다.",
    ))
    report.add(_set_axis(
        "doc.doc_type", group, "유형", pairs,
        source_of=lambda d: d["doc_type_names"],
        target_of=lambda t: [t.get("doc_type")] if t.get("doc_type") else [],
        samples=samples, subset_ok=True,
        note="유형이 여럿인 문서는 하나만 담기므로 겹치는 것이 하나라도 있으면 통과다.",
    ))

    attach_axis = report.add(AxisResult(
        key="doc.attachment", group=group, label="첨부",
        note="바깥 링크와 상한 초과는 이름 붙은 설계상 차이다.",
    ))
    _audit_attachments(
        attach_axis, pairs, file_by_legacy=file_by_legacy, ledger=ledger,
        count_of=lambda t: (t or {}).get("attachment_count") or 0, samples=samples,
    )

    space_axis = report.add(AxisResult(
        key="doc.space_visible", group=group, label="공간 가시성",
        note="공간의 `owner_kind` 가 `unset` 이면 소유 규칙의 어느 갈래에도 안 걸려 아무도 못 본다 (D7).",
    ))
    for ref, _src, tgt in pairs:
        space_id = (tgt or {}).get("space_id")
        if not space_id:
            continue
        space_axis.checked += 1
        owner_kind = (spaces.get(space_id) or {}).get("owner_kind")
        if owner_kind in (None, "", "unset"):
            _mark_lost(space_axis, ref, samples)

    report.add(AxisResult(
        key="doc.folder", group=group, label="폴더 배치", audited=False,
        note="원본에 폴더 축이 없어 비교할 것이 없다 (D6). 폴더는 비어 있는 것이 정답이다.",
        target_total=target.get("folders"),
    ))

    ph_axis = report.add(AxisResult(
        key="doc.placeholder", group=group, label="자리표시자 잔존",
        note="본문에 `[원본에서 확인: …]` 이 남아 있으면 그 자리의 내용은 아직 안 왔다.",
    ))
    for ref, _src, tgt in pairs:
        text = (tgt or {}).get("body_text")
        if text is None:
            continue
        ph_axis.checked += 1
        if PLACEHOLDER_RE.search(text):
            _mark_lost(ph_axis, ref, samples)


def _audit_attachments(
    axis: AxisResult, pairs, *, file_by_legacy, ledger, count_of, samples,
):
    """첨부 축. 원본에 바이트가 있던 것만 따진다.

    바이트가 저장소에 없을 때 **까닭이 이름 붙어 있어야** 봐준다. 까닭 없이 사라진
    첨부는 손실이다 — 내려받기 실패도 여기로 오고, 그것은 설계가 아니라 사고다.
    """
    for ref, src, tgt in pairs:
        wanted = src["attachments"]
        if not wanted:
            continue
        axis.checked += 1
        expected = 0
        excluded = False
        missing: list[str] = []
        for att in wanted:
            if not att["hosted"]:
                _note_reason(axis, BD_ATTACHMENT_EXTERNAL)
                excluded = True
                continue
            if att["legacy_id"] not in file_by_legacy:
                if ledger.get(att["legacy_id"]) == "attachment_rejected":
                    _note_reason(axis, BD_ATTACHMENT_LIMIT)
                    excluded = True
                else:
                    missing.append(att["name"])
                continue
            expected += 1
        if missing:
            _mark_lost(axis, f"{ref} (바이트 없음: {_brief(', '.join(missing))})", samples)
        elif expected and count_of(tgt) < expected:
            _mark_lost(axis, f"{ref} (파일은 있는데 안 붙었다)", samples)
        elif excluded:
            axis.by_design += 1


def _audit_tickets(
    report: Report, pairs, *, target, file_by_legacy, ledger,
    samples: int, body_ratio: float,
) -> None:
    group = "티켓"

    row_axis = report.add(AxisResult(
        key="ticket.row", group=group, label="티켓 행", checked=len(pairs),
        note="원본 작업 한 건마다 `tickets.notion_page_id` 로 짝을 찾는다.",
        source_total=len(pairs), target_total=len(target.get("tickets") or []),
    ))
    for ref, _src, tgt in pairs:
        if tgt is None:
            _mark_lost(row_axis, ref, samples)

    for key, label, getter, column, normalize in (
        ("ticket.title", "제목", "title", "title", _norm_text),
        ("ticket.status", "상태", "status", "status", _norm_text),
        ("ticket.priority", "우선순위", "priority", "priority", _norm_text),
        ("ticket.difficulty", "난이도", "difficulty", "difficulty", _norm_text),
        ("ticket.category", "대분류", "category", "category", _norm_text),
        ("ticket.due_date", "마감일", "due_date", "due_date", _norm_date),
        ("ticket.start_date", "시작일", "start_date", "start_date", _norm_date),
        ("ticket.est_wd", "예상 WD", "est_wd", "est_wd", _norm_num),
        ("ticket.act_wd", "실제 WD", "act_wd", "act_wd", _norm_num),
        ("ticket.created_time", "원본 생성일", "created_time",
         "notion_created_time", _norm_dt),
    ):
        report.add(_scalar_axis(
            key, group, label, pairs,
            source_of=(lambda name: lambda t: t[name])(getter),
            target_of=(lambda name: lambda t: t.get(name))(column),
            normalize=normalize, samples=samples,
        ))

    empty_axis = report.add(AxisResult(
        key="ticket.body_nonempty", group=group, label="본문 있음",
        note="원본에 글자가 있는 티켓의 본문이 우리 쪽에서 0자가 아닌가.",
    ))
    shrink_axis = report.add(AxisResult(
        key="ticket.body_chars", group=group, label="본문 글자",
        note=f"자리표시자를 뺀 낱말 글자가 원본의 {int(body_ratio * 100)}% 이상인가.",
    ))
    src_words = tgt_words = 0
    for ref, src, tgt in pairs:
        want = src["body_words"]
        if want <= 0:
            continue
        got = _words((tgt or {}).get("body_markdown"))
        src_words += want
        tgt_words += got
        empty_axis.checked += 1
        shrink_axis.checked += 1
        if got <= 0:
            _mark_lost(empty_axis, ref, samples)
        if got < want * body_ratio:
            _mark_lost(shrink_axis, ref, samples)
    shrink_axis.source_total = src_words
    shrink_axis.target_total = tgt_words

    report.add(_set_axis(
        "ticket.assignee", group, "담당자", pairs,
        source_of=lambda t: t["assignee_ids"],
        target_of=lambda t: _split_names(t.get("assignee_notion_ids")),
        samples=samples,
        note="Notion 사용자 id 그대로 비교한다. 포털 계정 연결 여부는 다른 축이다.",
    ))
    report.add(_set_axis(
        "ticket.project", group, "프로젝트", pairs,
        source_of=lambda t: t["project_ids"],
        target_of=lambda t: _split_names(t.get("project_ids")),
        samples=samples,
    ))

    # 상위 작업. 원본이 부모를 여럿 준 자리는 **설계상 차이**다 (D8).
    parent_axis = report.add(AxisResult(
        key="ticket.parent", group=group, label="상위 작업",
        note="부모가 하나면 그대로, 여럿이면 첫 하나만 남는 것이 계약이다 (D8).",
    ))
    subtask_edges = {
        (row.get("from_page"), row.get("to_page"))
        for row in (target.get("ticket_relations") or [])
        if row.get("kind") == "subtask_of"
    }
    source_parent_edges = 0
    for ref, src, tgt in pairs:
        parents = src["parent_ids"]
        if not parents:
            continue
        source_parent_edges += len(parents)
        parent_axis.checked += 1
        linked = (tgt or {}).get("parent_page_id")
        has_edge = any((ref, parent) in subtask_edges for parent in parents)
        if linked not in parents or not has_edge:
            _mark_lost(parent_axis, ref, samples)
        elif len(parents) > 1:
            # 부모가 여럿이던 행이다. 첫 하나는 이어졌고 나머지는 계약대로 버렸다.
            parent_axis.by_design += 1
            for _extra in parents[1:]:
                _note_reason(parent_axis, BD_SINGLE_PARENT)
    parent_axis.source_total = source_parent_edges
    parent_axis.target_total = len(subtask_edges)

    # 선행·후속. Notion 이 양쪽에 적어 두므로 변 하나로 모아 비교한다.
    block_axis = report.add(AxisResult(
        key="ticket.blocks", group=group, label="선행 후속 관계",
        note="`blocked_by` 는 (저쪽 → 이쪽), `blocks` 는 (이쪽 → 저쪽) 변이다.",
    ))
    target_block_edges = {
        (row.get("from_page"), row.get("to_page"))
        for row in (target.get("ticket_relations") or [])
        if row.get("kind") == "blocks"
    }
    wanted_edges: set[tuple[str, str]] = set()
    known_pages = {ref for ref, _s, _t in pairs}
    for ref, src, _tgt in pairs:
        for other in src["blocked_by"]:
            wanted_edges.add((other, ref))
        for other in src["blocks"]:
            wanted_edges.add((ref, other))
    for from_page, to_page in sorted(wanted_edges):
        if from_page not in known_pages or to_page not in known_pages:
            # 짝이 이관 대상에 없다. 원본에도 이을 상대가 없으므로 손실이 아니다.
            continue
        block_axis.checked += 1
        if (from_page, to_page) not in target_block_edges:
            _mark_lost(block_axis, f"{from_page}->{to_page}", samples)
    block_axis.source_total = len(wanted_edges)
    block_axis.target_total = len(target_block_edges)

    attach_axis = report.add(AxisResult(
        key="ticket.attachment", group=group, label="첨부",
        note="`ticket_attachments` 에 행이 있어야 티켓 화면이 첨부를 보여준다.",
    ))
    _audit_attachments(
        attach_axis, pairs, file_by_legacy=file_by_legacy, ledger=ledger,
        count_of=lambda t: (t or {}).get("attachment_count") or 0, samples=samples,
    )

    comment_total = sum(
        (row.get("comment_count") or 0) for row in (target.get("tickets") or [])
    )
    report.add(AxisResult(
        key="ticket.comment", group=group, label="댓글", audited=False,
        note="원본 캐시에 댓글 축이 없어 비교할 것이 없다. 표본 6쪽 탐침은 0건이었다.",
        target_total=comment_total,
    ))

    ph_axis = report.add(AxisResult(
        key="ticket.placeholder", group=group, label="자리표시자 잔존",
        note="본문에 `[원본에서 확인: …]` 이 남아 있으면 그 자리의 내용은 아직 안 왔다.",
    ))
    for ref, _src, tgt in pairs:
        text = (tgt or {}).get("body_markdown")
        if text is None:
            continue
        ph_axis.checked += 1
        if PLACEHOLDER_RE.search(text):
            _mark_lost(ph_axis, ref, samples)


def _audit_blocks(report: Report, src_docs, src_tickets, tgt_docs, tgt_tickets) -> None:
    """블록 종류별 보존율. **본문 안에서 무엇이 살아남았는가**를 따로 센다."""
    src_doc_kinds: dict[str, int] = {}
    src_ticket_kinds: dict[str, int] = {}
    src_doc_cells = src_ticket_cells = 0
    for doc in src_docs:
        for kind, count in doc["block_kinds"].items():
            src_doc_kinds[kind] = src_doc_kinds.get(kind, 0) + count
        src_doc_cells += doc["cell_words"]
    for ticket in src_tickets:
        for kind, count in ticket["block_kinds"].items():
            src_ticket_kinds[kind] = src_ticket_kinds.get(kind, 0) + count
        src_ticket_cells += ticket["cell_words"]

    tgt_doc_nodes: dict[str, int] = {}
    tgt_doc_cells = 0
    for row in tgt_docs.values():
        body = row.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                body = None
        if body is None:
            continue
        for kind, count in _node_census(body).items():
            tgt_doc_nodes[kind] = tgt_doc_nodes.get(kind, 0) + count
        tgt_doc_cells += _cell_words(body)

    tgt_ticket_nodes: dict[str, int] = {}
    tgt_ticket_cells = 0
    for row in tgt_tickets.values():
        census = _md_census(row.get("body_markdown"))
        for kind, count in census.items():
            tgt_ticket_nodes[kind] = tgt_ticket_nodes.get(kind, 0) + count
        tgt_ticket_cells += _md_table_words(row.get("body_markdown"))

    all_kinds = sorted(set(src_doc_kinds) | set(src_ticket_kinds))
    for kind in all_kinds:
        node = CONTRACT_BLOCKS.get(kind)
        src_doc = src_doc_kinds.get(kind, 0)
        src_ticket = src_ticket_kinds.get(kind, 0)
        row = {
            "kind": kind,
            "source_documents": src_doc,
            "source_tickets": src_ticket,
            "contract_node": node,
            "target_documents": tgt_doc_nodes.get(node, 0) if node else None,
            "target_tickets": tgt_ticket_nodes.get(node, 0) if node else None,
        }
        if node:
            got = row["target_documents"] + row["target_tickets"]
            want = src_doc + src_ticket
            row["preserved_pct"] = round(100.0 * got / want, 1) if want else None
        report.blocks.append(row)

    for kind in CONTRACT_BLOCKS:
        node = CONTRACT_BLOCKS[kind]
        want = src_doc_kinds.get(kind, 0) + src_ticket_kinds.get(kind, 0)
        if want <= 0:
            continue
        got = tgt_doc_nodes.get(node, 0) + tgt_ticket_nodes.get(node, 0)
        axis = report.add(AxisResult(
            key=f"block.{kind}", group="블록", label=f"{kind} 블록",
            checked=want, source_total=want, target_total=got,
            note=f"본문 계약의 `{node}` 노드로 남아 있어야 한다.",
        ))
        if got < want:
            axis.lost = want - got
            axis.samples.append(f"원본 {want} → 대상 {got}")

    cell_axis = report.add(AxisResult(
        key="block.table_cell_chars", group="블록", label="표 칸 글자",
        checked=src_doc_cells + src_ticket_cells,
        source_total=src_doc_cells + src_ticket_cells,
        target_total=tgt_doc_cells + tgt_ticket_cells,
        note="표 안에 있던 낱말 글자가 우리 본문의 표 칸에 얼마나 남았는가.",
    ))
    if cell_axis.checked and cell_axis.target_total < cell_axis.checked:
        cell_axis.lost = cell_axis.checked - cell_axis.target_total
        cell_axis.samples.append(
            f"원본 {cell_axis.source_total}자 → 대상 {cell_axis.target_total}자"
        )


# ── 출력 ─────────────────────────────────────────────────────────────────────

_MARK = {
    ST_OK: "OK  ", ST_LOST: "LOST", ST_BY_DESIGN: "DIFF", ST_NOT_AUDITED: "----",
}


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def render_table(report: Report) -> str:
    lines: list[str] = []
    lines.append("이관 정합성 감사: 원본 캐시 대비 대상 데이터베이스")
    lines.append("")
    counts = report.extras.get("counts") or {}
    if counts:
        lines.append(
            f"원본 문서 {counts.get('source_documents')}, 티켓 {counts.get('source_tickets')}"
            f"   /   대상 문서 {counts.get('target_documents')}, 티켓 {counts.get('target_tickets')}"
        )
        lines.append("")

    header = ("", "축", "본 건수", "맞음", "손실", "설계차", "표본")
    widths = [4, 26, 8, 7, 6, 7, 64]
    lines.append("  ".join(_pad(h, w) for h, w in zip(header, widths)))
    lines.append("-" * (sum(widths) + 2 * (len(widths) - 1)))

    group = None
    for axis in report.axes:
        if axis.group != group:
            group = axis.group
            lines.append(f"[{group}]")
        sample = axis.samples[0][:62] if axis.samples else ""
        if len(axis.samples) > 1:
            sample = f"{axis.samples[0][:50]} 외 {len(axis.samples) - 1}"
        cells = (
            _MARK[axis.status], axis.label, str(axis.checked), str(axis.ok),
            str(axis.lost), str(axis.by_design), sample,
        )
        lines.append("  ".join(_pad(c, w) for c, w in zip(cells, widths)))

    lines.append("")
    lines.append("블록 종류별 보존")
    bh = ("종류", "원본 문서", "원본 티켓", "대상 노드", "대상 문서", "대상 티켓", "보존율")
    bw = [20, 10, 10, 12, 10, 10, 8]
    lines.append("  ".join(_pad(h, w) for h, w in zip(bh, bw)))
    lines.append("-" * (sum(bw) + 2 * (len(bw) - 1)))
    for row in report.blocks:
        pct = row.get("preserved_pct")
        cells = (
            row["kind"], str(row["source_documents"]), str(row["source_tickets"]),
            row.get("contract_node") or "-",
            "-" if row.get("target_documents") is None else str(row["target_documents"]),
            "-" if row.get("target_tickets") is None else str(row["target_tickets"]),
            "-" if pct is None else f"{pct}%",
        )
        lines.append("  ".join(_pad(c, w) for c, w in zip(cells, bw)))

    by_design: dict[str, int] = {}
    for axis in report.axes:
        for reason, count in axis.by_design_reasons.items():
            by_design[reason] = by_design.get(reason, 0) + count
    if by_design:
        lines.append("")
        lines.append("설계상 차이 (실패로 세지 않는다)")
        for reason, count in sorted(by_design.items()):
            lines.append(f"  {reason} {count}건: {BY_DESIGN_WHY.get(reason, '')}")

    not_audited = [axis for axis in report.axes if not axis.audited]
    if not_audited:
        lines.append("")
        lines.append("비교하지 못한 축 (원본에 자료가 없다)")
        for axis in not_audited:
            lines.append(f"  {axis.key}: {axis.note}")

    unread = report.extras.get("unread_properties") or {}
    rows = [
        (scope, item) for scope, items in unread.items() for item in (items or [])[:5]
    ]
    if rows:
        lines.append("")
        lines.append("우리가 안 읽는데 원본에 값이 있는 속성 (참고)")
        for scope, item in rows:
            lines.append(f"  {scope} / {item['property']}: {item['filled_rows']}행")

    failing = [axis.key for axis in report.axes if axis.lost]
    lines.append("")
    lines.append(
        f"본 건수 합계 {report.total_checked}, 손실 합계 {report.total_lost}, "
        f"손실이 난 축 {len(failing)}개"
    )
    if failing:
        lines.append("  " + ", ".join(failing))
    lines.append(report.verdict)
    return "\n".join(lines)


# ── 실행 ─────────────────────────────────────────────────────────────────────


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        description="이관 정합성 감사. 원본 캐시와 대상 데이터베이스를 축마다 셉니다.",
    )
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--database-url", default=None,
                        help="대상 데이터베이스. 읽기 전용 SELECT 한 문장만 돈다.")
    parser.add_argument("--target-json", default=None,
                        help="미리 받아 둔 대상 스냅숏 JSON 파일.")
    parser.add_argument("--dump-target", default=None,
                        help="--database-url 로 받은 스냅숏을 이 경로에 저장한다.")
    parser.add_argument("--emit-target-sql", action="store_true",
                        help="대상 스냅숏을 뽑는 psql 스크립트를 찍고 끝낸다.")
    parser.add_argument("--source-only", action="store_true",
                        help="대상 없이 원본만 센다.")
    parser.add_argument("--json", nargs="?", const="-", default=None,
                        help="기계용 출력. 경로를 안 주면 표준출력에 찍는다.")
    parser.add_argument("--migration-report", default=str(DEFAULT_REPORT),
                        help="이관 보고서. 첨부가 왜 안 왔는지의 분류만 읽는다.")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--body-ratio", type=float, default=DEFAULT_BODY_RATIO)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.emit_target_sql:
        sys.stdout.write(emit_target_sql())
        return 0

    if args.source_only:
        source = collect_source(Path(args.cache_dir))
        payload = {
            "documents": len(source["documents"]),
            "tickets": len(source["tickets"]),
            "document_blocks": _sum_kinds(source["documents"]),
            "ticket_blocks": _sum_kinds(source["tickets"]),
            "unread_properties": source["unread_properties"],
        }
        # 원본만 센 결과에는 판정 줄을 안 붙인다. 비교를 안 했으므로 판정할 것이 없다.
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.target_json:
        target = load_target_json(Path(args.target_json))
    elif args.database_url:
        target = fetch_target(args.database_url)
        if args.dump_target:
            # 뜨는 것으로 끝낸다. 원본 캐시는 데이터베이스가 있는 기계에 없는 것이 보통이고,
            # 없는 캐시를 읽으려다 죽으면 방금 뜬 스냅숏이 쓸모없어 보인다.
            Path(args.dump_target).write_text(
                json.dumps(target, ensure_ascii=False), encoding="utf-8",
            )
            # 판정을 안 했으므로 판정 줄을 찍지 않는다. 아무것도 안 세고 찍은 `FIDELITY_OK`
            # 가 로그에 남으면 그 줄이 나중에 증거로 읽힌다.
            print(f"대상 스냅숏을 {args.dump_target} 에 저장했습니다.")
            return 0
    else:
        print("--database-url 이나 --target-json 중 하나가 필요합니다.", file=sys.stderr)
        return 2

    source = collect_source(Path(args.cache_dir))
    report = audit(
        source, target, ledger=load_ledger(Path(args.migration_report)),
        samples=args.samples, body_ratio=args.body_ratio,
    )

    if args.json and args.json != "-":
        Path(args.json).write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(render_table(report))
    elif args.json == "-":
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        print(report.verdict)
    else:
        print(render_table(report))
    return 0 if report.passed else 1


def _sum_kinds(rows) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        for kind, count in row["block_kinds"].items():
            out[kind] = out.get(kind, 0) + count
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
