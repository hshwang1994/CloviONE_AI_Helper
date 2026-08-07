"""Notion "작업" DB 쓰기 계층 (사용자 셀프서비스 티켓 수동 편집).

조회(notion_source)와 마찬가지로 앱→Notion 호출은 OutboundClient 단일 관문만 지난다
(allowlist=services, redirect 미추적, secret 주입). 이 모듈은 단건 페이지 조회/수정과 DB 스키마
조회, 그리고 러너에서 이식한 속성 페이로드 빌더(property_value)를 담당한다.

토큰은 secrets_dir/<notion_report_token_ref> 파일 참조로만 읽는다(평문 노출 없음). 이번 세션에서
같은 토큰으로 pages.create 가 실제로 동작함을 확인했다(쓰기 권한 보유).
"""

from __future__ import annotations

import concurrent.futures

from app.core.errors import AppError, ValidationAppError
from app.reports.notion_source import (
    PROP_ACT,
    PROP_CATEGORY,
    PROP_DIFFICULTY,
    PROP_DUE,
    PROP_EST,
    PROP_PEOPLE,
    PROP_PRIORITY,
    PROP_PROJECT,
    PROP_START,
    PROP_STATUS,
    PROP_TITLE,
    NotionNotConfiguredError,
    NotionQueryError,
    _parse_row,
)

# 도메인 필드 → 작업 DB 속성명 후보(rename 대비 별칭). Notion 속성명이 나타나는 곳은 이 모듈과
# notion_source 뿐이어야 한다(경계 정적검사) — 서비스 계층은 도메인 이름만 쓴다.
EDIT_PROP_ALIASES: dict[str, list[str]] = {
    "title": [PROP_TITLE],
    "status": [PROP_STATUS, "진행 상태"],
    "difficulty": [PROP_DIFFICULTY],
    "priority": [PROP_PRIORITY],
    "est_wd": [PROP_EST],
    "act_wd": [PROP_ACT],
    "due_date": [PROP_DUE],
    "start": [PROP_START],
    "category": [PROP_CATEGORY],
    "assignee_notion_ids": [PROP_PEOPLE],
    "project": [PROP_PROJECT],
}


def schema_prop(schema: dict, names: list[str]) -> tuple[str | None, dict | None]:
    """별칭 후보 중 스키마에 실제로 있는 속성 (이름, 정의) 을 돌려준다. 없으면 (None, None)."""
    for n in names:
        p = schema.get(n)
        if isinstance(p, dict):
            return n, p
    return None, None


def schema_prop_for(schema: dict, field: str) -> tuple[str | None, dict | None]:
    """도메인 필드 이름으로 스키마 속성을 찾는다(EDIT_PROP_ALIASES 경유)."""
    return schema_prop(schema, EDIT_PROP_ALIASES.get(field) or [])


class TicketNotFoundError(AppError):
    """대상 티켓(Notion 페이지)이 없거나 접근할 수 없다."""

    status_code = 404
    code = "ticket_not_found"
    default_message = "티켓을 찾을 수 없습니다."


def _headers(settings) -> dict[str, str]:
    return {
        "Notion-Version": settings.notion_api_version,
        "Content-Type": "application/json",
    }


def _request(
    outbound, settings, method: str, path: str, *, json: dict | None = None,
    not_found: type[AppError] = TicketNotFoundError,
) -> dict:
    """Notion REST 단건 호출. 토큰 미설정/유효하지 않음/404/기타 오류를 도메인 예외로 매핑한다.

    notion_source._query_tasks 와 같은 오류 처리 규약을 따른다(토큰 파일 없음→NotConfigured,
    401→NotConfigured, 404→not_found, 그 외 4xx/5xx→NotionQueryError).

    `not_found` 를 인자로 받는 이유: 이 오류 매핑은 작업 DB 전용이 아니라 **Notion REST 전체**
    의 규약인데, 404 문구만 도메인마다 다르다. 프로젝트 페이지가 없을 때 "티켓을 찾을 수
    없습니다" 라고 답하면 사용자는 자기가 안 건드린 것을 의심하며 엉뚱한 화면을 뒤진다.
    """
    url = f"{settings.notion_api_base.rstrip('/')}/{path.lstrip('/')}"
    try:
        resp = outbound.request(
            method,
            url,
            allowlist="services",
            json=json,
            headers=_headers(settings),
            timeout=30.0,
            auth_type="bearer",
            secret_ref=settings.notion_report_token_ref,
            # S9 — 쓰기 경로에도 건다. 429 는 **처리하지 않았다**는 뜻이라 블록 추가처럼
            # 두 번 하면 안 되는 요청도 다시 보내는 것이 안전하다(5xx 였다면 안 걸었다).
            # 안 걸면 본문 저장이 429 하나로 실패하고, 사용자는 방금 쓴 글이 원본에 안 갔다는
            # 배너를 보게 된다.
            rate_limit_retries=3,
        )
    except FileNotFoundError as exc:
        raise NotionNotConfiguredError() from exc
    except Exception as exc:  # 네트워크/전송 오류
        if settings.notion_report_token_ref in str(exc):
            raise NotionNotConfiguredError() from exc
        raise NotionQueryError(f"Notion 요청 실패: {type(exc).__name__}") from exc

    if resp.status_code == 401:
        raise NotionNotConfiguredError("Notion 토큰이 유효하지 않습니다(401).")
    if resp.status_code == 404:
        raise not_found()
    if resp.status_code >= 400:
        # Notion 이 주는 message 를 붙여 관리자가 원인을 볼 수 있게 한다(값은 담기지 않는다).
        detail = ""
        try:
            body = resp.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or "")
        except Exception:
            detail = ""
        suffix = f" - {detail}" if detail else ""
        raise NotionQueryError(f"Notion 응답 오류: HTTP {resp.status_code}{suffix}")
    return resp.json()


def notion_request(
    outbound, settings, method: str, path: str, *, json: dict | None = None,
    not_found: type[AppError] | None = None,
) -> dict:
    """다른 Notion DB(프로젝트)를 다루는 모듈이 **이 오류 매핑을 다시 적지 않게** 연 문.

    복사해 가면 규약이 두 벌이 된다: 한쪽만 401 을 '미연동'으로 번역하고 다른 쪽은 502 로
    올리는 식으로 갈라지고, 그때 증상은 "어떤 동기화만 연동 안내가 안 뜬다" 가 된다. 오류
    번역은 화면 문구를 정하는 판단이라 한 곳에 있어야 한다.

    이름을 `_request` 로 두고 밖에서 부르지 않는 이유는 반대다 - 밑줄은 "이 파일 안에서만"
    이라는 약속인데 그걸 다른 모듈이 어기면 약속 자체가 의미를 잃는다.
    """
    return _request(
        outbound, settings, method, path, json=json,
        not_found=not_found or TicketNotFoundError,
    )


def fetch_schema(outbound, settings, database_id: str | None = None) -> dict:
    """DB 스키마의 properties(속성명→정의) 를 돌려준다. rename/타입 표류 방어에 쓴다.

    `database_id` 를 안 주면 작업 DB 다(기존 호출부 전부). 프로젝트 DB 처럼 다른 DB 의
    스키마도 같은 함수로 읽는다 - 스키마 읽기는 DB 마다 다를 것이 없다.
    """
    data = _request(
        outbound, settings, "GET",
        f"/v1/databases/{database_id or settings.notion_tasks_database_id}",
    )
    props = data.get("properties")
    return props if isinstance(props, dict) else {}


def fetch_ticket(outbound, settings, page_id: str) -> dict:
    """단건 티켓(페이지)을 읽어 notion_source._parse_row 와 같은 형태로 돌려준다."""
    data = _request(outbound, settings, "GET", f"/v1/pages/{page_id}")
    return _parse_row(data)


def update_ticket_properties(outbound, settings, *, page_id: str, properties: dict) -> dict:
    """페이지 속성을 PATCH 하고, 반영된 페이지를 파싱해 돌려준다."""
    data = _request(
        outbound, settings, "PATCH", f"/v1/pages/{page_id}",
        json={"properties": properties},
    )
    return _parse_row(data)


def archive_page(outbound, settings, *, page_id: str) -> dict:
    """페이지를 보관처리(archive=휴지통으로) 한다 — 휴지통 보관기간이 지난 뒤 영구 삭제 시 호출.
    Notion 자체 휴지통에 들어가 30일간 복구 가능하므로 실수에도 되돌릴 여지가 있다."""
    return _request(outbound, settings, "PATCH", f"/v1/pages/{page_id}", json={"archived": True})


# 본문 블록 읽기(1레벨) — 티켓 상세를 우리 화면에서 읽기용으로 보여준다(문서 상세와 같은 구조).
_MAX_BLOCK_PAGES = 20
# Notion children append 한 번의 상한(API 제약). markdown_to_blocks 의 MAX_BLOCKS 와 같은 값이다.
_MAX_CHILDREN = 100
# 본문 교체에서 지워도 되는 기존 블록 수의 상한. 삭제는 블록당 DELETE 한 번이라 여기가 곧
# 요청 하나의 외부 왕복 수다. 우리 편집기가 만드는 본문은 최대 100줄이므로, 이보다 큰 원본을
# 여기서 교체한다는 건 남이 Notion 에서 쓴 문서를 통째로 지운다는 뜻이다.
_MAX_REPLACE_BLOCKS = 200
_TEXT_BLOCK_TYPES = {
    "paragraph": "paragraph", "heading_1": "heading_1", "heading_2": "heading_2",
    "heading_3": "heading_3", "bulleted_list_item": "bulleted", "numbered_list_item": "numbered",
    "to_do": "todo", "quote": "quote", "callout": "callout", "toggle": "toggle", "code": "code",
}


def _block_text(block: dict, btype: str) -> str:
    container = block.get(btype)
    if not isinstance(container, dict):
        return ""
    rich = container.get("rich_text") or []
    return "".join(s.get("plain_text", "") for s in rich if isinstance(s, dict))


def _image_view(block: dict) -> dict | None:
    """이미지 블록 → 화면이 그릴 수 있는 형태. 모르는 모양이면 None.

    ## URL 을 프록시하지 않고 그대로 내려보내는 이유

    Notion 호스팅 파일의 URL 은 **만료되는 서명 URL**(보통 1시간)이라 우리가 저장해 둘 수 없고,
    프록시하려면 그 S3 호스트를 SSRF 허용목록에 넣어야 한다. 허용목록은 이 제품의 아웃바운드
    방어선이라 이미지 하나 보자고 넓힐 자리가 아니다.

    반대로 브라우저가 직접 받으면 허용목록을 건드리지 않는다. CSP 의 `img-src` 가 https: 를
    허용하도록 이미 열려 있고(2026-08-04 사용자 지시), 이 URL 을 보는 사람은 **이미 그 티켓을
    읽을 수 있는 사람**이라 새로 열리는 권한이 없다. 서명 URL 이라 노출 시간도 스스로 끝난다.

    대가는 하나: 화면을 한 시간 넘게 켜 두면 이미지 링크가 만료된다. 새로고침하면 새 URL 이
    내려온다. 사라지는 것도 아니고 되돌릴 수 없는 것도 아니라 이 쪽이 낫다고 봤다.
    """
    payload = block.get("image")
    if not isinstance(payload, dict):
        return None
    holder = payload.get(payload.get("type") or "")
    url = holder.get("url") if isinstance(holder, dict) else None
    if not url:
        return None
    caption = "".join(
        s.get("plain_text", "") for s in (payload.get("caption") or []) if isinstance(s, dict)
    )
    return {"kind": "image", "url": url, "text": caption}


def fetch_page_blocks(outbound, settings, page_id: str) -> list[dict]:
    """티켓 페이지 본문을 얕게 읽어 렌더용 [{kind, text, checked?}] 로 돌려준다(문서 상세와 동일 형식).
    지원 밖 블록은 '[원본에서 확인]' 자리표시. 온전한 열람은 원본 링크로."""
    path = f"/v1/blocks/{page_id}/children"
    out: list[dict] = []
    cursor: str | None = None
    for _ in range(_MAX_BLOCK_PAGES):
        q = "?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        data = _request(outbound, settings, "GET", path + q)
        for block in data.get("results", []):
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "divider":
                out.append({"kind": "divider", "text": ""})
            elif btype in _TEXT_BLOCK_TYPES:
                item = {"kind": _TEXT_BLOCK_TYPES[btype], "text": _block_text(block, btype)}
                if btype == "to_do":
                    item["checked"] = bool((block.get("to_do") or {}).get("checked"))
                out.append(item)
            elif btype == "image":
                image = _image_view(block)
                # URL 을 못 읽으면(모르는 모양) 예전처럼 자리표시로 둔다 — 깨진 <img> 보다 낫다.
                out.append(image if image else {"kind": "unsupported", "text": "[image] 원본에서 확인"})
            else:
                out.append({"kind": "unsupported", "text": f"[{btype}] 원본에서 확인"})
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out


def page_block_ids(outbound, settings, page_id: str, *, limit: int | None = None) -> list[str]:
    """페이지 본문(1레벨 children)의 블록 id 목록.

    `limit` 을 주면 그 개수를 넘어서는 순간 멈춘다(넘었는지 알 수 있게 limit+1 개까지 모은다).
    """
    return [bid for bid, _ in page_block_refs(outbound, settings, page_id, limit=limit)]


def page_block_refs(
    outbound, settings, page_id: str, *, limit: int | None = None
) -> list[tuple[str, str]]:
    """(블록 id, 블록 타입) 목록.

    타입이 필요한 이유: 본문을 저장할 때 **우리 편집기가 표현할 수 있는 블록만** 지워야 한다.
    예전에는 id 만 모아 전부 지웠고, 그래서 이미지·표가 저장 한 번에 사라졌다.
    """
    path = f"/v1/blocks/{page_id}/children"
    refs: list[tuple[str, str]] = []
    cursor: str | None = None
    for _ in range(_MAX_BLOCK_PAGES):
        q = "?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        data = _request(outbound, settings, "GET", path + q)
        for block in data.get("results", []):
            if isinstance(block, dict) and block.get("id"):
                refs.append((block["id"], block.get("type") or ""))
        if limit is not None and len(refs) > limit:
            return refs
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return refs


# 우리 편집기가 마크다운으로 **표현할 수 있는** 블록 타입. 저장할 때 지워도 되는 것은 이것뿐이다.
# 이 집합 밖(image/table/embed/file/video/child_page…)은 편집기에 애초에 실려 오지 않으므로,
# 지우면 사용자가 만든 적도 없는 내용을 없애는 것이 된다.
_EDITABLE_BLOCK_TYPES = set(_TEXT_BLOCK_TYPES) | {"divider"}


def replace_page_body(outbound, settings, *, page_id: str, blocks: list[dict]) -> None:
    """본문의 **글 부분만** 교체한다. 이미지·표 같은 비텍스트 블록은 건드리지 않는다.

    ## 왜 '통째로 교체'를 그만뒀나

    예전에는 1레벨 children 을 전부 지우고 새로 넣었다. 그 결과 **저장 한 번에 원본의
    이미지·표가 사라졌다** — 편집기에는 애초에 실려 오지도 않는(마크다운으로 표현할 수 없어
    `[image] 원본에서 확인` 자리표시로 바뀌는) 내용이라, 사용자는 자기가 무엇을 지웠는지도
    몰랐다. 화면에 경고를 띄워 두긴 했지만, 경고는 유실을 막지 못한다.

    사용자 지시(2026-08-04)로 이 포털이 **노션을 대신하는 유일한 창구**가 되면 그 유실은
    곧 사용자 데이터 유실이다. 그래서 지우는 대상을 '우리가 표현할 수 있는 블록'으로 좁혔다.

    ## 왜 지웠다 다시 만들지 않나 (순서를 지키려면 그게 맞아 보이는데)

    Notion 호스팅 파일(`image.type == "file"`)은 **API 로 재생성할 수 없다**. 읽을 때 나오는
    URL 은 만료되는 서명 URL 이고, 그 URL 로 새 블록을 만들면 곧 죽은 링크가 된다.
    (외부 URL 이미지만 재생성 가능하다.) AI 도우미가 붙이는 이미지가 정확히 이 '호스팅 파일'
    쪽이라, 지웠다 다시 만드는 길은 애초에 없다. **안 지우는 것이 유일한 방법이다.**

    ## 그래서 순서는 어떻게 되나

    지우지 않은 비텍스트 블록이 앞에 남고, 새로 쓴 글이 그 뒤에 붙는다. 원본에서 이미지가
    글 중간에 있었다면 위치가 앞으로 모인다. 위치가 바뀌는 것과 내용이 사라지는 것 중
    무엇이 나은지는 물어볼 필요가 없다. 화면 안내 문구도 이 동작에 맞춰 고쳤다.

    ## 실패 시

    순서를 **삭제 → 추가**로 두는 이유는 재시도 수렴이다: 중간에 실패해도 같은 본문으로 다시
    저장하면 원하는 상태가 된다. 반대로 하면 실패할 때마다 본문이 한 벌씩 늘어난다.
    실패해도 우리 DB 의 정본(body_markdown)은 이미 저장된 뒤라 사용자 글은 살아 있다.

    원본이 아주 큰 페이지는 손대지 않고 거절한다(_MAX_REPLACE_BLOCKS) — 삭제가 블록당 한 번의
    DELETE 라 수백 개면 요청 하나가 수백 왕복이 된다.

    ## 삭제를 동시에 보내는 이유 (PF8)

    블록이 여러 개면 예전에는 DELETE 를 하나씩 순서대로 기다렸다 — 본문 저장 한 번이 블록
    수만큼의 Notion 왕복이 됐다(수십 개짜리 본문이면 화면 하나 저장에 수십 회). 블록끼리는
    서로 독립이라(삭제 순서가 결과에 영향 없다) 굳이 기다릴 이유가 없다. 429 재시도
    (`rate_limit_retries`)는 `_request` 안에서 호출 하나마다 자기 완결적으로 도니 여러 스레드가
    동시에 재시도해도 서로 침범하지 않는다. 실패 하나가 있으면(어느 스레드든) 그대로 올려
    새 본문은 붙이지 않는다 — 위 "실패 시" 절의 재시도 수렴이 이 순서(전부 삭제 확인 → 추가)
    에 의존하기 때문이다.
    """
    refs = page_block_refs(outbound, settings, page_id, limit=_MAX_REPLACE_BLOCKS)
    if len(refs) > _MAX_REPLACE_BLOCKS:
        raise ValidationAppError(
            f"원본 본문이 너무 커서(블록 {_MAX_REPLACE_BLOCKS}개 초과) 여기서 교체하지 않았습니다. "
            f"원본에서 편집해 주세요."
        )
    # 편집기가 표현할 수 없는 블록은 사용자가 지운 적이 없다 — 그대로 둔다.
    deletable = [bid for bid, btype in refs if not btype or btype in _EDITABLE_BLOCK_TYPES]
    if deletable:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(deletable))) as pool:
            futures = [
                pool.submit(_request, outbound, settings, "DELETE", f"/v1/blocks/{block_id}")
                for block_id in deletable
            ]
            for future in futures:
                future.result()  # 하나라도 실패하면 여기서 그대로 올린다(추가는 하지 않는다).
    if blocks:
        _request(
            outbound, settings, "PATCH", f"/v1/blocks/{page_id}/children",
            json={"children": blocks[:_MAX_CHILDREN]},
        )


def property_value(prop: dict, value):
    """스키마 속성 타입에 맞는 Notion 쓰기 페이로드를 만든다(러너 property_value 이식).

    편집(status/select/date/number/people)과 생성(title/rich_text/relation)에 필요한 타입을 모두
    지원한다. 지원하지 않는 타입은 None(호출측이 '적용 불가'로 처리). 빈 값 규약:
      - date: 빈 값 → {"date": None}(삭제). Notion 은 {"start": ""} 를 400 으로 거절한다.
      - select: 빈 값 → {"select": None}(값 지움).
      - number: None/공백 → {"number": None}. 캐스팅 실패는 None(적용 불가)로 흘린다.
    """
    kind = prop.get("type")
    if kind == "title":
        return {"title": [{"type": "text", "text": {"content": str(value or "")[:2000]}}]}
    if kind == "rich_text":
        return {"rich_text": [{"type": "text", "text": {"content": str(value or "")[:2000]}}]}
    if kind == "status":
        return {"status": {"name": value}} if value else None
    if kind == "select":
        return {"select": {"name": value}} if value else {"select": None}
    if kind == "date":
        text = value if isinstance(value, str) else ""
        return {"date": {"start": text}} if text.strip() else {"date": None}
    if kind == "number":
        if value is None or (isinstance(value, str) and not value.strip()):
            return {"number": None}
        try:
            return {"number": float(value)}
        except (TypeError, ValueError):
            return None
    if kind == "people":
        ids = value if isinstance(value, list) else [value]
        return {"people": [{"id": v} for v in ids if v]}
    if kind == "relation":
        ids = value if isinstance(value, list) else [value]
        return {"relation": [{"id": v} for v in ids if v]}
    return None


def relation_target_db(prop: dict) -> str | None:
    """relation 속성이 가리키는 대상 데이터베이스 id(프로젝트 목록을 스키마에서 자동 발견하는 데 쓴다)."""
    if prop.get("type") != "relation":
        return None
    rel = prop.get("relation")
    return rel.get("database_id") if isinstance(rel, dict) else None


def paragraph_block(text_str: str) -> dict:
    """설명 본문을 담는 문단 블록(생성 시 children)."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": str(text_str or "")[:2000]}}]},
    }


def create_page(outbound, settings, *, parent_database_id: str, properties: dict, children: list | None = None) -> dict:
    """작업 DB에 새 페이지(티켓)를 만들고 파싱된 결과를 돌려준다."""
    body: dict = {"parent": {"database_id": parent_database_id}, "properties": properties}
    if children:
        body["children"] = children
    data = _request(outbound, settings, "POST", "/v1/pages", json=body)
    return _parse_row(data)


def query_relation_titles(outbound, settings, database_id: str, *, limit_pages: int = 5) -> list[dict]:
    """relation 대상 DB(예: 프로젝트)를 조회해 [{id, name}] 목록을 돌려준다(제목만).

    Notion 페이지의 title 속성명은 DB마다 다를 수 있어(예: '프로젝트'/'Name'), title 타입 속성을
    자동으로 찾아 텍스트를 뽑는다.
    """
    url_path = f"/v1/databases/{database_id}/query"
    rows: list[dict] = []
    cursor = None
    for _ in range(max(1, limit_pages)):
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _request(outbound, settings, "POST", url_path, json=body)
        for page in data.get("results", []):
            if not isinstance(page, dict):
                continue
            props = page.get("properties") or {}
            name = ""
            for v in props.values():
                if isinstance(v, dict) and v.get("type") == "title":
                    name = "".join(seg.get("plain_text", "") for seg in (v.get("title") or []) if isinstance(seg, dict)).strip()
                    break
            rows.append({"id": page.get("id"), "name": name})
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return rows


def option_names(prop: dict) -> list[str]:
    """select/status 속성의 허용 옵션명 목록. 다른 타입이면 빈 목록."""
    kind = prop.get("type")
    if kind not in ("select", "status"):
        return []
    container = prop.get(kind)
    options = container.get("options") if isinstance(container, dict) else None
    return [o.get("name") for o in (options or []) if isinstance(o, dict) and o.get("name")]
