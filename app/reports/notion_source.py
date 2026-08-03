"""Notion "작업" 데이터베이스 조회 계층 (개발자 월간 리포트).

앱 서버가 Notion REST API를 직접 부르는 유일한 곳이다. 다른 모든 외부 호출과 똑같이
OutboundClient 단일 관문을 지나며(SSRF allowlist=services, redirect 미추적, secret 주입),
토큰은 secrets_dir 파일 참조로만 읽는다. 이 모듈은 원시 티켓 목록만 돌려주고, 이름 해석과
집계는 service.py가 담당한다(관심사 분리).
"""

from __future__ import annotations

from app.core.errors import AppError

# 마감일 필터에 쓰는 Notion 속성 이름과, 우리가 읽는 속성들. Notion 스키마와 정확히 일치해야 한다.
PROP_DUE = "마감일"
PROP_TITLE = "제목"
PROP_STATUS = "진행상태"
PROP_PEOPLE = "티켓 담당자"
PROP_EST = "예상 WD"
PROP_ACT = "실제 WD"
PROP_DIFFICULTY = "난이도"
PROP_PRIORITY = "우선순위"
PROP_TICKET_ID = "티켓 ID"
PROP_PROJECT = "프로젝트"

_MAX_PAGES = 20  # 100건 x 20 = 2000건 상한. 무한 루프 방지(정상 데이터는 한두 페이지).


class NotionNotConfiguredError(AppError):
    """Notion 연동 토큰이 아직 서버에 없다(사용자가 provisioning 하기 전)."""

    status_code = 503
    code = "notion_not_configured"
    default_message = "Notion 연동 토큰이 설정되지 않았습니다."


class NotionQueryError(AppError):
    status_code = 502
    code = "notion_query_failed"
    default_message = "Notion 조회에 실패했습니다."


def _plain_title(prop: dict) -> str:
    parts = prop.get("title") or []
    return "".join(seg.get("plain_text", "") for seg in parts if isinstance(seg, dict)).strip()


def _people_ids(prop: dict) -> list[str]:
    return [p.get("id") for p in (prop.get("people") or []) if isinstance(p, dict) and p.get("id")]


def _relation_ids(prop: dict) -> list[str]:
    return [r.get("id") for r in (prop.get("relation") or []) if isinstance(r, dict) and r.get("id")]


def _select_name(prop: dict) -> str | None:
    sel = prop.get("select")
    return sel.get("name") if isinstance(sel, dict) else None


def _status_name(prop: dict) -> str | None:
    st = prop.get("status")
    return st.get("name") if isinstance(st, dict) else None


def _date_start(prop: dict) -> str | None:
    d = prop.get("date")
    return d.get("start") if isinstance(d, dict) else None


def _number(prop: dict):
    return prop.get("number")


def _ticket_number(prop: dict):
    # auto_increment_id 는 REST에서 unique_id {prefix, number} 로 온다.
    uid = prop.get("unique_id")
    if isinstance(uid, dict):
        return uid.get("number")
    return None


def _parse_row(row: dict) -> dict:
    props = row.get("properties") or {}

    def p(name: str) -> dict:
        v = props.get(name)
        return v if isinstance(v, dict) else {}

    return {
        "id": row.get("id"),
        "url": row.get("url"),
        "tid": _ticket_number(p(PROP_TICKET_ID)),
        "title": _plain_title(p(PROP_TITLE)),
        "status": _status_name(p(PROP_STATUS)),
        "due": _date_start(p(PROP_DUE)),
        "start": None,  # 시작일은 리포트에 쓰지 않는다(공수 아님) — 필요 시 확장.
        "assignees": _people_ids(p(PROP_PEOPLE)),
        "est_wd": _number(p(PROP_EST)),
        "act_wd": _number(p(PROP_ACT)),
        "difficulty": _select_name(p(PROP_DIFFICULTY)),
        "priority": _select_name(p(PROP_PRIORITY)),
        "project_ids": _relation_ids(p(PROP_PROJECT)),
    }


def _parse_row_with_times(row: dict) -> dict:
    """_parse_row + Notion 원본 타임스탬프. 미러 동기화 전용이다.

    _parse_row 자체에 넣지 않는 이유: 목록 응답(_enrich)이 파싱 결과를 그대로 펼쳐 내보내므로
    키를 하나 더하면 프런트 계약(골든)이 움직인다. 캐시에만 필요한 값은 여기서 더한다.
    """
    return {
        **_parse_row(row),
        "created_time": row.get("created_time"),
        "last_edited": row.get("last_edited_time"),
    }


def _query_tasks_paged(
    outbound, settings, *, filter_obj=None, sorts=None, parse=_parse_row
) -> tuple[list[dict], bool]:
    """작업 DB를 filter/sorts 로 조회해 (파싱된 dict 목록, truncated) 를 돌려준다.

    truncated=True 는 상한(_MAX_PAGES = 2000건)에 걸려 '더 있는데 못 받아온' 상태다. 이 신호
    없이 미러 동기화를 돌리면 2000건만 받아 놓고 나머지를 'Notion에서 삭제됨'으로 오인해
    캐시에서 지워 버린다(= 티켓이 앱 전체에서 사라진다). 문서 쪽
    notion_docs.query_all_documents 와 같은 규약이며, 호출측은 truncated 면 prune 을 건너뛴다.

    페이지네이션·토큰 미설정/오류 매핑을 한곳에서 처리한다. 토큰이 없으면
    NotionNotConfiguredError, Notion 오류면 NotionQueryError.
    """
    url = f"{settings.notion_api_base.rstrip('/')}/v1/databases/{settings.notion_tasks_database_id}/query"
    headers = {
        "Notion-Version": settings.notion_api_version,
        "Content-Type": "application/json",
    }
    rows: list[dict] = []
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        body: dict = {"page_size": 100}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        if cursor:
            body["start_cursor"] = cursor
        try:
            resp = outbound.post(
                url,
                allowlist="services",
                json=body,
                headers=headers,
                timeout=30.0,
                auth_type="bearer",
                secret_ref=settings.notion_report_token_ref,
            )
        except FileNotFoundError as exc:
            # secrets_dir 에 토큰 파일이 없음 = 아직 연동 안 됨.
            raise NotionNotConfiguredError() from exc
        except Exception as exc:  # 네트워크/전송 오류
            # secret provider 가 '없음'을 어떤 예외로 던지든 토큰 미설정으로 취급할 수 있게,
            # 메시지에 secret 이름이 있으면 not-configured 로 매핑한다.
            if settings.notion_report_token_ref in str(exc):
                raise NotionNotConfiguredError() from exc
            raise NotionQueryError(f"Notion 조회 실패: {type(exc).__name__}") from exc

        if resp.status_code == 401:
            raise NotionNotConfiguredError("Notion 토큰이 유효하지 않습니다(401).")
        if resp.status_code >= 400:
            raise NotionQueryError(f"Notion 응답 오류: HTTP {resp.status_code}")

        data = resp.json()
        for row in data.get("results", []):
            if isinstance(row, dict):
                rows.append(parse(row))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    else:
        # for 루프가 break 없이 _MAX_PAGES를 소진 = 마지막 페이지에도 has_more가 남아 있었다.
        return rows, True
    return rows, False


def _query_tasks(outbound, settings, *, filter_obj=None, sorts=None) -> list[dict]:
    """_query_tasks_paged 의 행 목록만 쓰는 얇은 래퍼.

    기존 query_* 함수들의 시그니처(리스트 반환)를 그대로 유지하려고 남긴다 — 프런트가 의존하는
    응답 계약(골든)이 이 경로로 나오므로 모양을 바꾸지 않는다. truncated 가 필요한 곳(미러
    동기화)만 _query_tasks_paged 를 직접 쓴다.
    """
    rows, _truncated = _query_tasks_paged(
        outbound, settings, filter_obj=filter_obj, sorts=sorts
    )
    return rows


def query_tasks_for_period(outbound, settings, *, start_date: str, end_date: str) -> list[dict]:
    """마감일이 [start_date, end_date) 인 티켓을 모두 읽어 파싱된 dict 목록으로 돌려준다.

    start_date/end_date 는 'YYYY-MM-DD' ISO 날짜. end_date 는 배타적(다음 달 1일).
    """
    return _query_tasks(outbound, settings, filter_obj={
        "and": [
            {"property": PROP_DUE, "date": {"on_or_after": start_date}},
            {"property": PROP_DUE, "date": {"before": end_date}},
        ]
    })


_DUE_ASC = [{"property": PROP_DUE, "direction": "ascending"}]


def query_tasks_by_assignee(outbound, settings, *, notion_user_id: str) -> list[dict]:
    """티켓 담당자에 notion_user_id 가 포함된 티켓 전부(마감일 무관, 마감 오름차순).

    '내 티켓' 셀프서비스 화면용. notion_user_id 는 반드시 세션 사용자에서만 도출한다(브라우저 미입력).
    """
    return _query_tasks(
        outbound, settings,
        filter_obj={"property": PROP_PEOPLE, "people": {"contains": notion_user_id}},
        sorts=_DUE_ASC,
    )


def query_all_tasks(outbound, settings) -> list[dict]:
    """작업 DB의 모든 티켓(마감 오름차순). 팀 티켓 보기 화면용 — 상태 필터는 호출측 책임."""
    return _query_tasks(outbound, settings, sorts=_DUE_ASC)


def query_all_tasks_paged(outbound, settings) -> tuple[list[dict], bool]:
    """query_all_tasks 와 같은 조회에 truncated 신호를 함께 돌려준다(미러 동기화 전용).

    동기화는 '못 받아온 것'과 '삭제된 것'을 구분해야 한다 — 구분 못 하면 상한을 넘긴 순간
    캐시를 통째로 비운다. 목록 API는 계속 query_all_tasks 를 쓴다(응답 계약 불변).
    """
    return _query_tasks_paged(outbound, settings, sorts=_DUE_ASC, parse=_parse_row_with_times)


def query_unassigned_tasks(outbound, settings) -> list[dict]:
    """담당자(사람)가 없는 티켓 전부(마감 오름차순). 완료/취소 제외 같은 상태 필터는 호출측 책임."""
    return _query_tasks(
        outbound, settings,
        filter_obj={"property": PROP_PEOPLE, "people": {"is_empty": True}},
        sorts=_DUE_ASC,
    )
