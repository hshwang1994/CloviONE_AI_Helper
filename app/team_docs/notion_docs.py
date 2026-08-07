"""Notion "문서" 데이터베이스 조회 계층 (팀 공간 §17).

app/reports/notion_source.py 와 같은 규약: 외부 호출은 OutboundClient 단일 관문(allowlist=
services, redirect 금지, secret 주입)만 지나고, 토큰은 secrets_dir 파일 참조(notion_docs_token_ref)
로만 읽는다. 이 모듈은 원시 데이터만 돌려주고, 캐시 매핑·집계는 sync.py/service.py가 한다.

**프롬프트 인젝션 방어(§11.3/§17.2)**: 문서 본문·속성은 전부 '데이터'로만 취급한다. 여기서
문자열을 명령으로 해석하거나 실행하는 경로는 없다(블록은 타입+텍스트로만 구조화해 돌려주고,
프런트가 textContent로만 렌더한다).
"""

from __future__ import annotations

import concurrent.futures

from app.core.errors import AppError, ValidationAppError

# 우리가 읽는 "문서" DB 속성 이름 — Notion 스키마와 정확히 일치해야 한다(§17.2 추측 금지, 실제 확인함).
PROP_TITLE = "제목"
PROP_TYPE = "유형"
PROP_CATEGORY = "카테고리"
PROP_PROJECT = "프로젝트"
PROP_STATUS = "상태"
PROP_PRIORITY = "우선순위"
PROP_AUTHOR = "작성자"
PROP_OWNER = "소유자"
PROP_DATE = "날짜"
PROP_ORIG_DATE = "원본 생성일"
PROP_ORIG_URL = "원본 URL"
PROP_SOURCE = "출처"
PROP_MEMO = "메모"
PROP_FAVORITE = "즐겨찾기"
PROP_ARCHIVED = "보관됨"
PROP_FILES = "첨부파일"
PROP_MEDIA = "파일과 미디어"

_RELATION_PROPS = (PROP_TYPE, PROP_CATEGORY, PROP_PROJECT)

_MAX_PAGES = 100  # 100 x 100 = 10000건 상한(무한 루프 방지). 초과 시 truncated=True로 알린다.
_MAX_RELATION_PAGES = 50  # relation 대상 DB 제목 해석 상한(100 x 50 = 5000행)
_MAX_BLOCK_PAGES = 20


class NotionDocsNotConfiguredError(AppError):
    status_code = 503
    code = "notion_docs_not_configured"
    default_message = "Notion 문서 연동 토큰이 설정되지 않았습니다."


class NotionDocsQueryError(AppError):
    status_code = 502
    code = "notion_docs_query_failed"
    default_message = "Notion 문서 조회에 실패했습니다."


class NotionDocsWriteForbiddenError(AppError):
    status_code = 403
    code = "notion_docs_write_forbidden"
    default_message = (
        "Notion 통합에 문서 생성(쓰기) 권한이 없습니다. 워크스페이스에서 통합에 "
        "'콘텐츠 삽입' 권한과 문서 데이터베이스 접근을 허용해 주세요."
    )


def _headers(settings) -> dict[str, str]:
    return {
        "Notion-Version": settings.notion_api_version,
        "Content-Type": "application/json",
    }


def _require_documents_database_id(settings) -> None:
    """문서 DB id 가 비었으면 **부르기 전에** '설정 안 됨' 으로 끊는다 (P1).

    작업 DB 쪽(`app/reports/notion_source.py::_require_tasks_database_id`)과 같은 이유이고
    같은 모양이다. 빈 id 로 부르면 URL 이 `/v1/databases//query` 가 되고 Notion 은 400 을
    준다. 화면은 그걸 "조회 실패" 로 그리고, 운영자는 네트워크나 토큰을 의심하며 시간을 버린다.
    설정이 비었다는 사실은 부르기 전에 이미 안다.

    (고객사 고유값을 소스 기본값에서 비운 뒤로 이 상태가 **설치 직후의 정상 상태**가 됐다 -
    그래서 조용히 실패하면 안 된다.)
    """
    if not (settings.notion_documents_database_id or "").strip():
        raise NotionDocsNotConfiguredError(
            "노션 문서 데이터베이스 id 가 설정되지 않았습니다(NOTION_DOCUMENTS_DATABASE_ID)."
        )


def _request(outbound, settings, method: str, path: str, *, json: dict | None = None) -> dict:
    """docs 토큰으로 Notion REST를 부른다. 토큰 미설정→NotConfigured, 그 외 오류→QueryError."""
    # DB id 를 쓰는 경로만 여기서 걸린다 - 페이지 단건 조회는 id 가 필요 없다.
    if "/v1/databases/" in path:
        _require_documents_database_id(settings)
    url = f"{settings.notion_api_base.rstrip('/')}{path}"
    try:
        resp = outbound.request(
            method,
            url,
            allowlist="services",
            json=json,
            headers=_headers(settings),
            timeout=30.0,
            auth_type="bearer",
            secret_ref=settings.notion_docs_token_ref,
            # S9 — 문서 동기화 한 번이 최대 251요청이라 429 가 실제로 난다.
            rate_limit_retries=3,
        )
    except FileNotFoundError as exc:
        raise NotionDocsNotConfiguredError() from exc
    except Exception as exc:
        if settings.notion_docs_token_ref in str(exc):
            raise NotionDocsNotConfiguredError() from exc
        raise NotionDocsQueryError(f"Notion 조회 실패: {type(exc).__name__}") from exc
    if resp.status_code == 401:
        raise NotionDocsNotConfiguredError("Notion 토큰이 유효하지 않습니다(401).")
    if resp.status_code >= 400:
        raise NotionDocsQueryError(f"Notion 응답 오류: HTTP {resp.status_code}")
    return resp.json()


# ── 속성 파서 ──────────────────────────────────────────────────────────────
def _plain_title(prop: dict) -> str:
    parts = prop.get("title") or []
    return "".join(s.get("plain_text", "") for s in parts if isinstance(s, dict)).strip()


def _rich_text(prop: dict) -> str:
    parts = prop.get("rich_text") or []
    return "".join(s.get("plain_text", "") for s in parts if isinstance(s, dict)).strip()


def _relation_ids(prop: dict) -> list[str]:
    return [r.get("id") for r in (prop.get("relation") or []) if isinstance(r, dict) and r.get("id")]


def _select_name(prop: dict) -> str | None:
    sel = prop.get("select")
    return sel.get("name") if isinstance(sel, dict) else None


def _date_start(prop: dict) -> str | None:
    d = prop.get("date")
    return d.get("start") if isinstance(d, dict) else None


def _checkbox(prop: dict) -> bool:
    return bool(prop.get("checkbox"))


def _url(prop: dict) -> str | None:
    u = prop.get("url")
    return u if isinstance(u, str) and u else None


def _person_ids(prop: dict) -> list[str]:
    """person 속성에서 **소스 id** 만. 이름은 바뀌지만 id 는 안 바뀐다(X2)."""
    return [p.get("id") for p in (prop.get("people") or []) if isinstance(p, dict) and p.get("id")]


def _person_names(prop: dict) -> list[str]:
    # 통합이 People 를 읽을 수 있으면 name 이 온다. 없으면 빈 목록(소유자 텍스트로 폴백).
    return [p.get("name") for p in (prop.get("people") or []) if isinstance(p, dict) and p.get("name")]


def _has_files(*props: dict) -> bool:
    for p in props:
        if p.get("files"):
            return True
    return False


def parse_document(row: dict) -> dict:
    """원시 Notion 페이지 → 캐시 매핑 전 단계의 dict(관계는 아직 id 목록)."""
    props = row.get("properties") or {}

    def p(name: str) -> dict:
        v = props.get(name)
        return v if isinstance(v, dict) else {}

    return {
        "notion_page_id": row.get("id"),
        "url": row.get("url"),
        "last_edited": row.get("last_edited_time"),
        "created_time": row.get("created_time"),
        "title": _plain_title(p(PROP_TITLE)),
        "type_ids": _relation_ids(p(PROP_TYPE)),
        "category_ids": _relation_ids(p(PROP_CATEGORY)),
        "project_ids": _relation_ids(p(PROP_PROJECT)),
        "status": _select_name(p(PROP_STATUS)),
        "priority": _select_name(p(PROP_PRIORITY)),
        "author_names": _person_names(p(PROP_AUTHOR)),
        # id 도 같이 가져온다 (X2). 응답에 이미 들어 있는데 예전에는 이름만 남기고 버렸다.
        "author_notion_ids": _person_ids(p(PROP_AUTHOR)),
        "owner": _rich_text(p(PROP_OWNER)),
        "doc_date": _date_start(p(PROP_DATE)),
        "orig_date": _date_start(p(PROP_ORIG_DATE)),
        "original_url": _rich_text(p(PROP_ORIG_URL)) or None,
        "source_url": _url(p(PROP_SOURCE)),
        "memo": _rich_text(p(PROP_MEMO)),
        "notion_favorite": _checkbox(p(PROP_FAVORITE)),
        "archived": _checkbox(p(PROP_ARCHIVED)),
        "has_files": _has_files(p(PROP_FILES), p(PROP_MEDIA)),
    }


def query_all_documents(outbound, settings) -> tuple[list[dict], bool]:
    """"문서" DB 전체를 페이지네이션으로 읽어 (parse_document 목록, truncated) 를 돌려준다.

    truncated=True 는 상한(_MAX_PAGES)에 걸려 '더 있는데 못 받아온' 상태다 — 이 경우 호출측은
    prune(삭제 감지)을 건너뛰어야 안 받아온 문서를 삭제로 오인하지 않는다.
    """
    path = f"/v1/databases/{settings.notion_documents_database_id}/query"
    rows: list[dict] = []
    cursor: str | None = None
    truncated = False
    for _ in range(_MAX_PAGES):
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _request(outbound, settings, "POST", path, json=body)
        for row in data.get("results", []):
            if isinstance(row, dict):
                rows.append(parse_document(row))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    else:
        # for 루프가 break 없이 _MAX_PAGES를 소진 = 마지막 페이지에도 has_more가 남아 있었다.
        truncated = True
    return rows, truncated


def fetch_documents_schema(outbound, settings) -> dict:
    data = _request(
        outbound, settings, "GET",
        f"/v1/databases/{settings.notion_documents_database_id}",
    )
    props = data.get("properties")
    return props if isinstance(props, dict) else {}


def _relation_target_db(prop: dict) -> str | None:
    if not isinstance(prop, dict) or prop.get("type") != "relation":
        return None
    rel = prop.get("relation")
    return rel.get("database_id") if isinstance(rel, dict) else None


def _query_titles(outbound, settings, database_id: str) -> dict[str, str]:
    """relation 대상 DB를 조회해 {page_id: title} 맵을 만든다(제목 타입 속성 자동 탐색)."""
    path = f"/v1/databases/{database_id}/query"
    out: dict[str, str] = {}
    cursor: str | None = None
    for _ in range(_MAX_RELATION_PAGES):
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _request(outbound, settings, "POST", path, json=body)
        for page in data.get("results", []):
            if not isinstance(page, dict):
                continue
            name = ""
            for v in (page.get("properties") or {}).values():
                if isinstance(v, dict) and v.get("type") == "title":
                    name = "".join(
                        s.get("plain_text", "") for s in (v.get("title") or []) if isinstance(s, dict)
                    ).strip()
                    break
            if page.get("id"):
                out[page["id"]] = name
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out


def resolve_relation_maps(
    outbound, settings, schema: dict, *, failures: list[str] | None = None
) -> dict[str, dict[str, str]]:
    """유형·카테고리·프로젝트 relation 각각의 {page_id: name} 맵을 스키마에서 대상 DB를
    자동 발견해 만든다. 한 relation 해석이 실패해도 다른 것에 영향 주지 않는다(개별 격리).

    `failures` 를 주면 **실패한 relation 이름을 담아 준다** (C4).

    왜 필요한가: 실패를 `{}` 로 삼키면 호출측이 "그 relation 이 원래 비어 있다" 와
    "조회가 실패했다" 를 구분할 수 없다. 그런데 결과는 전혀 다르다 — 맵이 비면
    `classify([], [], title)` 로 떨어져 **전 문서의 문서종류·업무분야·기술태그가 한 번에
    '기타' 로 바뀐다**. 그런데 동기화 상태는 `ok`, error 는 `null` 이었다. 다음 성공
    동기화가 되돌리지만 그 사이(기본 600초) 필터가 전부 무너지고, 아무도 이유를 모른다.

    반환값 모양은 그대로다 — 기존 호출부와 테스트가 계속 동작한다.

    ## 세 조회를 동시에 보내는 이유 (PF8)

    유형·카테고리·프로젝트는 서로 다른 DB 를 가리키는, 서로 완전히 독립인 조회다. 예전에는
    이 셋을 순서대로 기다렸다 — 문서 목록 한 번을 채우는 데 (스키마 1 + 유형 + 카테고리 +
    프로젝트 + 문서 목록 자체) 최소 5회의 순차 Notion 왕복이 쌓였다. 셋 다 실패해도 서로
    영향이 없어야 한다는 계약(개별 격리)은 그대로 유지한다 — 병렬로 돌려도 각 future 의
    성공/실패는 각자 처리한다. 429 재시도는 `_request` 안에서 호출 하나마다 자기 완결적으로
    도니 세 스레드가 동시에 재시도해도 서로 침범하지 않는다.
    """
    targets: dict[str, str] = {}
    maps: dict[str, dict[str, str]] = {}
    for prop_name in _RELATION_PROPS:
        target = _relation_target_db(schema.get(prop_name) or {})
        if target:
            targets[prop_name] = target
        else:
            maps[prop_name] = {}
    if not targets:
        return maps
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as pool:
        future_to_prop = {
            pool.submit(_query_titles, outbound, settings, target): prop_name
            for prop_name, target in targets.items()
        }
        for future in future_to_prop:
            prop_name = future_to_prop[future]
            try:
                maps[prop_name] = future.result()
            except AppError:
                maps[prop_name] = {}  # 이 relation만 이름 미해석 — 목록은 계속 만든다
                if failures is not None:
                    failures.append(prop_name)
    return maps


# ── 본문 블록 ───────────────────────────────────────────────────────────────
_TEXT_BLOCK_TYPES = {
    "paragraph": "paragraph",
    "heading_1": "heading_1",
    "heading_2": "heading_2",
    "heading_3": "heading_3",
    "bulleted_list_item": "bulleted",
    "numbered_list_item": "numbered",
    "to_do": "todo",
    "quote": "quote",
    "callout": "callout",
    "toggle": "toggle",
    "code": "code",
}


def _block_text(block: dict, btype: str) -> str:
    container = block.get(btype)
    if not isinstance(container, dict):
        return ""
    rich = container.get("rich_text") or []
    return "".join(s.get("plain_text", "") for s in rich if isinstance(s, dict))


# ── 문서 생성(쓰기) ──────────────────────────────────────────────────────────
def resolve_names_to_ids(outbound, settings, schema: dict, prop_name: str, names) -> list[str]:
    """선택한 relation 이름들을 대상 DB에서 page id로 해석한다(생성 시 관계 연결용).
    스키마에 없거나 이름을 못 찾으면 그 이름은 조용히 건너뛴다(부분 성공)."""
    if not names:
        return []
    target = _relation_target_db(schema.get(prop_name) or {})
    if not target:
        return []
    id_to_name = _query_titles(outbound, settings, target)
    name_to_id = {name: pid for pid, name in id_to_name.items() if name}
    return [name_to_id[n] for n in names if n in name_to_id]


def list_all_project_names(outbound, settings) -> list[str]:
    """"문서" DB의 '프로젝트' relation 대상 DB에서 전체 프로젝트 제목을 돌려준다(생성 폼용).

    필터 목록은 '문서가 있는 프로젝트'만 보이지만, 새 문서 작성 시에는 문서 유무와 무관하게
    Notion에 존재하는 모든 프로젝트를 고를 수 있어야 한다(사용자 피드백). Notion 호출이므로
    실패하면 예외를 던진다 — 호출측(라우터)이 캐시 기반으로 폴백한다(목록 화면엔 영향 없음)."""
    schema = fetch_documents_schema(outbound, settings)
    target = _relation_target_db(schema.get(PROP_PROJECT) or {})
    if not target:
        return []
    id_to_name = _query_titles(outbound, settings, target)
    return sorted({n for n in id_to_name.values() if n})


def build_create_properties(
    *, title, status, priority, owner, memo, type_ids, category_ids, project_ids, author_id=None
) -> dict:
    props: dict = {PROP_TITLE: {"title": [{"text": {"content": (title or "")[:200]}}]}}
    if author_id:
        # 작성자(person)를 생성자로 채운다 — Notion People에 매핑된 사용자만(§작성자 자동 채움).
        props[PROP_AUTHOR] = {"people": [{"id": author_id}]}
    if status:
        props[PROP_STATUS] = {"select": {"name": status}}
    if priority:
        props[PROP_PRIORITY] = {"select": {"name": priority}}
    if owner:
        props[PROP_OWNER] = {"rich_text": [{"text": {"content": owner[:200]}}]}
    if memo:
        props[PROP_MEMO] = {"rich_text": [{"text": {"content": memo[:2000]}}]}
    if type_ids:
        props[PROP_TYPE] = {"relation": [{"id": i} for i in type_ids]}
    if category_ids:
        props[PROP_CATEGORY] = {"relation": [{"id": i} for i in category_ids]}
    if project_ids:
        props[PROP_PROJECT] = {"relation": [{"id": i} for i in project_ids]}
    return props


def body_children(body: str) -> list[dict]:
    """본문 텍스트를 Notion 블록으로(가벼운 마크다운 인식). 티켓 설명과 규칙을 공유하기 위해
    app.core.notion_blocks.markdown_to_blocks에 위임한다(프런트 BodyEditor 미리보기와 동일 규칙)."""
    from app.core.notion_blocks import markdown_to_blocks

    return markdown_to_blocks(body)


def create_document(outbound, settings, *, properties: dict, children: list) -> dict:
    """문서 DB에 페이지를 생성한다. 403(쓰기 권한 없음)은 명확한 메시지로 매핑한다."""
    url = f"{settings.notion_api_base.rstrip('/')}/v1/pages"
    body: dict = {
        "parent": {"database_id": settings.notion_documents_database_id},
        "properties": properties,
    }
    if children:
        body["children"] = children[:100]
    try:
        resp = outbound.request(
            "POST", url, allowlist="services", json=body, headers=_headers(settings),
            timeout=30.0, auth_type="bearer", secret_ref=settings.notion_docs_token_ref,
        )
    except FileNotFoundError as exc:
        raise NotionDocsNotConfiguredError() from exc
    except Exception as exc:
        if settings.notion_docs_token_ref in str(exc):
            raise NotionDocsNotConfiguredError() from exc
        raise NotionDocsQueryError(f"문서 생성 실패: {type(exc).__name__}") from exc
    if resp.status_code == 401:
        raise NotionDocsNotConfiguredError("Notion 토큰이 유효하지 않습니다(401).")
    if resp.status_code == 403:
        raise NotionDocsWriteForbiddenError()
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = (resp.json() or {}).get("message", "")
        except Exception:
            detail = ""
        raise NotionDocsQueryError(
            f"문서 생성 실패(HTTP {resp.status_code})" + (f": {detail}" if detail else "")
        )
    return resp.json()


def archive_page(outbound, settings, *, page_id: str) -> dict:
    """문서 페이지를 보관처리(archive=휴지통으로) 한다 — 휴지통 보관기간 초과 시 영구 삭제에서 호출.
    Notion 자체 휴지통에서 30일 복구 가능."""
    return _request(outbound, settings, "PATCH", f"/v1/pages/{page_id}", json={"archived": True})


def fetch_page_blocks(outbound, settings, page_id: str) -> list[dict]:
    """페이지 본문 블록을 얕게(1레벨) 읽어 렌더용 구조 [{kind, text, checked?}]로 돌려준다.

    지원 밖 블록(이미지·표·컬럼 등)은 '[원본에서 확인]' 자리표시로 대체한다 — 본문 전체를
    완벽 재현하지 않고 '읽을 수 있게' 보여주는 것이 목표(§17.2). 원본 링크로 온전한 열람 가능.
    """
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
                continue
            if btype in _TEXT_BLOCK_TYPES:
                item = {"kind": _TEXT_BLOCK_TYPES[btype], "text": _block_text(block, btype)}
                if btype == "to_do":
                    todo = block.get("to_do") or {}
                    item["checked"] = bool(todo.get("checked"))
                out.append(item)
            else:
                out.append({"kind": "unsupported", "text": f"[{btype}] 원본에서 확인"})
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out


# ── 본문 쓰기(포털에서 편집) ─────────────────────────────────────────────────
#
# 규칙 자체는 `app/tickets/notion_write.py::replace_page_body` 가 먼저 정했고 그 docstring 이
# 왜 그렇게 하는지를 길게 적어 놓았다. 여기서 그 함수를 **부르지 않고 다시 쓰는 이유는 하나**다:
# 문서 DB 와 작업 DB 는 서로 다른 Notion 통합(토큰)으로 붙는다. 티켓 토큰으로 문서 페이지의
# 블록을 지우려 하면 404 가 나고, 그때는 이미 정본을 저장한 뒤라 "저장됐는데 원본과 어긋남"
# 상태가 늘 켜진다. 토큰이 다르면 관문도 달라야 한다.
_MAX_REPLACE_BLOCKS = 200
_MAX_CHILDREN = 100
# 우리 편집기가 표현할 수 있는 블록 + 구분선. 이 집합 **밖의 블록은 지우지 않는다.**
_EDITABLE_BLOCK_TYPES = set(_TEXT_BLOCK_TYPES) | {"divider"}


def page_block_refs(
    outbound, settings, page_id: str, *, limit: int | None = None
) -> list[tuple[str, str]]:
    """(블록 id, 블록 타입) 목록.

    타입까지 읽는 이유는 아래 `replace_page_body` 가 **지워도 되는 블록만** 지우기 위해서다.
    id 만 모아 전부 지우면 저장 한 번에 원본의 이미지·표가 사라진다.
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


def replace_page_body(outbound, settings, *, page_id: str, blocks: list[dict]) -> None:
    """문서 본문의 **글 부분만** 교체한다. 이미지·표 같은 비텍스트 블록은 건드리지 않는다.

    ## 왜 통째로 교체하지 않나

    편집기에는 이미지·표가 실려 오지도 않는다(마크다운으로 표현할 수 없어 '원본에서 확인'
    자리표시로 바뀐다). 그 상태에서 1레벨 children 을 전부 지우면 **사용자가 본 적도 없는
    내용이 저장 한 번에 사라진다.** 문서는 계약서·설계서가 들어 있는 자리라 티켓보다 잃는
    것이 크다. 그리고 Notion 호스팅 파일은 API 로 재생성할 수 없어서(만료되는 서명 URL)
    지웠다 다시 만드는 길도 없다. **안 지우는 것이 유일한 방법이다.**

    남은 비텍스트 블록이 앞에 오고 새로 쓴 글이 뒤에 붙는다. 원본에서 이미지가 글 중간에
    있었다면 위치가 앞으로 모인다. 위치가 바뀌는 것과 내용이 사라지는 것 중 무엇이 나은지는
    물어볼 필요가 없다(화면 안내 문구도 이 동작에 맞춰 적었다).

    ## 실패 시

    순서를 삭제 → 추가로 두는 이유는 재시도 수렴이다: 중간에 실패해도 같은 본문으로 다시
    저장하면 원하는 상태가 된다. 반대로 하면 실패할 때마다 본문이 한 벌씩 늘어난다.
    실패해도 우리 DB 의 정본은 이미 저장된 뒤라 사용자 글은 살아 있다.

    원본이 아주 큰 페이지는 손대지 않고 거절한다 - 삭제가 블록당 한 번의 DELETE 라
    수백 개면 요청 하나가 수백 왕복이 된다.

    ## 삭제를 동시에 보내는 이유 (PF8)

    블록끼리는 서로 독립이라(삭제 순서가 결과에 영향 없다) 순서대로 기다릴 이유가 없다 -
    예전에는 블록 수만큼 Notion 왕복이 직렬로 쌓였다. 429 재시도(`rate_limit_retries`)는
    `_request` 안에서 호출 하나마다 자기 완결적으로 도니 여러 스레드가 동시에 재시도해도
    서로 침범하지 않는다. 하나라도 실패하면(어느 스레드든) 그대로 올려 새 본문은 붙이지
    않는다 - 위 "실패 시" 절의 재시도 수렴이 이 순서(전부 삭제 확인 → 추가)에 의존한다.
    """
    refs = page_block_refs(outbound, settings, page_id, limit=_MAX_REPLACE_BLOCKS)
    if len(refs) > _MAX_REPLACE_BLOCKS:
        raise ValidationAppError(
            f"원본 본문이 너무 커서(블록 {_MAX_REPLACE_BLOCKS}개 초과) 여기서 교체하지 "
            f"않았습니다. 원본에서 편집해 주세요."
        )
    # 편집기가 표현할 수 없는 블록은 사용자가 지운 적이 없다 - 그대로 둔다.
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
