"""Notion 관리 화면의 판정 (9-4). Notion 을 직접 알지 않는다.

## 이 화면이 생긴 이유

고객사에 설치한 뒤 Notion 토큰을 바꾸려면 **SSH 로 들어가 파일을 고치고 재시작**해야 했다.
셋업 마법사는 "데이터베이스 id 와 토큰을 넣으세요" 라고 말하는데 넣을 화면이 없었고,
`SetupWizard.jsx` 는 그 사실을 주석으로 적어 두고 진단 화면으로 보내고 있었다.

## 무엇을 어디서 바꾸는가

  * **데이터베이스 id** 는 설정 레지스트리를 지난다(`app/settings/registry.py`). 검증,
    감사, 버전 이력, 되돌리기가 이미 거기 붙어 있다. 여기에 두 번째 쓰기 경로를 내지 않는다.
  * **토큰**은 설정에 넣지 않는다. 시크릿 파일 참조다(`app/core/secret_refs.py`). DB 에
    평문으로 넣으면 감사 로그, 설정 스냅샷, 버전 이력 세 곳에 토큰이 남는다 - 그 셋은
    전부 되돌려 읽을 수 있는 자리다.

## 토큰을 다시 보여 주지 않는다

이 화면은 토큰을 **읽어 보여 주지 않는다.** 설정됨/안 됨과, 그 토큰이 지금 통하는지만
말한다. "확인용으로 앞 네 글자만" 같은 타협도 하지 않는다 - 접두사는 어느 워크스페이스의
어느 통합인지를 좁혀 주고, 그건 유출의 시작이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import ConflictError, ValidationAppError
from app.core.secret_refs import STATUS_CONFIGURED
from app.notion_console import probe_notion as probe

# 감사 대상 이름. 한국어 라벨은 app/profiles/activity.py::OBJECT_LABELS 에 있다.
OBJECT_TYPE_TOKEN = "notion_token"
OBJECT_TYPE_DATABASE = "notion_database"

# 화면이 다루는 데이터베이스 셋. 설정 키와 토큰 참조가 서로 다르므로 표 하나로 묶는다 -
# 두 벌로 두면 한쪽만 늘어나고, 그러면 새 데이터베이스가 진단에서 조용히 빠진다.
#
# `creatable` 이 False 인 것(스프린트)은 **일부러다**. 포털은 스프린트 DB 를 읽지 않으므로
# 우리가 만들어 주면 아무도 안 쓰는 빈 데이터베이스가 남는다.


@dataclass(frozen=True)
class DatabaseSpec:
    key: str            # 설정 레지스트리 키 = Settings 필드 이름
    label: str
    token_ref_field: str  # Settings 의 토큰 참조 필드 이름
    kind: str           # probe_notion.SCHEMAS 의 키("" 면 생성 불가)
    used_for: str
    when_unset: str


DATABASES: tuple[DatabaseSpec, ...] = (
    DatabaseSpec(
        key="notion_tasks_database_id",
        label="작업 데이터베이스",
        token_ref_field="notion_report_token_ref",
        kind="tasks",
        used_for="티켓 목록, 스프린트, 개발자 리포트가 이 데이터베이스를 읽습니다.",
        when_unset="티켓 목록과 리포트가 비어 있게 됩니다.",
    ),
    DatabaseSpec(
        key="notion_documents_database_id",
        label="문서 데이터베이스",
        token_ref_field="notion_docs_token_ref",
        kind="documents",
        used_for="팀 공간의 문서 목록이 이 데이터베이스를 읽습니다.",
        when_unset="팀 공간 문서 목록이 비어 있게 됩니다.",
    ),
    DatabaseSpec(
        key="notion_sprint_database_id",
        label="스프린트 데이터베이스",
        token_ref_field="notion_report_token_ref",
        kind="",
        used_for="진단에만 씁니다. 포털의 이번 주는 이 데이터베이스를 읽지 않습니다.",
        when_unset="포털과 팀이 서로 다른 것을 스프린트라고 부르는지 확인할 수 없습니다.",
    ),
)

DATABASES_BY_KEY = {spec.key: spec for spec in DATABASES}

# 토큰 참조 둘. 같은 값을 넣어도 되지만 참조를 나눠 두면 문서 접근만 따로 회수할 수 있다
# (app/core/config.py 가 그 이유를 적어 뒀다).
TOKEN_REFS: tuple[tuple[str, str], ...] = (
    ("notion_report_token_ref", "작업과 티켓용 토큰"),
    ("notion_docs_token_ref", "문서용 토큰"),
)

# 값이 바뀌면 언제 반영되는가. 화면이 이 문장을 그대로 싣는다.
#
# 즉시인 이유: 소비자는 `settings.notion_*_database_id` 를 읽고, 설정 캐시가 저장할 때마다
# 그 위에 값을 얹는다(app/core/tenant_config.py::apply_overrides). 워커는 자기 틱에서 캐시를
# 다시 읽으므로 한 틱 늦는다. 그 차이를 뭉개지 않는다 - "즉시" 라고만 적으면 운영자는
# 동기화가 곧바로 새 DB 를 읽을 거라 믿는다.
APPLY_NOTE = (
    "저장하면 화면과 API 조회에는 곧바로 반영됩니다. 백그라운드 동기화는 다음 실행 주기부터 "
    "새 값을 씁니다. 서비스를 다시 시작할 필요는 없습니다."
)


def _effective_value(settings, effective: dict, key: str) -> tuple[str, str]:
    """(지금 적용 중인 값, 그 값이 어디서 왔는가)."""
    raw = effective.get(key)
    saved = raw.get("value") if isinstance(raw, dict) and "value" in raw else raw
    if isinstance(saved, str) and saved.strip():
        return saved.strip(), "settings"
    env_value = getattr(settings, key, "") or ""
    return str(env_value).strip(), "env"


def token_status(settings, secrets) -> dict:
    """토큰 두 개의 상태 + **이 서버가 토큰을 화면에서 바꿀 수 있는가**.

    쓸 수 없는 것이 운영 설치의 정상 상태다(systemd 하드닝). 그 사실을 숨기고 입력란만
    보여 주면 운영자는 저장 버튼을 누르고 바뀌었다고 믿는다.
    """
    writable = secrets.writable()
    items = []
    for field, label in TOKEN_REFS:
        ref = getattr(settings, field, "") or ""
        items.append(
            {
                "field": field,
                "ref": ref,
                "label": label,
                # 값은 절대 싣지 않는다. 설정됨/안 됨뿐이다.
                "configured": secrets.status(ref) == STATUS_CONFIGURED,
            }
        )
    return {
        "items": items,
        "writable": writable,
        "directory": str(secrets.directory),
        "note": (
            "토큰 값은 저장한 뒤 다시 보여 주지 않습니다. 설정됨 여부와 연결 테스트 결과만 "
            "확인할 수 있습니다."
        ),
        "manual_instruction": None
        if writable
        else (
            "이 서버의 웹 프로세스는 시크릿 디렉터리에 쓸 수 없습니다(의도된 설정입니다). "
            f"서버에서 {secrets.directory} 안에 토큰 참조 이름과 같은 이름의 파일을 만들고 "
            "그 안에 토큰만 한 줄로 넣은 뒤, 소유권과 권한을 다른 시크릿 파일과 같게 맞추세요. "
            "그 다음 이 화면의 연결 테스트로 확인하면 됩니다."
        ),
    }


def sprint_diagnosis(settings, effective: dict) -> dict:
    """포털의 '이번 주' 와 팀의 노션 스프린트가 같은 것을 가리키는가.

    ## 무엇이 문제였나

    포털의 스프린트 화면은 **작업 데이터베이스의 마감일**로 이번 주를 계산한다
    (`app/sprints/service.py::default_sprint_window` - 이번 주 월요일부터 다음 주 월요일까지).
    팀은 노션에 별도의 스프린트 데이터베이스를 두고 거기서 스프린트를 관리한다. 조회해 보면
    404 다(통합에 공유되지 않았다).

    즉 **두 곳이 같은 이름으로 서로 다른 것을 부른다.** 어느 쪽도 고장 나지 않았고, 그래서
    아무 화면도 아무 말을 하지 않았다. 회의에서 두 숫자가 다를 때 사람이 그 자리에서 원인을
    알 방법이 없었다.

    이 진단은 **고치지 않는다.** 무엇이 어긋나 있는지 말할 뿐이다. 포털이 노션 스프린트를
    정본으로 읽게 만드는 것은 별개의 결정이고, 그 결정을 이 화면이 몰래 내리면 안 된다.
    """
    value, source = _effective_value(settings, effective, "notion_sprint_database_id")
    return {
        "portal_window": (
            "포털의 이번 주는 작업 데이터베이스의 마감일로 계산합니다. 이번 주 월요일부터 "
            "다음 주 월요일 직전까지입니다."
        ),
        "sprint_database_id": value,
        "source": source,
        "linked": bool(value),
        "finding": (
            "팀의 노션 스프린트 데이터베이스가 연결돼 있지 않습니다. 포털이 말하는 이번 주와 "
            "팀이 노션에서 관리하는 스프린트는 지금 서로 다른 것입니다. 같은 이름으로 부르고 "
            "있어 회의에서 숫자가 어긋날 수 있습니다."
            if not value
            else
            "스프린트 데이터베이스 id 가 설정돼 있습니다. 연결 테스트로 이 서버가 실제로 그 "
            "데이터베이스를 읽을 수 있는지 확인하세요. 읽을 수 있어도 포털의 이번 주 계산은 "
            "바뀌지 않습니다."
        ),
        "next_step": (
            "스프린트 데이터베이스 id 를 넣고 연결 테스트를 눌러 보세요. 찾지 못한다고 나오면 "
            "노션에서 그 데이터베이스를 통합에 공유해야 합니다."
            if not value
            else
            "포털의 이번 주를 노션 스프린트에 맞추려면 별도 작업이 필요합니다. 이 화면은 두 "
            "곳이 어긋났는지만 알려 줍니다."
        ),
    }


def overview(settings, secrets, effective: dict) -> dict:
    """화면 한 판. 외부 호출을 하지 않는다 - 여는 것만으로 노션을 부르면 안 된다."""
    databases = []
    for spec in DATABASES:
        value, source = _effective_value(settings, effective, spec.key)
        databases.append(
            {
                "key": spec.key,
                "label": spec.label,
                "value": value,
                "source": source,
                "configured": bool(value),
                "creatable": bool(spec.kind),
                "token_ref": getattr(settings, spec.token_ref_field, "") or "",
                "used_for": spec.used_for,
                "when_unset": spec.when_unset,
            }
        )
    return {
        "databases": databases,
        "token": token_status(settings, secrets),
        "sprint": sprint_diagnosis(settings, effective),
        "apply_note": APPLY_NOTE,
    }


def run_connection_test(outbound, settings, secrets) -> dict:
    """토큰 하나와 데이터베이스 셋을 **실제로 부른다**.

    토큰을 먼저 본다. 토큰이 무효면 데이터베이스 결과는 전부 '못 찾음' 으로 보이고, 그 화면은
    운영자를 잘못된 방향(멀쩡한 id 를 다시 붙여 넣기)으로 보낸다.
    """
    tokens = []
    token_ok: dict[str, bool] = {}
    for field, label in TOKEN_REFS:
        ref = getattr(settings, field, "") or ""
        if secrets.status(ref) != STATUS_CONFIGURED:
            view = {
                "ref": ref,
                "result": probe.RESULT_TOKEN_MISSING,
                "message": probe.message_for(probe.RESULT_TOKEN_MISSING),
            }
        else:
            view = probe.check_token(outbound, settings, token_ref=ref)
        view["field"] = field
        view["label"] = label
        tokens.append(view)
        token_ok[field] = view["result"] == probe.RESULT_OK

    databases = []
    for spec in DATABASES:
        value = (getattr(settings, spec.key, "") or "").strip()
        if not value:
            view = {
                "result": probe.RESULT_UNSET,
                "message": probe.message_for(probe.RESULT_UNSET),
            }
        elif not token_ok.get(spec.token_ref_field, False):
            # 토큰이 안 통하는데 DB 를 부르면 무조건 실패한다. 그 실패를 '데이터베이스
            # 문제' 로 그리는 것이 정확히 이 함수가 없애려는 오해다.
            view = {
                "result": probe.RESULT_TOKEN_INVALID,
                "message": (
                    "토큰이 먼저 확인되지 않아 이 데이터베이스는 확인하지 않았습니다."
                ),
            }
        else:
            view = probe.check_database(
                outbound,
                settings,
                database_id=value,
                token_ref=getattr(settings, spec.token_ref_field, "") or "",
            )
        view["key"] = spec.key
        view["label"] = spec.label
        databases.append(view)

    ok = all(t["result"] == probe.RESULT_OK for t in tokens) and all(
        d["result"] in (probe.RESULT_OK, probe.RESULT_UNSET) for d in databases
    )
    return {"ok": ok, "tokens": tokens, "databases": databases}


def guard_create(spec_key: str, settings, effective: dict, *, confirm: bool) -> DatabaseSpec:
    """만들기 전에 세 가지를 본다. 하나라도 걸리면 만들지 않는다.

    되돌리기 어려운 동작이라(노션에 진짜 데이터베이스가 생긴다) 이 문 앞에서 막는 편이
    사후에 지우는 것보다 훨씬 싸다.
    """
    spec = DATABASES_BY_KEY.get(spec_key)
    if spec is None or not spec.kind:
        raise ValidationAppError("이 데이터베이스는 화면에서 만들 수 없습니다.")
    if not confirm:
        raise ValidationAppError("만들기 전에 확인이 필요합니다.")
    value, _source = _effective_value(settings, effective, spec.key)
    if value:
        # **이미 있으면 안 만든다.** 여기서 하나 더 만들면 두 데이터베이스에 티켓이 나뉘고,
        # 그 상태는 사람이 손으로 합치기 전에는 복구되지 않는다.
        raise ConflictError(
            "이미 데이터베이스 id 가 설정돼 있습니다. 새로 만들려면 먼저 이 값을 비우세요."
        )
    return spec


__all__ = [
    "APPLY_NOTE",
    "DATABASES",
    "DATABASES_BY_KEY",
    "OBJECT_TYPE_DATABASE",
    "OBJECT_TYPE_TOKEN",
    "DatabaseSpec",
    "guard_create",
    "overview",
    "run_connection_test",
    "sprint_diagnosis",
    "token_status",
]
