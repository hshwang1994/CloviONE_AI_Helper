"""Notion "프로젝트" 데이터베이스 쓰기 계층 (0045, 포털 → Notion push).

작업 DB 쪽(`app/tickets/notion_write.py`)과 **같은 관용**이다: 스키마를 먼저 읽어 실제 속성
타입에 맞는 페이로드를 만들고, PATCH 한 뒤 반영된 페이지를 파싱해 돌려준다. REST 호출과
오류 매핑은 저쪽 `notion_request` 하나를 지난다(번역이 두 벌이 되지 않게).

## 스키마를 왜 매번 읽는가

값을 그냥 보내면 Notion 이 400 으로 거절하고, 우리는 그것을 502(NotionQueryError)로 올린다.
화면에는 "Notion 응답 오류" 가 뜨는데 원인은 사용자가 고른 상태값 하나다 - 아무도 자기
입력을 의심하지 않는다. 스키마를 보면 그 판정을 우리가 하고 이유를 우리 말로 답할 수 있다.

## 여기서 Notion 에 **새 속성을 만들지 않는다**

부서·코드·마일스톤·헬스·주간 리포트는 앱에만 둔다(사용자 결정). Notion 에 속성을 늘릴수록
팀이 쓰는 뷰·필터·수식이 깨질 위험이 커진다. 이 모듈은 **이미 있는 속성만** 고친다.
"""

from __future__ import annotations

from app.core.errors import AppError, ValidationAppError
from app.projects import notion_source
from app.tickets import notion_write


class ProjectPageNotFoundError(AppError):
    """대상 프로젝트(Notion 페이지)가 없거나 접근할 수 없다.

    작업 DB 쪽 `TicketNotFoundError` 와 문구를 나누는 이유: 프로젝트 페이지가 사라졌는데
    "티켓을 찾을 수 없습니다" 라고 답하면 사용자는 자기가 안 건드린 화면을 뒤진다.
    """

    status_code = 404
    code = "project_page_not_found"
    default_message = "Notion 에서 이 프로젝트 페이지를 찾을 수 없습니다."


def fetch_schema(outbound, settings, database_id: str) -> dict:
    """프로젝트 DB 스키마의 properties. 작업 DB 와 **같은 함수**를 쓴다."""
    return notion_write.fetch_schema(outbound, settings, database_id)


def _date_range_value(start: str | None, end: str | None):
    """기간(date range) 쓰기 페이로드.

    `tickets.notion_write.property_value` 의 date 분기를 못 쓴다 - 저기는 마감일처럼 **하루**
    를 다루느라 `start` 만 만든다. 그대로 쓰면 프로젝트를 저장할 때마다 종료일이 조용히
    지워진다(있던 값이 사라지는 부류라 되돌릴 수도 없다).

    시작이 비면 기간 자체를 지운다. Notion 은 `{"start": ""}` 를 400 으로 거절하므로 빈 값의
    뜻을 여기서 정해 준다(작업 DB date 규약과 같다).
    """
    if not (start or "").strip():
        return {"date": None}
    payload: dict = {"start": start}
    if (end or "").strip():
        payload["end"] = end
    return {"date": payload}


def _status_value(prop: dict, value: str | None):
    """진행 상태 쓰기 페이로드. 스키마에 없는 옵션이면 **여기서** 거절한다.

    허용 옵션 목록을 앱에 하드코딩하지 않는 이유: Notion 이 정본이라 옵션을 하나 늘린 날
    포털이 정상 값을 거절하게 된다. 매번 스키마에서 읽으면 그런 표류가 생길 자리가 없다.
    """
    if value is None or not str(value).strip():
        # 빈 값은 '상태 지움'. status 타입은 None 을 허용하지 않는 워크스페이스가 있어
        # 아예 보내지 않는 편이 안전하다(호출측이 None 을 걸러 낸다).
        return None
    allowed = notion_write.option_names(prop)
    if allowed and value not in allowed:
        raise ValidationAppError(
            f"Notion 에 없는 진행 상태입니다: {value} (가능한 값: {', '.join(allowed)})"
        )
    return notion_write.property_value(prop, value)


def build_properties(
    schema: dict,
    *,
    title: str | None = None,
    status: str | None = None,
    start: str | None = None,
    end: str | None = None,
    owner_notion_ids: list[str] | None = None,
) -> dict:
    """스키마에 실제로 있는 속성만 골라 PATCH 페이로드를 만든다.

    스키마에 없는 속성은 **조용히 건너뛴다**(예외가 아니다). 팀이 Notion 에서 속성 하나를
    지우거나 이름을 바꿨다고 포털의 저장이 통째로 막히면, 사용자는 자기가 고칠 수 없는
    이유로 일을 못 하게 된다. 반대로 **아무 속성도 안 남으면** 호출측이 그 빈 dict 를 보고
    push 를 건너뛴다 - 빈 PATCH 를 보내면 Notion 이 400 을 주고, 그 502 는 원인을 안 말한다.

    `None` 인 인자는 '안 건드림' 이다. 빈 문자열은 '지움' 이고, 그 구별이 없으면 이름만 고친
    저장 한 번이 기간과 담당자를 통째로 지운다.
    """
    props: dict = {}

    if title is not None:
        name, prop = notion_source.schema_prop(schema, "title")
        if prop is not None:
            props[name] = notion_write.property_value(prop, title)

    if status is not None:
        name, prop = notion_source.schema_prop(schema, "status")
        if prop is not None:
            payload = _status_value(prop, status)
            if payload is not None:
                props[name] = payload

    if start is not None or end is not None:
        name, prop = notion_source.schema_prop(schema, "period")
        if prop is not None:
            props[name] = _date_range_value(start, end)

    if owner_notion_ids is not None:
        name, prop = notion_source.schema_prop(schema, "owner")
        if prop is not None:
            props[name] = notion_write.property_value(prop, list(owner_notion_ids))

    return props


def update_project_properties(outbound, settings, *, page_id: str, properties: dict) -> dict:
    """페이지 속성을 PATCH 하고, 반영된 페이지를 파싱해 돌려준다.

    작업 DB 쪽 `update_ticket_properties` 와 같은 모양이되 파싱만 프로젝트 것을 쓴다 -
    돌아온 값을 그대로 미러에 반영할 수 있어야 다음 동기화까지 화면이 낡은 값을 보여주지 않는다.
    """
    data = notion_write.notion_request(
        outbound, settings, "PATCH", f"/v1/pages/{page_id}",
        json={"properties": properties},
        not_found=ProjectPageNotFoundError,
    )
    return notion_source.parse_row(data)
