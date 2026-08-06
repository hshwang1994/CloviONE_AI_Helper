"""Notion 을 **실제로 한 번 부르는** 자리 (9-4 연결 테스트 / DB 생성).

## 왜 별도 파일이고 왜 이 이름인가

이 저장소는 Notion 구현 세부(엔드포인트, 속성 이름, 오류 코드)를 저장소 seam 뒤에 가둔다 -
`scripts/static_checks.sh` 의 "Notion 모듈 import 경계" 검사가 그 규칙을 지킨다. 파일 이름이
`*_notion.py` 인 것이 그 검사가 인정하는 구현체 표시다. 그래서 콘솔의 판정
(`service.py`)과 라우터는 이 파일 뒤에 서고, 여기만 Notion 을 안다.

## 왜 이유를 구분해서 돌려주는가

"연결 실패" 한 마디는 아무것도 알려 주지 않는다. 운영자가 실제로 하는 세 가지 행동이 전부
다르기 때문이다.

  * **토큰이 무효다** -> Notion 통합 설정에서 새 토큰을 발급해 서버에 놓는다.
  * **데이터베이스를 못 찾는다** -> id 가 틀렸거나, 그 페이지를 통합에 **공유하지 않았다**.
    Notion 은 두 경우를 **똑같이 404 `object_not_found`** 로 답한다. 우리가 그것을 구분해
    말할 방법은 없다 - 그래서 둘 다 적어 준다. 아는 척하지 않는다.
  * **권한이 없다**(403 `restricted_resource`) -> 통합의 권한(읽기/쓰기)을 올린다.

그래서 토큰 자체를 먼저 확인한다(`GET /v1/users/me`). 이 호출이 401 이면 데이터베이스
결과가 무엇이든 원인은 토큰이다. 이 순서가 없으면 만료된 토큰이 전부 "데이터베이스 없음"
으로 보이고, 운영자는 멀쩡한 id 를 몇 번씩 다시 붙여 넣는다.

## 정직한 한계

이 판정은 **한 순간의 사실**이다. 여기서 성공했다고 다음 동기화가 성공한다는 뜻은 아니다
(429, 네트워크, 권한 회수). 화면은 '지금 눌러서 이렇게 나왔다' 로만 말해야 한다.
"""

from __future__ import annotations

import logging

from app.reports.notion_source import (
    PROP_ACT,
    PROP_CATEGORY,
    PROP_DIFFICULTY,
    PROP_DUE,
    PROP_EST,
    PROP_PARENT,
    PROP_PEOPLE,
    PROP_PRIORITY,
    PROP_START,
    PROP_STATUS,
    PROP_TICKET_ID,
    PROP_TITLE,
)

logger = logging.getLogger("app.notion_console")

# 결과 어휘. 화면과 테스트가 **이 문자열**을 본다.
RESULT_OK = "ok"
RESULT_UNSET = "unset"
RESULT_TOKEN_MISSING = "token_missing"
RESULT_TOKEN_INVALID = "token_invalid"
RESULT_NOT_FOUND = "database_not_found"
RESULT_NO_PERMISSION = "no_permission"
RESULT_INVALID_ID = "invalid_id"
RESULT_RATE_LIMITED = "rate_limited"
RESULT_UNREACHABLE = "unreachable"
RESULT_FAILED = "failed"

# 결과 -> 화면에 그대로 실을 수 있는 한 줄. **우리가 쓴 문장만 나간다** -
# Notion 이 준 영어 message 를 그대로 옮기지 않는다(app/llm/provider.py 와 같은 규칙:
# 내부 식별자가 섞여 나올 수 있고, 한국어 화면에 영어가 새고, 읽어도 무엇을 해야 할지
# 알려 주지 않는다).
RESULT_MESSAGES: dict[str, str] = {
    RESULT_OK: "연결에 성공했습니다.",
    RESULT_UNSET: "아직 설정하지 않았습니다.",
    RESULT_TOKEN_MISSING: "서버에 토큰 파일이 없습니다.",
    RESULT_TOKEN_INVALID: "토큰이 유효하지 않습니다. 노션 통합에서 토큰을 다시 발급하세요.",
    RESULT_NOT_FOUND: (
        "데이터베이스를 찾지 못했습니다. id 가 틀렸거나, 그 데이터베이스를 통합에 "
        "공유하지 않았습니다. 노션에서 해당 페이지의 연결 메뉴로 통합을 추가해 주세요."
    ),
    RESULT_NO_PERMISSION: (
        "토큰은 유효하지만 이 데이터베이스에 접근할 권한이 없습니다. 노션 통합의 권한을 "
        "확인하세요."
    ),
    RESULT_INVALID_ID: "데이터베이스 id 의 모양이 올바르지 않습니다.",
    RESULT_RATE_LIMITED: "노션이 요청을 제한하고 있습니다. 잠시 뒤 다시 시도해 주세요.",
    RESULT_UNREACHABLE: "노션에 연결하지 못했습니다. 서버의 네트워크와 방화벽을 확인하세요.",
    RESULT_FAILED: "노션이 예상하지 못한 응답을 돌려줬습니다.",
}

# Notion 오류 코드 -> 우리 어휘. 목록에 없는 코드는 상태 코드로 판정한다.
_CODE_MAP = {
    "unauthorized": RESULT_TOKEN_INVALID,
    "restricted_resource": RESULT_NO_PERMISSION,
    "object_not_found": RESULT_NOT_FOUND,
    "validation_error": RESULT_INVALID_ID,
    "rate_limited": RESULT_RATE_LIMITED,
}

_TIMEOUT_SECONDS = 15.0


def message_for(result: str) -> str:
    return RESULT_MESSAGES.get(result, RESULT_MESSAGES[RESULT_FAILED])


def _headers(settings) -> dict[str, str]:
    return {
        "Notion-Version": settings.notion_api_version,
        "Content-Type": "application/json",
    }


def _url(settings, path: str) -> str:
    return f"{settings.notion_api_base.rstrip('/')}{path}"


def _classify(response) -> str:
    """HTTP 응답 하나 -> 우리 어휘 하나."""
    status = getattr(response, "status_code", 0)
    if 200 <= status < 300:
        return RESULT_OK
    code = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            code = str(body.get("code") or "")
    except Exception:  # noqa: BLE001 - 본문이 JSON 이 아니어도 상태 코드로 판정한다
        code = ""
    mapped = _CODE_MAP.get(code)
    if mapped:
        return mapped
    if status == 401:
        return RESULT_TOKEN_INVALID
    if status == 403:
        return RESULT_NO_PERMISSION
    if status == 404:
        return RESULT_NOT_FOUND
    if status == 429:
        return RESULT_RATE_LIMITED
    if status == 400:
        return RESULT_INVALID_ID
    return RESULT_FAILED


def _call(outbound, settings, method: str, path: str, *, token_ref: str, json=None):
    """한 번 부르고 (결과어휘, 응답) 을 돌려준다. **예외를 밖으로 던지지 않는다.**

    화면이 여는 진단이라 어떤 실패도 500 이 되면 안 된다 - 500 은 '일시적 오류' 로 읽히고,
    운영자는 원인을 못 본 채 재시도만 반복한다.
    """
    try:
        response = outbound.request(
            method,
            _url(settings, path),
            allowlist="services",
            json=json,
            headers=_headers(settings),
            timeout=_TIMEOUT_SECONDS,
            auth_type="bearer",
            secret_ref=token_ref,
        )
    except FileNotFoundError:
        return RESULT_TOKEN_MISSING, None
    except Exception as exc:  # noqa: BLE001 - 네트워크/전송 오류 전부
        if token_ref and token_ref in str(exc):
            return RESULT_TOKEN_MISSING, None
        # 원문은 서버 로그에만. 주소나 secret 이름이 섞여 있을 수 있다.
        logger.warning("노션 호출 실패 %s %s: %s", method, path, type(exc).__name__)
        return RESULT_UNREACHABLE, None
    return _classify(response), response


def check_token(outbound, settings, *, token_ref: str) -> dict:
    """토큰 하나가 지금 통하는가. `GET /v1/users/me` 로 확인한다.

    이 호출은 **데이터베이스와 무관**해서, 결과가 곧 "토큰 자체의 상태" 다. 그래서 DB 조회
    결과와 겹쳐 보면 원인이 토큰인지 공유인지 갈린다.
    """
    result, response = _call(outbound, settings, "GET", "/v1/users/me", token_ref=token_ref)
    view = {"ref": token_ref, "result": result, "message": message_for(result)}
    if result == RESULT_OK and response is not None:
        # 통합 이름은 **비밀이 아니다**(워크스페이스 관리자가 붙인 이름). 이걸 보여 줘야
        # 운영자가 "지금 어느 통합의 토큰이 꽂혀 있는지" 를 확인할 수 있다.
        try:
            body = response.json()
            name = body.get("name") if isinstance(body, dict) else None
            if isinstance(name, str) and name.strip():
                view["integration_name"] = name.strip()[:100]
        except Exception:  # noqa: BLE001 - 이름을 못 읽어도 판정은 이미 끝났다
            pass
    return view


def check_database(outbound, settings, *, database_id: str, token_ref: str) -> dict:
    """데이터베이스 하나에 지금 닿는가. 비어 있으면 부르지 않는다."""
    if not (database_id or "").strip():
        return {"result": RESULT_UNSET, "message": message_for(RESULT_UNSET)}
    result, response = _call(
        outbound, settings, "GET", f"/v1/databases/{database_id.strip()}", token_ref=token_ref
    )
    view = {"result": result, "message": message_for(result)}
    if result == RESULT_OK and response is not None:
        try:
            body = response.json()
            if isinstance(body, dict):
                title = "".join(
                    seg.get("plain_text", "")
                    for seg in (body.get("title") or [])
                    if isinstance(seg, dict)
                ).strip()
                if title:
                    view["title"] = title[:200]
                props = body.get("properties")
                if isinstance(props, dict):
                    view["property_count"] = len(props)
        except Exception:  # noqa: BLE001 - 제목을 못 읽어도 판정은 이미 끝났다
            pass
    return view


# ── 빈 워크스페이스에 데이터베이스 만들기 ────────────────────────────────────
#
# 속성 이름은 **읽는 쪽에서 가져온다**(app/reports/notion_source.py 의 PROP_*). 여기에 다시
# 적으면 이름이 갈라지는 날 새로 만든 DB 만 조용히 안 읽힌다 - 그리고 그 사실은 며칠 뒤
# "티켓이 안 보인다" 로 나타난다.
TASKS_SCHEMA: dict[str, dict] = {
    PROP_TITLE: {"title": {}},
    PROP_STATUS: {
        "status": {}
    },
    PROP_PRIORITY: {
        "select": {"options": [{"name": "높음"}, {"name": "보통"}, {"name": "낮음"}]}
    },
    PROP_DIFFICULTY: {
        "select": {"options": [{"name": "1"}, {"name": "3"}, {"name": "5"}]}
    },
    PROP_DUE: {"date": {}},
    PROP_START: {"date": {}},
    PROP_CATEGORY: {"rich_text": {}},
    PROP_EST: {"number": {"format": "number"}},
    PROP_ACT: {"number": {"format": "number"}},
    PROP_PEOPLE: {"people": {}},
    PROP_TICKET_ID: {"unique_id": {"prefix": "T"}},
}

# 문서 DB 는 제목만 강제한다. 나머지 속성은 팀마다 다르고, 우리가 읽는 것은 제목과 본문이다.
DOCUMENTS_SCHEMA: dict[str, dict] = {
    PROP_TITLE: {"title": {}},
}

# 상위 작업(self relation)은 DB 를 만든 **뒤에** 자기 자신을 가리키게 붙여야 한다.
# 생성 요청 안에서는 아직 그 id 가 없기 때문이다. 못 붙이면 WBS 트리가 비는데, 그것은
# 데이터가 없는 것과 구별되지 않는다 - 그래서 실패를 결과에 담아 화면이 말하게 한다.
PARENT_RELATION_PROP = PROP_PARENT

SCHEMAS = {"tasks": TASKS_SCHEMA, "documents": DOCUMENTS_SCHEMA}


def create_database(
    outbound, settings, *, parent_page_id: str, title: str, kind: str, token_ref: str
) -> dict:
    """빈 워크스페이스에 데이터베이스 하나를 만든다.

    **되돌리기 어려운 동작이다.** 여기서는 확인 절차를 다루지 않는다 - 부르는 쪽
    (`service.py`)이 '이미 있으면 안 만든다' 와 '확인을 받았는가' 를 먼저 본다.
    """
    schema = SCHEMAS.get(kind)
    if schema is None:
        return {"result": RESULT_FAILED, "message": message_for(RESULT_FAILED)}
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": schema,
    }
    result, response = _call(
        outbound, settings, "POST", "/v1/databases", token_ref=token_ref, json=payload
    )
    view: dict = {"result": result, "message": message_for(result)}
    if result != RESULT_OK or response is None:
        return view
    try:
        body = response.json()
        database_id = body.get("id") if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001
        database_id = None
    if not isinstance(database_id, str) or not database_id:
        # 만들어졌는데 id 를 못 읽었다. 성공이라고 말하면 운영자는 설정이 끝났다고 믿는다.
        return {"result": RESULT_FAILED, "message": message_for(RESULT_FAILED)}
    view["database_id"] = database_id
    if kind == "tasks":
        view["parent_relation"] = _attach_self_relation(
            outbound, settings, database_id=database_id, token_ref=token_ref
        )
    return view


def _attach_self_relation(outbound, settings, *, database_id: str, token_ref: str) -> str:
    """'상위 작업' self-relation 을 붙인다. 결과 어휘 하나를 돌려준다."""
    result, _response = _call(
        outbound,
        settings,
        "PATCH",
        f"/v1/databases/{database_id}",
        token_ref=token_ref,
        json={
            "properties": {
                PARENT_RELATION_PROP: {
                    "relation": {"database_id": database_id, "single_property": {}}
                }
            }
        },
    )
    return result


__all__ = [
    "RESULT_OK",
    "RESULT_UNSET",
    "RESULT_TOKEN_MISSING",
    "RESULT_TOKEN_INVALID",
    "RESULT_NOT_FOUND",
    "RESULT_NO_PERMISSION",
    "RESULT_INVALID_ID",
    "RESULT_RATE_LIMITED",
    "RESULT_UNREACHABLE",
    "RESULT_FAILED",
    "RESULT_MESSAGES",
    "check_database",
    "check_token",
    "create_database",
    "message_for",
]
