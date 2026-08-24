"""소스의 모양 → 우리 도메인의 모양. **DB 를 모르는 순수 함수만 둔다** (S13).

## 왜 순수 함수인가

이관에서 가장 조용히 틀리는 자리는 「이 Notion 속성이 어느 컬럼이 되는가」다. 그 판단이
적재 코드 안에 섞여 있으면 확인하려고 임시 PostgreSQL 을 세워야 하고, 그러면 아무도
표본 하나로 확인하지 않는다. 여기 있는 함수는 전부 사전 하나를 받아 사전 하나를 낸다 —
시험이 Notion 응답 표본 하나로 「이 값이 저기로 간다」를 직접 단언한다.

## Notion 블록 → 본문 정본

문서 본문의 정본은 Block JSON 이다(D-198). Notion 블록을 마크다운으로 한 번 내렸다가
다시 올리면 **코드 블록 46개와 목록 중첩이 뭉개진다**(실측 표본: 문서 하나당 38블록 중
code 46 · bulleted 127). 그래서 마크다운을 거치지 않고 노드로 직접 옮긴다.

표·이미지는 **글자가 아니라 노드로** 옮긴다(S14 · D3). 그 전에는 스키마에 자리가 없어서
`[원본에서 확인: image]` 같은 문단으로 바꿔 넣었고, 그러면 표 셀의 글자 31,310자가
어디에도 안 남았다. 남은 자리표시자는 사람이 읽는 문장으로 적는다 — 사용자에게
`synced_block` 같은 내부 이름을 보여 주면 그것은 설명이 아니라 소음이다.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import unquote, urlsplit

from app.core import dates
from app.migration.source_notion import NotionSourceError
from app.knowledge import blocks as block_mod
from app.work import models as work_models

__all__ = [
    "TASK_PROPS", "DOC_PROPS", "PROJECT_PROPS",
    "NotionAttachment", "NotionMedia", "NotionComment",
    "parse_task", "parse_project", "parse_document", "parse_comment", "comments_of",
    "attachments_of", "media_of", "notion_blocks_to_doc", "classify_ticket_exception",
    "space_slug", "assign_sequences", "property_coverage", "relation_titles",
]


# ── Notion 속성 이름 (실측 2026-08-23 · 워크스페이스 직접 조회) ────────────
#
# ## 이름을 다시 쟀다. 옛 상수는 문서 DB 에서 **하나도 안 맞았다**
#
# `app/team_docs/notion_docs.py` 가 들고 있는 이름(`제목`·`유형`·`카테고리`·`프로젝트`)은
# 지금 워크스페이스에 **없다**. 실제 이름은 `이름 `·` 유형`·` 카테고리`·`프로젝트 선택`
# 이고, 앞뒤에 공백이 붙어 있는 것이 여럿이다.
#
# 이것이 INVENTORY 05 가 기록한 사실의 **원인**이다: 「`type_names` 110건 전부 빈
# 문자열」. 동기화는 매번 성공했고 분류만 조용히 비어 있었다 — 속성 이름이 안 맞으면
# Notion 은 오류를 내지 않고 그냥 그 키가 없는 응답을 준다.
#
# 그래서 두 가지를 함께 한다:
#   1. 이름을 실측으로 맞춘다 (아래 표).
#   2. **앞뒤 공백을 무시하고 찾는다** (`_prop`). 공백 하나로 필드가 사라지는 일이
#      다시 생기지 않게.
#   3. 그리고 **하나도 안 맞으면 말한다** (`property_coverage`). 이름이 또 바뀌는 날
#      조용히 빈 컬럼이 되는 대신 보고서가 그 사실을 적는다.
TASK_PROPS = {
    "title": "제목",
    "ticket_id": "티켓 ID",
    "status": "진행상태",
    "priority": "우선순위",
    "difficulty": "난이도",
    "est_wd": "예상 WD",
    "act_wd": "실제 WD",
    "start": "시작일",
    "due": "마감일",
    "category": "대분류",
    "assignees": "티켓 담당자",
    "project": "프로젝트",
    "parent": "상위 작업",
    # 선후 관계. `ticket_relations(blocks)` 가 된다 (D-236 · INVENTORY 07).
    "predecessors": "티켓 선택(선행 작업)",
    "successors": "티켓 선택(후속 작업)",
}

DOC_PROPS = {
    "title": "이름 ",
    "type": " 유형",
    "category": " 카테고리",
    "project": "프로젝트 선택",
    "status": "상태 ",
    "priority": "우선순위 ",
    "author": "작성자",
    "owner": " 소유자",
    "date": "날짜",
    "source": " 출처 ",
    "memo": " 메모 ",
    "favorite": " 즐겨찾기 ",
    "archived": " 보관됨 ",
}

PROJECT_PROPS = {
    "title": "프로젝트",
    "status": "진행 상태",
    "progress": "프로젝트 진행률",
    "owner": "담당자(정)",
    "biz_type": "사업 구분",
    "product": "제품/품목",
    "period": "기간",
    "summary": "요약",
}


# ── 속성 하나를 읽는 잔손 ────────────────────────────────────────────────────


def _key(name: str | None) -> str:
    """속성 이름 비교용. **앞뒤·가운데 공백과 유니코드 합성만** 다듬는다.

    철자는 안 건드린다 — 「비슷한 이름」을 같다고 보기 시작하면 엉뚱한 속성을 읽는다.
    """
    return " ".join(unicodedata.normalize("NFC", name or "").split())


def _prop(row: dict, name: str) -> dict:
    props = row.get("properties") or {}
    value = props.get(name)
    if isinstance(value, dict):
        return value
    # 정확히 없으면 공백만 다듬어 다시 본다. 실측에 ` 유형`·`이름 `·`첨부파일 ` 처럼
    # 앞뒤 공백이 붙은 이름이 여럿 있다.
    wanted = _key(name)
    for key, value in props.items():
        if isinstance(value, dict) and _key(key) == wanted:
            return value
    return {}


def property_coverage(rows: list[dict], names: dict[str, str]) -> dict[str, int]:
    """논리 필드마다 **값이 실제로 들어 있던 행 수**.

    0 이면 둘 중 하나다: 그 속성이 정말 비어 있거나, **이름이 안 맞거나.** 후자는
    오류를 안 내므로 세지 않으면 영원히 안 보인다 — 문서 분류 110건이 그렇게 비어
    있었다(INVENTORY 05).
    """
    out = {logical: 0 for logical in names}
    for row in rows:
        for logical, name in names.items():
            prop = _prop(row, name)
            kind = prop.get("type")
            if not kind:
                continue
            value = prop.get(kind)
            if isinstance(value, (list, dict)):
                if value:
                    out[logical] += 1
            elif value not in (None, ""):
                out[logical] += 1
    return out


def _plain(parts) -> str:
    return "".join(
        seg.get("plain_text", "")
        for seg in (parts or [])
        if isinstance(seg, dict)
    ).strip()


def _title(prop: dict) -> str:
    return _plain(prop.get("title"))


def _rich(prop: dict) -> str | None:
    return _plain(prop.get("rich_text")) or None


def _select(prop: dict) -> str | None:
    value = prop.get("select")
    return value.get("name") if isinstance(value, dict) else None


def _status(prop: dict) -> str | None:
    value = prop.get("status")
    return value.get("name") if isinstance(value, dict) else None


def _relations(prop: dict) -> list[str]:
    return [
        item["id"]
        for item in (prop.get("relation") or [])
        if isinstance(item, dict) and item.get("id")
    ]


def _people(prop: dict) -> list[str]:
    return [
        item["id"]
        for item in (prop.get("people") or [])
        if isinstance(item, dict) and item.get("id")
    ]


def _people_names(prop: dict) -> list[str]:
    return [
        (item.get("name") or "").strip()
        for item in (prop.get("people") or [])
        if isinstance(item, dict) and (item.get("name") or "").strip()
    ]


def _date_start(prop: dict) -> str | None:
    value = prop.get("date")
    return value.get("start") if isinstance(value, dict) else None


def _number(prop: dict):
    """숫자. **formula 와 rollup 도 읽는다.**

    프로젝트 진행률은 `formula` 다 — `prop["number"]` 만 보면 언제나 `None` 이고,
    그러면 「Notion 은 이렇게 말한다」 칸이 영원히 빈다(`projects.notion_progress_pct`).
    """
    if prop.get("number") is not None:
        return prop["number"]
    for wrapper in ("formula", "rollup"):
        inner = prop.get(wrapper)
        if isinstance(inner, dict) and inner.get("number") is not None:
            return inner["number"]
    return None


def _date_range(prop: dict) -> tuple[str | None, str | None]:
    value = prop.get("date")
    if not isinstance(value, dict):
        return None, None
    return value.get("start"), value.get("end")


def _checkbox(prop: dict) -> bool:
    return bool(prop.get("checkbox"))


def _url(prop: dict) -> str | None:
    value = prop.get("url")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _unique_id(prop: dict) -> tuple[str | None, int | None]:
    value = prop.get("unique_id")
    if not isinstance(value, dict):
        return None, None
    return value.get("prefix"), value.get("number")


# ── 첨부 ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotionAttachment:
    """페이지에 붙은 파일 하나.

    `hosted` 가 거짓이면 **바이트가 Notion 에 없다** — 사람이 붙여 둔 바깥 링크다
    (SharePoint 문서 등). 내려받으려 하면 자격증명이 없어 실패하고, 실패를 오류로
    세면 「이관이 깨졌다」로 보이지만 실제로는 원래 링크였던 것이다. 그래서 종류를
    값으로 들고 다닌다.
    """

    page_id: str
    index: int
    name: str
    url: str
    hosted: bool
    property_name: str

    @property
    def legacy_id(self) -> str:
        """`legacy_mapping` 이 쓰는 안정적 식별자.

        Notion 이 파일에 id 를 주지 않는다 — 임시 URL 은 매 조회마다 바뀌므로 키로 쓸
        수 없다. 페이지 안의 자리(속성 + 순번)가 안정적인 유일한 값이다.
        """
        return f"{self.page_id}:{self.index}"


def attachments_of(row: dict) -> list[NotionAttachment]:
    """페이지의 모든 `files` 속성에서 첨부를 모은다.

    속성 이름을 고정하지 않는 이유가 실측에 있다: 문서 DB 는 `첨부파일 `(끝에 공백)과
    `파일과 미디어` 두 곳에 파일을 갖고 있다. 이름으로 찾으면 그중 하나를 놓친다.
    """
    page_id = row.get("id") or ""
    out: list[NotionAttachment] = []
    index = 0
    for prop_name, prop in sorted((row.get("properties") or {}).items()):
        if not isinstance(prop, dict) or prop.get("type") != "files":
            continue
        for item in prop.get("files") or []:
            if not isinstance(item, dict):
                continue
            hosted = isinstance(item.get("file"), dict)
            holder = item.get("file") if hosted else item.get("external")
            url = (holder or {}).get("url") if isinstance(holder, dict) else None
            if not url:
                continue
            out.append(NotionAttachment(
                page_id=page_id,
                index=index,
                name=(item.get("name") or "").strip() or "첨부",
                url=url,
                hosted=hosted,
                property_name=prop_name,
            ))
            index += 1
    return out


# ── 댓글 (D11) ───────────────────────────────────────────────────────────────

# 첨부만 있고 글이 없는 댓글의 본문. 실측 325건 중 17건이 그렇고 전부 파일이 붙어
# 있다. 빈 글로 넣으면 화면에 아무 말도 없는 줄이 남고, 안 넣으면 「누가 언제 무엇을
# 올렸다」가 통째로 사라진다 — 본문의 잃은 파일과 같은 문장을 쓴다.
COMMENT_ATTACHMENT_ONLY = "원본에만 있는 첨부 파일입니다."


@dataclass(frozen=True)
class NotionComment:
    """Notion 댓글 하나 → 우리 `ticket_comments` 한 줄이 될 값.

    `discussion_id` 를 들고 다니지만 **우리 표에는 그 칸이 없다.** 그래도 버리지 않는
    이유는 순서 때문이다: 같은 스레드의 답글이 원글보다 먼저 들어가면 목록이 대화가
    아니라 파편이 된다. 적재가 시간 순으로 펴 넣으므로 그 순서는 지켜지고, 이 값은
    「원본에서 어느 대화였는가」를 보고서가 셀 수 있게 남긴다.
    """

    page_id: str
    comment_id: str
    discussion_id: str
    author_notion_id: str | None
    # `display_name.type` 이다. `user` 면 사람이고 `integration` 이면 자동화가 쓴 것이다.
    # 판정에는 안 쓴다 — 작성자는 `user_notion_mappings` 하나로만 푼다. 보고서에서
    # 「이건 사람이 아니다」를 사람이 읽게 하는 값이다.
    author_kind: str
    author_label: str
    body: str
    created_at: datetime | None
    created_raw: str
    attachment_count: int

    @property
    def legacy_id(self) -> str:
        """`legacy_mapping` 이 쓰는 식별자. Notion 이 댓글에 준 id 를 그대로 쓴다.

        페이지 안의 자리(순번)로 만들지 않는 이유는 댓글이 지워질 수 있기 때문이다 —
        하나가 사라지면 그 뒤 전부의 자리가 밀리고, 재실행이 같은 댓글을 새 댓글로 본다.
        """
        return self.comment_id


def _comment_text(parts) -> str:
    """댓글 `rich_text` → 평문. **줄바꿈을 지운다면 코드 조각이 한 줄이 된다.**

    본문(`_plain`)과 달리 조각마다 `strip` 하지 않고 그대로 잇는다. 실측 댓글에는
    자바 코드가 여러 줄로 들어 있고, 그 줄바꿈이 사라지면 읽을 수 없는 한 줄이 된다.
    양 끝의 공백만 다듬는다.
    """
    out: list[str] = []
    for seg in parts or []:
        if not isinstance(seg, dict):
            continue
        text = seg.get("plain_text")
        if text is None:
            holder = seg.get("text")
            text = holder.get("content") if isinstance(holder, dict) else None
        if text:
            out.append(text)
    return "".join(out).strip()


def parse_comment(raw: dict, *, page_id: str = "") -> NotionComment | None:
    """Notion 댓글 한 건 → `NotionComment`. 식별자가 없으면 `None`.

    작성자를 여기서 사람으로 풀지 않는다. `created_by.id` 를 그대로 넘기고 해석은
    `_user_for_notion` 하나가 한다 — 이름으로 잇는 두 번째 판정이 생기면 그 둘은
    언젠가 갈리고, 갈린 쪽이 남의 이름으로 남의 글을 적는다(U11).
    """
    if not isinstance(raw, dict):
        return None
    comment_id = raw.get("id")
    if not comment_id:
        return None
    parent = raw.get("parent") if isinstance(raw.get("parent"), dict) else {}
    holder = raw.get("created_by") if isinstance(raw.get("created_by"), dict) else {}
    display = raw.get("display_name") if isinstance(raw.get("display_name"), dict) else {}
    attachments = raw.get("attachments")
    body = _comment_text(raw.get("rich_text"))
    count = len(attachments) if isinstance(attachments, list) else 0
    if not body and count:
        body = COMMENT_ATTACHMENT_ONLY
    return NotionComment(
        page_id=page_id or parent.get("page_id") or "",
        comment_id=comment_id,
        discussion_id=raw.get("discussion_id") or "",
        author_notion_id=holder.get("id"),
        author_kind=(display.get("type") or "").strip(),
        author_label=(display.get("resolved_name") or "").strip(),
        body=body,
        created_at=dates.parse_dt(raw.get("created_time")),
        created_raw=raw.get("created_time") or "",
        attachment_count=count,
    )


def comments_of(page_id: str, raw_comments) -> list[NotionComment]:
    """페이지 하나의 댓글 전부.

    식별자가 없어 못 읽는 것은 빼고 낸다. 그렇게 빠진 건수는 검증이 잡는다 —
    「원본 댓글 수 = 이관된 수 + 분류된 예외」가 안 맞으면 그 차이가 여기서 생긴다.
    """
    out: list[NotionComment] = []
    for raw in raw_comments or []:
        parsed = parse_comment(raw, page_id=page_id)
        if parsed is not None:
            out.append(parsed)
    return out


# ── 행 ───────────────────────────────────────────────────────────────────────


def parse_task(row: dict) -> dict:
    """Notion 작업 한 행 → 티켓 컬럼 사전.

    날짜는 여기서 `date` 로 바꾼다 — 문자열을 그대로 넘기면 적재가 `500` 을 낸다(D-248).
    """
    # 접두사(`GIT`)는 버린다 — 옛 티켓 이름을 이관하지 않는다(D-283).
    # 번호는 **채번 순서**로 계속 쓴다(D-281).
    _, number = _unique_id(_prop(row, TASK_PROPS["ticket_id"]))
    parents = _relations(_prop(row, TASK_PROPS["parent"]))
    return {
        "notion_page_id": row.get("id"),
        "url": row.get("url"),
        "title": _title(_prop(row, TASK_PROPS["title"])),
        "notion_ticket_number": number,
        "status": _status(_prop(row, TASK_PROPS["status"])),
        "priority": _select(_prop(row, TASK_PROPS["priority"])),
        "difficulty": _select(_prop(row, TASK_PROPS["difficulty"])),
        "est_wd": _number(_prop(row, TASK_PROPS["est_wd"])),
        "act_wd": _number(_prop(row, TASK_PROPS["act_wd"])),
        "start_date": dates.parse_date(_date_start(_prop(row, TASK_PROPS["start"]))),
        "due_date": dates.parse_date(_date_start(_prop(row, TASK_PROPS["due"]))),
        "category": _rich(_prop(row, TASK_PROPS["category"])),
        "assignee_notion_ids": _people(_prop(row, TASK_PROPS["assignees"])),
        "project_ids": _relations(_prop(row, TASK_PROPS["project"])),
        # 부모가 둘이면 그것은 트리가 아니다. 첫 번째만 쓰고 나머지는 버리되, 몇 개였는지는
        # 남긴다 — 「하나만 골랐다」와 「원래 하나였다」는 다른 사실이다.
        "parent_page_id": parents[0] if parents else None,
        "parent_count": len(parents),
        # 선행 = 저쪽이 이 티켓을 막는다. 후속 = 이 티켓이 저쪽을 막는다.
        # 방향을 여기서 확정해 둔다 — 적재 쪽에서 다시 생각하면 반대로 넣는 날이 온다.
        "blocked_by_pages": _relations(_prop(row, TASK_PROPS["predecessors"])),
        "blocks_pages": _relations(_prop(row, TASK_PROPS["successors"])),
        "notion_created_time": dates.parse_dt(row.get("created_time")),
        "notion_last_edited": dates.parse_dt(row.get("last_edited_time")),
        "last_edited_raw": row.get("last_edited_time"),
        "archived": bool(row.get("archived")),
    }


def parse_project(row: dict) -> dict:
    """Notion 프로젝트 한 행 → 프로젝트 컬럼 사전."""
    title = _title(_prop(row, PROJECT_PROPS["title"]))
    if not title:
        # 제목 속성 이름이 워크스페이스마다 다를 수 있다. `title` 타입 속성을 찾아 쓴다 —
        # 이름을 못 맞혔다고 프로젝트 21건이 전부 빈 이름이 되면 안 된다.
        for prop in (row.get("properties") or {}).values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                title = _title(prop)
                if title:
                    break
    starts, ends = _date_range(_prop(row, PROJECT_PROPS["period"]))
    return {
        "notion_page_id": row.get("id"),
        "name": title,
        "notion_status": _status(_prop(row, PROJECT_PROPS["status"]))
        or _select(_prop(row, PROJECT_PROPS["status"])),
        "notion_progress_pct": _number(_prop(row, PROJECT_PROPS["progress"])),
        "notion_owner_ids": _people(_prop(row, PROJECT_PROPS["owner"])),
        "biz_type": _select(_prop(row, PROJECT_PROPS["biz_type"])),
        "product": _select(_prop(row, PROJECT_PROPS["product"])),
        "starts_on": dates.parse_date(starts),
        "ends_on": dates.parse_date(ends),
        "goal": _rich(_prop(row, PROJECT_PROPS["summary"])),
        "notion_last_edited": dates.parse_dt(row.get("last_edited_time")),
        "last_edited_raw": row.get("last_edited_time"),
        "archived": bool(row.get("archived")),
    }


def parse_document(row: dict) -> dict:
    """Notion 문서 한 행 → 문서 컬럼 사전.

    `원본 생성일`·`원본 URL` 은 **지금 워크스페이스에 없다.** 옛 상수에 있던 이름이고,
    그래서 `document_cache.original_url` 이 운영에서 전량 NULL 이었다(INVENTORY 05 가
    그 사실만 기록해 두었다). 없는 속성을 계속 읽는 대신 목록에서 뺐다.
    """
    return {
        "notion_page_id": row.get("id"),
        "url": row.get("url"),
        "title": _title(_prop(row, DOC_PROPS["title"])),
        "type_ids": _relations(_prop(row, DOC_PROPS["type"])),
        "category_ids": _relations(_prop(row, DOC_PROPS["category"])),
        "project_ids": _relations(_prop(row, DOC_PROPS["project"])),
        "status": _status(_prop(row, DOC_PROPS["status"]))
        or _select(_prop(row, DOC_PROPS["status"])),
        "priority": _select(_prop(row, DOC_PROPS["priority"])),
        "author_notion_ids": _people(_prop(row, DOC_PROPS["author"])),
        "author_names": _people_names(_prop(row, DOC_PROPS["author"])),
        "owner": _rich(_prop(row, DOC_PROPS["owner"])),
        "doc_date": dates.parse_date(_date_start(_prop(row, DOC_PROPS["date"]))),
        "source_url": _url(_prop(row, DOC_PROPS["source"])),
        "memo": _rich(_prop(row, DOC_PROPS["memo"])),
        "notion_favorite": _checkbox(_prop(row, DOC_PROPS["favorite"])),
        "archived": _checkbox(_prop(row, DOC_PROPS["archived"])) or bool(row.get("archived")),
        "notion_created_time": dates.parse_dt(row.get("created_time")),
        "notion_last_edited": dates.parse_dt(row.get("last_edited_time")),
        "last_edited_raw": row.get("last_edited_time"),
    }


def relation_titles(rows: list[dict]) -> dict[str, str]:
    """분류 taxonomy(문서 유형 15 · 카테고리 11) 의 `page id → 이름`."""
    out: dict[str, str] = {}
    for row in rows:
        page_id = row.get("id")
        if not page_id:
            continue
        name = ""
        for prop in (row.get("properties") or {}).values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                name = _title(prop)
                if name:
                    break
        out[page_id] = name
    return out


# ── Notion 블록 → Block JSON (D-198) ─────────────────────────────────────────

# `heading_4` 를 3 으로 낮추지 않는다. 스키마가 1..6 을 받으므로(`blocks._normalize_attrs`)
# 4 를 그대로 쓸 수 있고, 낮추면 실측 21개의 제목이 바로 위 `heading_3` 과 같은 층이 되어
# 「어느 것이 어느 것의 하위인가」가 사라진다.
_HEADING_LEVEL = {"heading_1": 1, "heading_2": 2, "heading_3": 3, "heading_4": 4}
_LIST_KIND = {"bulleted_list_item": "bulletList", "numbered_list_item": "orderedList"}

# 자식만 이어 붙이고 자기 자신은 아무 자리도 안 차지하는 블록. 자리표시자를 남기면
# 군더더기다 — 컬럼이었다는 사실은 옮겨진 글 어디에도 필요하지 않고, `child_page` 는
# 자식 페이지의 본문이 이미 이어 붙는다.
_TRANSPARENT_BLOCKS = frozenset({
    "column_list", "column", "synced_block", "child_page",
    "table_of_contents", "breadcrumb", "template",
})

# 바이트를 들고 있는 블록. `media_of` 가 모으고, 적재가 우리 저장소로 옮긴 다음 URL 을
# 돌려준다(D4). Notion 서명 URL 은 한 시간이면 죽으므로 본문에 남기지 않는다.
MEDIA_BLOCKS = frozenset({"image", "file", "pdf", "video", "audio"})

# 못 옮긴 자리에 남기는 말. **내부 타입 이름을 사용자에게 보여 주지 않는다** — 「원본에서
# 확인: synced_block」은 읽는 사람에게 아무것도 알려 주지 않고 오류처럼 보인다.
_LOST_IMAGE = "원본에만 있는 이미지입니다."
_LOST_FILE = "원본에만 있는 첨부 파일입니다."
_LOST_BLOCK = "원본에만 있는 내용입니다."
# `to_do` 는 우리 스키마에 체크박스 노드가 없다(TipTap StarterKit 만 쓴다 · D-198).
# 목록 항목으로 내리고 상태를 글자로 남긴다 — 지우면 「무엇이 끝났는가」가 사라진다.
_TODO_MARK = {True: "[x] ", False: "[ ] "}


def _inline(parts) -> list[dict]:
    """Notion rich_text → 인라인 노드. 링크와 굵기·기울임·취소선·코드를 옮긴다."""
    out: list[dict] = []
    for seg in parts or []:
        if not isinstance(seg, dict):
            continue
        text = seg.get("plain_text")
        if text is None:
            holder = seg.get("text")
            text = holder.get("content") if isinstance(holder, dict) else None
        if not text:
            continue
        node: dict = {"type": "text", "text": text}
        marks: list[dict] = []
        annotations = seg.get("annotations") or {}
        for flag, name in (
            ("bold", "bold"), ("italic", "italic"),
            ("strikethrough", "strike"), ("code", "code"),
        ):
            if annotations.get(flag):
                marks.append({"type": name})
        href = seg.get("href")
        if isinstance(href, str) and href.strip():
            marks.append({"type": "link", "attrs": {"href": href.strip()}})
        if marks:
            node["marks"] = marks
        out.append(node)
    return out


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _list_item(inline: list[dict], children: list[dict]) -> dict:
    content: list[dict] = [{"type": "paragraph", "content": inline}]
    content.extend(children)
    return {"type": "listItem", "content": content}


def _link_paragraph(text: str, href: str) -> dict:
    return {"type": "paragraph", "content": [
        {"type": "text", "text": text,
         "marks": [{"type": "link", "attrs": {"href": href}}]},
    ]}


def _table(holder: dict, rows) -> dict | None:
    """Notion `table` + `table_row` → D3 의 table 노드.

    머리 칸은 두 축이 따로 정한다: `has_column_header` 는 **첫 줄 전체**를,
    `has_row_header` 는 **첫 칸 열 전체**를 머리로 만든다. 둘 다 켜진 표에서 왼쪽 위
    한 칸이 양쪽에 걸리는데 그것도 머리다.

    빈 셀은 **빈 문단 하나**를 갖는다(D3). 문단을 안 넣으면 ProseMirror 가 그 셀을
    빈 칸이 아니라 잘못된 모양으로 읽는다.
    """
    has_column_header = bool(holder.get("has_column_header"))
    has_row_header = bool(holder.get("has_row_header"))
    out_rows: list[dict] = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict) or row.get("type") != "table_row":
            continue
        cells = (row.get("table_row") or {}).get("cells") or []
        out_cells: list[dict] = []
        for column, cell in enumerate(cells):
            header = (has_column_header and index == 0) or (has_row_header and column == 0)
            inline = _inline(cell)
            paragraph: dict = {"type": "paragraph"}
            if inline:
                paragraph["content"] = inline
            out_cells.append({
                "type": "tableHeader" if header else "tableCell",
                "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None},
                "content": [paragraph],
            })
        if out_cells:
            out_rows.append({"type": "tableRow", "content": out_cells})
    return {"type": "table", "content": out_rows} if out_rows else None


# ── 본문 안의 바이트 (D4) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotionMedia:
    """본문 블록 하나가 들고 있는 파일.

    `NotionAttachment` 와 나누어 둔 이유는 붙는 자리가 다르기 때문이다. 저쪽은 페이지
    **속성**의 첨부라 본문과 무관하게 첨부 목록에 붙고, 이쪽은 본문 **그 자리**에
    이미지나 링크로 다시 들어가야 한다 — 그래서 블록 id 를 들고 다닌다.
    """

    page_id: str
    block_id: str
    block_type: str
    name: str
    url: str
    hosted: bool

    @property
    def legacy_id(self) -> str:
        """`legacy_mapping` 이 쓰는 안정적 식별자.

        블록 id 는 Notion 이 주는 값이고 페이지를 다시 읽어도 같다. 서명 URL 은 매
        조회마다 바뀌므로 키로 쓸 수 없다 — 그것을 키로 쓰면 재실행이 같은 이미지를
        매번 새로 내려받아 첨부가 회차마다 늘어난다.
        """
        return f"block:{self.block_id}"

    @property
    def is_image(self) -> bool:
        return self.block_type == "image"


def _media_name(holder: dict, url: str, *, block_type: str) -> str:
    """파일 이름. 없으면 **URL 의 마지막 조각**에서 만든다.

    이름이 비면 `store_bytes` 가 확장자 없는 이름을 저장하고, 화면에는 무엇인지 알 수
    없는 줄이 하나 남는다. 형식 판정 자체는 매직바이트가 하므로(`sniff_media_type`)
    이름은 사람이 읽기 위한 값이다.
    """
    given = (holder.get("name") or "").strip() if isinstance(holder.get("name"), str) else ""
    if given:
        return given
    caption = _plain(holder.get("caption"))
    tail = unquote((urlsplit(url).path or "").rsplit("/", 1)[-1]).strip()
    if tail:
        return tail
    if caption:
        return caption[:100]
    return "이미지" if block_type == "image" else "첨부"


def _media_of_block(page_id: str, block: dict) -> NotionMedia | None:
    block_type = block.get("type") or ""
    if block_type not in MEDIA_BLOCKS:
        return None
    holder = block.get(block_type)
    if not isinstance(holder, dict):
        return None
    hosted = isinstance(holder.get("file"), dict)
    source = holder.get("file") if hosted else holder.get("external")
    url = source.get("url") if isinstance(source, dict) else None
    block_id = block.get("id")
    if not url or not block_id:
        return None
    # 🔴 「외부」인데 실제로는 이미지가 그 자리에 그대로 박혀 있는 경우가 있다
    # (`data:` URI — 실측: 1,235쪽 중 1건, 누군가 base64 이미지를 직접 붙여 넣은
    # 것으로 보인다). 진짜 외부 링크가 아니라 우리가 옮겨야 할 바이트라 `hosted=False`
    # 로 두면 그 문자열이 그대로 본문에 남고, `blocks.py` 는 허용하지 않는 스킴이라
    # 거절한다 — 그 순간 이미지 하나 때문에 **문서 전체**가 안 들어간다. 우리 저장소로
    # 옮겨야 하는 자리이므로 `hosted` 로 다룬다(`_body_media` 가 그 값으로 갈래를 정한다).
    hosted = hosted or url.startswith("data:")
    return NotionMedia(
        page_id=page_id,
        block_id=block_id,
        block_type=block_type,
        name=_media_name(holder, url, block_type=block_type),
        url=url,
        hosted=hosted,
    )


def media_bytes(url: str, fetch) -> bytes:
    """미디어 바이트. `data:` URI 는 그 자리에서 풀고, 그 밖은 `fetch` 로 받는다.

    Notion 의 "외부" 이미지가 실제로는 원본 안에 그대로 인코딩돼 있는 경우가 있다
    (`_media_of_block` 참조). 그때는 내려받을 곳이 없다 — `OutboundClient` 에 `data:`
    URI 를 넘기면 스킴이 http/https 가 아니라 허용 목록에서 거절되므로, 애초에
    네트워크로 보내지 않고 여기서 바로 디코드한다.
    """
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        if ";base64" not in header:
            raise NotionSourceError("base64 가 아닌 data URI 는 지원하지 않습니다")
        try:
            return base64.b64decode(payload, validate=True)
        except binascii.Error as exc:
            raise NotionSourceError(f"data URI 를 읽지 못했습니다: {exc}") from exc
    return fetch(url)


def media_of(page_id: str, raw_blocks) -> list[NotionMedia]:
    """페이지 본문이 들고 있는 파일 전부. **중첩 안까지 본다.**

    실측에서 이미지는 컬럼이나 토글 안에 들어 있는 것이 흔하다. 최상위만 훑으면 그
    그림들이 조용히 빠지고, 빠졌다는 사실은 아무 데도 안 남는다.
    """
    out: list[NotionMedia] = []
    for block in raw_blocks or []:
        if not isinstance(block, dict):
            continue
        found = _media_of_block(page_id, block)
        if found is not None:
            out.append(found)
        out.extend(media_of(page_id, block.get("_children") or []))
    return out


def notion_blocks_to_doc(raw_blocks, *, media_urls: dict[str, str] | None = None) -> dict:
    """Notion 블록 목록 → Block JSON 문서. **정규화는 부르는 쪽이 한다.**

    여기서 `blocks.normalize` 를 부르지 않는 이유는 앞판 이어붙이기다 — 재실행에서
    블록 id 를 이어 주려면 `carry_from` 이 필요하고, 그 값은 DB 를 봐야 안다(D-247).

    `media_urls` 는 「블록 id → 우리 첨부 주소」다. 적재가 바이트를 옮긴 뒤에 넘긴다 —
    비어 있으면 이미지 자리에 사람이 읽는 한 문장이 남는다. Notion 서명 URL 을 대신
    넣지 않는 이유는 D4 에 있다: 그 주소는 한 시간이면 죽고, 죽었다는 사실은 사용자가
    문서를 열어 깨진 그림을 볼 때만 드러난다.
    """
    resolved = media_urls or {}
    content: list[dict] = []
    pending_kind: str | None = None
    pending_items: list[dict] = []

    def flush() -> None:
        nonlocal pending_kind, pending_items
        if pending_kind and pending_items:
            content.append({"type": pending_kind, "content": pending_items})
        pending_kind, pending_items = None, []

    for block in raw_blocks or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type") or ""
        holder = block.get(btype)
        holder = holder if isinstance(holder, dict) else {}
        raw_children = block.get("_children") or []
        # 표는 자식을 **자기가** 읽는다(`table_row`). 먼저 문서로 바꿔 두면 셀이
        # 자리표시자 문단이 되어 버리고, 그러면 셀 글자를 두 번 넣는 꼴이 된다.
        children = (
            [] if btype == "table"
            else notion_blocks_to_doc(raw_children, media_urls=resolved).get("content") or []
        )

        if btype in _LIST_KIND:
            kind = _LIST_KIND[btype]
            if pending_kind != kind:
                flush()
                pending_kind = kind
            pending_items.append(_list_item(_inline(holder.get("rich_text")), children))
            continue

        flush()

        if btype == "paragraph":
            inline = _inline(holder.get("rich_text"))
            # 빈 문단은 넣지 않는다 — Notion 본문에는 간격용 빈 블록이 흔하고, 그대로
            # 옮기면 편집기에 빈 문단이 줄줄이 남는다.
            if inline:
                content.append({"type": "paragraph", "content": inline})
            content.extend(children)
        elif btype in _HEADING_LEVEL:
            content.append({
                "type": "heading",
                "attrs": {"level": _HEADING_LEVEL[btype]},
                "content": _inline(holder.get("rich_text")),
            })
            content.extend(children)
        elif btype == "to_do":
            mark = _TODO_MARK[bool(holder.get("checked"))]
            inline = [{"type": "text", "text": mark}, *_inline(holder.get("rich_text"))]
            content.append({"type": "bulletList", "content": [_list_item(inline, children)]})
        elif btype in ("quote", "callout"):
            inner: list[dict] = []
            inline = _inline(holder.get("rich_text"))
            if inline:
                inner.append({"type": "paragraph", "content": inline})
            inner.extend(children)
            content.append({"type": "blockquote", "content": inner or [_paragraph("")]})
        elif btype == "toggle":
            inline = _inline(holder.get("rich_text"))
            if inline:
                content.append({"type": "paragraph", "content": inline})
            content.extend(children)
        elif btype == "code":
            language = holder.get("language")
            content.append({
                "type": "codeBlock",
                "attrs": {"language": language if isinstance(language, str) else ""},
                "content": _inline(holder.get("rich_text")) or [],
            })
        elif btype == "divider":
            content.append({"type": "horizontalRule"})
        elif btype == "table":
            node = _table(holder, raw_children)
            if node is not None:
                content.append(node)
        elif btype == "table_row":
            # 표 밖에 홀로 온 줄. 부모 표가 이미 읽었으므로 여기 오면 원본이 이상한
            # 것이고, 셀 글자만 문단으로 건진다 — 버리면 그 글자가 어디에도 안 남는다.
            for cell in (holder.get("cells") or []):
                inline = _inline(cell)
                if inline:
                    content.append({"type": "paragraph", "content": inline})
        elif btype == "image":
            caption = _plain(holder.get("caption"))
            src = resolved.get(block.get("id"))
            if src:
                content.append({
                    "type": "image",
                    "attrs": {"src": src, "alt": caption, "title": None},
                })
            else:
                content.append(_paragraph(_LOST_IMAGE))
                if caption:
                    content.append(_paragraph(caption))
        elif btype in MEDIA_BLOCKS:
            # 이미지가 아닌 바이트(문서·압축·녹화). 본문에는 **사람이 읽는 링크 문단**을
            # 남긴다 — 첨부 목록에만 넣으면 「이 문단 다음에 규격서가 있었다」가 사라진다.
            found = _media_of_block("", {**block, "id": block.get("id") or "?"})
            href = resolved.get(block.get("id"))
            if found is None:
                content.append(_paragraph(_LOST_FILE))
            elif href:
                content.append(_link_paragraph(found.name, href))
            else:
                content.append(_paragraph(f"{_LOST_FILE} {found.name}"))
            caption = _plain(holder.get("caption"))
            if caption:
                content.append(_paragraph(caption))
        elif btype in ("bookmark", "embed", "link_preview", "link_to_page"):
            href = holder.get("url")
            caption = _plain(holder.get("caption"))
            if isinstance(href, str) and href.strip():
                content.append(_link_paragraph(caption or href.strip(), href.strip()))
            elif caption:
                content.append(_paragraph(caption))
        elif btype == "equation":
            expression = (holder.get("expression") or "").strip()
            if expression:
                content.append({
                    "type": "codeBlock",
                    "attrs": {"language": ""},
                    "content": [{"type": "text", "text": expression}],
                })
        elif btype in _TRANSPARENT_BLOCKS:
            # 자기 자신은 아무 글자도 안 갖는다. 자식만 이어 붙이고 자리표시자는 안 남긴다.
            content.extend(children)
        else:
            # 여기 오는 것은 정말 못 옮기는 것뿐이다(예: `child_database`). 사람이 읽는
            # 문장 하나로 자리를 남긴다 — 지우면 그 자리가 있었다는 사실까지 사라진다.
            content.append(_paragraph(_LOST_BLOCK))
            content.extend(children)

    flush()
    return {"type": "doc", "content": content}


def notion_blocks_to_markdown(raw_blocks, *, media_urls: dict[str, str] | None = None) -> str:
    """블록 → 마크다운. 티켓 본문(`tickets.body_markdown`)이 이 형태다."""
    doc = notion_blocks_to_doc(raw_blocks, media_urls=media_urls)
    return block_mod.to_markdown(block_mod.normalize(doc))


# ── Migration Exception 분류 (U11 · D-197) ───────────────────────────────────


@dataclass(frozen=True)
class TicketExceptionVerdict:
    reason: str | None
    evidence: dict = field(default_factory=dict)

    @property
    def excepted(self) -> bool:
        return self.reason is not None


def classify_ticket_exception(
    *,
    project_ids: list[str],
    resolved_project_id: str | None,
    notion_missing: bool,
) -> TicketExceptionVerdict:
    """이 티켓에 번호를 줘도 되는가. 안 되면 **왜인지**.

    순서가 중요하다. 「원본에서 사라졌다」가 먼저다 — 사라진 티켓의 프로젝트 관계를
    다시 따지는 것은 이미 없는 것을 보고 판정하는 일이다.

    **임의로 하나를 고르지 않는다.** 잘못 배정한 티켓은 남의 부서로 새고, 그 사고는
    화면이 정상으로 보이기 때문에 아무도 신고하지 않는다(U11).
    """
    if notion_missing:
        return TicketExceptionVerdict(
            work_models.EXC_SOURCE_MISSING, {"project_ids": list(project_ids)}
        )
    if len(project_ids) > 1:
        return TicketExceptionVerdict(
            work_models.EXC_AMBIGUOUS, {"project_ids": list(project_ids)}
        )
    if not project_ids:
        return TicketExceptionVerdict(work_models.EXC_MISSING, {"project_ids": []})
    if resolved_project_id is None:
        return TicketExceptionVerdict(
            work_models.EXC_UNRESOLVED, {"project_ids": list(project_ids)}
        )
    return TicketExceptionVerdict(None)


# ── 재채번 ───────────────────────────────────────────────────────────────────


def assign_sequences(
    *, existing: dict[str, int], candidates: list[tuple[str, int | None, str]]
) -> dict[str, int]:
    """프로젝트 하나 안에서 번호를 매긴다. **이미 받은 번호는 안 움직인다.**

    `existing` 은 `{ticket_id: seq}` — 앞 회차가 준 번호다. `candidates` 는
    `(ticket_id, 옛 번호, 정렬 보조키)` 이고, 옛 번호 순으로 1 부터 채운다.

    이미 번호를 받은 티켓을 다시 매기지 않는 이유는 `canonical_key` 가 외부
    식별자이기 때문이다(§5.2 「삭제 후에도 재사용하지 않는다」). 재실행 때마다 번호가
    밀리면 어제 공유한 링크가 오늘 다른 티켓을 연다.

    옛 번호가 없는 티켓은 **뒤로 간다.** 앞에 끼우면 옛 번호가 있는 티켓의 번호가
    밀린다 — 그것이 정확히 위에서 막으려는 것이다.
    """
    out = dict(existing)
    used = set(out.values())
    nxt = (max(used) + 1) if used else 1

    def sort_key(item: tuple[str, int | None, str]):
        _tid, legacy_no, tiebreak = item
        return (legacy_no is None, legacy_no if legacy_no is not None else 0, tiebreak)

    for ticket_id, _legacy_no, _tiebreak in sorted(candidates, key=sort_key):
        if ticket_id in out:
            continue
        out[ticket_id] = nxt
        nxt += 1
    return out


# ── 지식 공간 ────────────────────────────────────────────────────────────────

_SLUG_STRIP = re.compile(r"[^a-z0-9-]+")


def space_slug(*, owner_kind: str, owner_id: str | None) -> str:
    """공간 주소. **소유 축에서 결정론적으로 만든다.**

    임의로 붙이면 재실행 때 같은 소유의 공간이 두 개가 되고, 문서가 두 공간에 갈린다.
    """
    base = f"{owner_kind}-{owner_id}" if owner_id else owner_kind
    slug = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    slug = _SLUG_STRIP.sub("-", slug.lower()).strip("-")
    return (slug or "space")[:64]
