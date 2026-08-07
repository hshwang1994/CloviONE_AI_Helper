"""Notion "프로젝트" 데이터베이스 조회 계층 (0045).

`app/reports/notion_source.py` 가 작업 DB 에 하는 일을 프로젝트 DB 에 한다: 원시 행을 읽어
파싱된 dict 로만 돌려주고, 앱 표로의 반영은 `app/projects/sync.py` 가 한다.

REST 호출과 오류 매핑은 **다시 적지 않는다** - `app/tickets/notion_write.notion_request`
하나를 지난다(토큰 파일 없음/401 → 미연동, 그 외 4xx/5xx → 조회 오류). 복사해 오면 두
동기화가 같은 실패를 다르게 번역하게 되고, 그때 증상은 "어떤 화면만 연동 안내가 안 뜬다" 다.

## 프로젝트 DB id 를 설정에 두지 않는 이유

작업 DB 의 `프로젝트` relation 이 가리키는 DB 를 그대로 쓴다(`discover_database_id`).
설정값으로 따로 받으면 오타 하나로 **다른 DB 를 미러링해도 아무 오류가 나지 않는다** -
`ticket_cache.project_ids` 에 들어 있는 relation id 와 `projects.notion_page_id` 가 서로 다른
DB 의 id 가 되어, 모든 프로젝트가 "걸린 작업 0건"(진행률 없음)으로 보이고 원인은 어디에도
안 적힌다. relation 을 따라가면 두 id 가 같은 DB 에서 왔다는 것이 구조적으로 보장된다.
"""

from __future__ import annotations

from app.tickets import notion_write

# 프로젝트 DB 속성 이름. Notion 속성명이 나타나는 곳은 이 모듈과 `notion_write.py` 뿐이어야
# 한다(저장소 seam 정적검사) - 서비스 계층은 도메인 이름만 쓴다.
#
# ⚠️ `진행 상태` 는 작업 DB 의 `진행상태`(공백 없음)와 **다른 이름**이다. 실제 두 DB 의 속성명이
# 그렇게 다르다. 한쪽 상수를 재사용하면 조회가 조용히 빈 값을 돌려준다(속성이 없으면 예외가
# 아니라 그냥 없는 것이다).
PROP_TITLE = "제목"
PROP_STATUS = "진행 상태"
PROP_PERIOD = "기간"
PROP_OWNER = "담당자(정)"
PROP_DEPUTY = "담당자(부)"
PROP_BIZ_TYPE = "사업 구분"
PROP_PRODUCT = "제품/품목"
PROP_TASKS = "작업"
# rollup / formula. **정본으로 쓰지 않는다**(아래 `_percent` 주석).
PROP_TICKET_PROGRESS = "티켓 진행률"
PROP_PROJECT_PROGRESS = "프로젝트 진행률"

# 도메인 필드 → 속성명 후보. 작업 DB 쪽 `EDIT_PROP_ALIASES` 와 같은 관용이다: Notion 에서
# 속성 이름을 바꿔도 후보 중 하나가 맞으면 계속 돈다. 이름 하나 바뀐 날 동기화가 통째로
# 멈추는 것보다, 맞는 후보로 계속 도는 편이 낫다.
PROP_ALIASES: dict[str, list[str]] = {
    # 이 워크스페이스의 실측 이름이 `프로젝트` 다. 다만 정본은 위 타입 탐색이다.
    "title": [PROP_TITLE, "프로젝트", "이름", "Name"],
    "status": [PROP_STATUS, "진행상태"],
    "period": [PROP_PERIOD],
    "owner": [PROP_OWNER, "담당자"],
    "biz_type": [PROP_BIZ_TYPE],
    "product": [PROP_PRODUCT],
}

_MAX_PAGES = 20  # 100건 x 20 = 2000건 상한. 작업 DB 와 같은 규약(무한 루프 방지).


def schema_prop(schema: dict, field: str) -> tuple[str | None, dict | None]:
    """도메인 필드 이름으로 프로젝트 DB 스키마 속성 (이름, 정의) 을 찾는다.

    🔴 **제목만은 이름이 아니라 타입으로 찾는다.**

    운영에서 프로젝트 목록이 통째로 `(제목 없음) 262c5c5a-...` 로 떴다. 이 워크스페이스의
    프로젝트 DB 는 제목 속성 이름이 **`프로젝트`** 인데 별칭표에는 `제목`·`이름`·`Name` 만
    있었다. 속성이 없으면 예외가 아니라 **그냥 없는 것**이라 조용히 빈 문자열이 됐고,
    폴백 문구가 UUID 를 그대로 화면에 뿌렸다.

    이름을 더 넣는 것으로는 같은 사고가 또 난다 - 고객마다 이름이 다르고 언제든 바뀐다.
    Notion DB 에는 **`type: "title"` 인 속성이 정확히 하나** 있고 그것이 곧 제목이다.
    그 구조를 쓰면 이름이 무엇이든 맞는다. 별칭은 그다음 폴백으로만 남긴다.
    """
    if field == "title":
        for name, prop in (schema or {}).items():
            if isinstance(prop, dict) and prop.get("type") == "title":
                return name, prop
    return notion_write.schema_prop(schema, PROP_ALIASES.get(field) or [])


def discover_database_id(tasks_schema: dict) -> str | None:
    """작업 DB 스키마에서 `프로젝트` relation 이 가리키는 DB id. 못 찾으면 None.

    None 은 "프로젝트 미러링을 할 수 없다" 는 뜻이라 호출측이 `SYNC_ERROR` 로 올린다 -
    조용히 0건 동기화로 끝내면 화면에는 '정상' 이라 적힌 채 프로젝트가 하나도 안 뜬다.
    """
    _, prop = notion_write.schema_prop_for(tasks_schema, "project")
    return notion_write.relation_target_db(prop) if prop else None


# ── 속성값 파서 ────────────────────────────────────────────────────────────────
# 작업 DB 쪽(`app/reports/notion_source.py`)과 같은 모양이다. 재사용하지 않고 다시 쓴 것은
# 저쪽 함수들이 전부 밑줄 붙은 내부 함수이기 때문이고, 여기서 필요한 것은 그중 절반이며
# **date range(끝 날짜)와 rollup/formula 는 저쪽에 아예 없다**.


def _title(prop: dict) -> str:
    parts = prop.get("title") or []
    return "".join(s.get("plain_text", "") for s in parts if isinstance(s, dict)).strip()


def _named(prop: dict, kind: str) -> str | None:
    container = prop.get(kind)
    return container.get("name") if isinstance(container, dict) else None


def _status_or_select(prop: dict) -> str | None:
    """진행 상태는 워크스페이스에 따라 status 이거나 select 다. 둘 다 받는다.

    한쪽만 읽으면 타입이 바뀐 날 모든 프로젝트의 상태가 조용히 NULL 이 된다 - 예외가 아니라
    '값이 없음' 으로 보이므로 아무도 알아채지 못한다.
    """
    return _named(prop, "status") or _named(prop, "select")


def _people_ids(prop: dict) -> list[str]:
    return [p.get("id") for p in (prop.get("people") or []) if isinstance(p, dict) and p.get("id")]


def _relation_ids(prop: dict) -> list[str]:
    return [r.get("id") for r in (prop.get("relation") or []) if isinstance(r, dict) and r.get("id")]


def _date_range(prop: dict) -> tuple[str | None, str | None]:
    """기간(date range) → (시작, 끝). 끝이 없는 하루짜리 일정이면 끝은 None 이다.

    끝을 시작으로 채우지 않는다. '언제 끝나는지 정하지 않았다' 와 '오늘 끝난다' 는 다른
    말이고, 마일스톤·헬스가 보는 것이 정확히 그 차이다.
    """
    date = prop.get("date")
    if not isinstance(date, dict):
        return None, None
    return date.get("start"), date.get("end")


def _percent(prop: dict) -> float | None:
    """rollup / formula 의 숫자를 0..100 퍼센트로. 값이 없으면 None.

    ## 왜 이 값을 정본으로 쓰지 않는가

    `티켓 진행률` 은 `percent_per_group / groupName="Complete"` 인데 작업 DB 의 status 그룹이
    `complete = [완료, 취소]` 라서 **취소한 티켓을 완료로 센다**. 10건 중 3건을 취소하면
    진행률이 그냥 +30% 다. `프로젝트 진행률` 은 formula 라 코드가 불투명해 검증조차 안 된다.
    (실측 근거는 `app/projects/progress.py` 모듈 docstring 에 셋 다 적어 뒀다.)

    그래도 읽어 두는 이유: 두 화면에 다른 숫자가 뜨는 것은 **정상 상태**이고, 그때 한쪽만
    보이면 사용자는 "포털이 틀렸다" 고 결론 내린다. 나란히 놓아야 둘 다 믿을 수 있다.

    ## 0..1 과 0..100 을 어떻게 가르나

    Notion 의 percent 계열 숫자는 0..1 비율로 온다(0.3 = 30%). 다만 formula 는 사람이 짠
    식이라 이미 100 을 곱해 놓았을 수 있다. **1 을 경계로 가른다**: 1 이하면 비율로 보고
    100 을 곱하고, 1 보다 크면 이미 퍼센트로 본다. 이 규칙이 틀리는 자리는 하나뿐이다 -
    formula 가 퍼센트 단위인데 값이 1%(=1.0) 인 경우. 그때는 100% 로 보인다.
    추정이므로 여기 적어 둔다. 이 값이 정본이 아닌 참고값이라 그 대가를 받아들인다.
    """
    kind = prop.get("type")
    holder = prop.get(kind) if kind in ("rollup", "formula") else None
    number = holder.get("number") if isinstance(holder, dict) else None
    if not isinstance(number, (int, float)) or isinstance(number, bool):
        return None
    percent = float(number) * 100.0 if number <= 1 else float(number)
    # 범위 밖 값은 잘라 낸다. 화면에 -12% 나 340% 가 뜨면 그 숫자 하나 때문에 옆에 있는
    # 앱 계산값까지 못 믿게 된다.
    return round(min(max(percent, 0.0), 100.0), 1)


def parse_row(row: dict) -> dict:
    """프로젝트 페이지 한 행 → 앱이 쓰는 dict.

    속성이 없으면 예외가 아니라 None/빈 값이다(Notion 에서 속성을 지우거나 이름을 바꾸면
    그렇게 온다). 그 사실 자체는 호출측이 '이름이 빈 프로젝트' 로 보고 판단한다.
    """
    props = row.get("properties") or {}

    def by_field(field: str) -> dict:
        name, _prop = schema_prop(props, field)
        value = props.get(name) if name else None
        return value if isinstance(value, dict) else {}

    def by_name(name: str) -> dict:
        value = props.get(name)
        return value if isinstance(value, dict) else {}

    start, end = _date_range(by_field("period"))
    # 프로젝트 진행률(formula)을 먼저 본다 - 팀이 실제로 보는 숫자가 그것이다. 없으면 재료가
    # 되는 rollup 으로 떨어진다.
    progress = _percent(by_name(PROP_PROJECT_PROGRESS))
    if progress is None:
        progress = _percent(by_name(PROP_TICKET_PROGRESS))

    return {
        "id": row.get("id"),
        "url": row.get("url"),
        "title": _title(by_field("title")),
        "status": _status_or_select(by_field("status")),
        "start": start,
        "end": end,
        "owner_ids": _people_ids(by_field("owner")),
        "deputy_ids": _people_ids(by_name(PROP_DEPUTY)),
        "biz_type": _named(by_field("biz_type"), "select"),
        "product": _named(by_field("product"), "select"),
        "task_ids": _relation_ids(by_name(PROP_TASKS)),
        "notion_progress_pct": progress,
        "created_time": row.get("created_time"),
        "last_edited": row.get("last_edited_time"),
    }


def query_all_projects_paged(outbound, settings, database_id: str) -> tuple[list[dict], bool]:
    """프로젝트 DB 전체를 읽어 (파싱된 목록, truncated) 를 돌려준다.

    `truncated=True` 는 상한(_MAX_PAGES)에 걸려 '더 있는데 못 받아온' 상태다. 이 신호 없이
    prune 을 돌리면 못 받아온 프로젝트를 'Notion 에서 삭제됨' 으로 오인해 표시해 버린다
    (작업 DB 쪽 `query_all_tasks_paged` 와 같은 규약이며, 호출측은 truncated 면 prune 을
    건너뛴다).
    """
    path = f"/v1/databases/{database_id}/query"
    rows: list[dict] = []
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = notion_write.notion_request(outbound, settings, "POST", path, json=body)
        for row in data.get("results", []):
            if isinstance(row, dict):
                rows.append(parse_row(row))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    else:
        # break 없이 상한을 소진 = 마지막 페이지에도 has_more 가 남아 있었다.
        return rows, True
    return rows, False
