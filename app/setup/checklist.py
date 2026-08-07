"""남은 셋업 항목을 계산한다 - 화면과 배너의 유일한 출처 (9-3, P3).

## 이 파일이 답하는 질문

  1. 무엇이 남았는가 (`items`, `remaining`)
  2. **지금** 무엇을 안내해야 하는가 (`next_key`)
  3. 어떤 항목이 **무엇 때문에** 막혔는가 (`blocked_by`)

## 막는 것은 "안 됨" 뿐이다

앞 항목이 **확인 불가**라고 해서 뒤 항목을 막지 않는다. 확인 불가는 사람이 할 일이 아니라
물어볼 일이라, 그것 때문에 다음 단계를 막으면 안내가 영원히 그 자리에 선다. 반대로 앞이
**안 됨**이면 뒤는 지금 해도 동작하지 않으므로 막고, 무엇이 막았는지 이름을 말한다.

## 끝난 항목도 목록에서 지우지 않는다

한 번 닫으면 다시 못 보는 마법사는 설정을 미룬 사람에게 아무 도움이 안 된다. 그래서
`items` 는 언제나 전체이고, 끝났는지는 `complete` 로만 말한다. 화면은 이 목록을 접어 둘
수는 있어도 없앨 수는 없다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.secret_refs import FileSecretReferenceProvider
from app.setup.probes import PROBES, STATE_DONE, STATE_TODO, STATE_UNKNOWN, ProbeContext
from app.setup.steps import SETUP_STEPS, USER_VISIBLE_KEYS

# 사용자 배너에 쓰는 알림 id. 프런트가 이 값으로 배너를 알아본다.
USER_NOTICE_ID = "setup.incomplete"
# 마법사 화면 경로(frontend/src/app/AdminRoutes.jsx 의 "/setup"). 관리자 배너가 여기로 보낸다.
SETUP_SCREEN_HREF = "#/setup"


def build_setup_checklist(
    db: Session,
    settings: Settings,
    *,
    secrets: FileSecretReferenceProvider,
    cache=None,
) -> dict:
    """항목별 상태 + 안내 순서 + 막힌 이유.

    ``cache``: 이미 따뜻한 ``app.state.settings_cache``. 관리 콘솔에서 바꾼 값이 env 보다
    우선하므로(app/core/tenant_config.py) 넘기지 않으면 관리자가 콘솔에서 채워 둔 설정을
    "설정 안 함" 이라고 잘못 말한다. 캐시가 없는 호출부(ad-hoc 스크립트)만 None 이다.
    """
    effective = _effective(db, cache)
    ctx = ProbeContext(db=db, settings=settings, secrets=secrets, effective=effective)

    outcomes = {step.key: PROBES[step.key](ctx) for step in SETUP_STEPS}

    items: list[dict] = []
    for step in SETUP_STEPS:
        outcome = outcomes[step.key]
        blocked_by = _blocked_by(step.requires, outcomes)
        items.append(
            {
                "key": step.key,
                "label": step.label,
                "why": step.why,
                "state": outcome.state,
                "detail": outcome.detail,
                "action": outcome.action,
                "question": outcome.question,
                "requires": list(step.requires),
                "requires_why": step.requires_why,
                "blocked_by": blocked_by,
                "blocked_by_label": (
                    _label_of(blocked_by) if blocked_by is not None else None
                ),
            }
        )

    remaining = [i["key"] for i in items if i["state"] != STATE_DONE]
    return {
        "items": items,
        "remaining": remaining,
        "todo": [i["key"] for i in items if i["state"] == STATE_TODO],
        "unknown": [i["key"] for i in items if i["state"] == STATE_UNKNOWN],
        # 지금 안내할 항목 = 아직 안 끝났고 막히지도 않은 첫 항목.
        "next_key": next(
            (
                i["key"]
                for i in items
                if i["state"] != STATE_DONE and i["blocked_by"] is None
            ),
            None,
        ),
        "complete": not remaining,
    }


def setup_notice(
    db: Session,
    settings: Settings,
    *,
    secrets: FileSecretReferenceProvider,
    cache=None,
    for_admin: bool = False,
) -> dict | None:
    """셋업이 안 끝난 동안 **모든 로그인 사용자**에게 보이는 한 줄. 정상이면 None.

    ## 왜 로그인을 막지 않는가

    셋업이 안 끝났다고 일반 사용자의 로그인을 막으면, 관리자가 설정을 미루는 동안 회사
    전체가 앱을 못 쓴다. 그건 이 과제가 고치려는 문제보다 큰 문제를 새로 만드는 일이다.
    그렇다고 지금처럼 **조용히 빈 목록**을 주면 사용자는 "내 티켓이 사라졌다" 로 읽고
    같은 문의를 반복한다.

    그래서 셋 중 가운데를 고른다: **들여보내되 왜 비어 있는지 말한다.**

    ## 무엇을 말하지 않는가

    항목 키, 설정 키, 파일 경로, 러너 주소는 내보내지 않는다. 일반 사용자에게 그것은
    무엇을 하라는 지시도 못 되면서 내부 구조만 알려 준다(app/observability/router.py 와
    같은 선). 관리자에게만 어디로 가면 되는지 한 문장을 덧붙인다.
    """
    checklist = build_setup_checklist(db, settings, secrets=secrets, cache=cache)
    blocking = [
        item
        for item in checklist["items"]
        # STATE_TODO 만 보면 STATE_UNKNOWN(예: 토큰은 넣었는데 아직 한 번도 동기화되지
        # 않은 Notion, 등록만 되고 헬스체크된 적 없는 러너/연동)이 조용히 빠진다. 그 상태도
        # 화면은 똑같이 비거나 AI 가 답하지 않는다 - "확인 불가" 는 이 화면을 막을 이유가
        # 아니라는 것과, 사용자에게 "왜 비어 있는지" 조용히 넘어가지 않는다는 것은 다른
        # 얘기다. remaining 과 같은 기준(!= STATE_DONE)을 쓴다.
        if item["key"] in USER_VISIBLE_KEYS and item["state"] != STATE_DONE
    ]
    if not blocking:
        return None
    message = (
        "초기 설정이 아직 끝나지 않았습니다. "
        "목록이 비어 있거나 AI 기능이 답하지 않을 수 있습니다."
    )
    message += (
        " 초기 설정 화면에서 남은 항목을 확인하세요."
        if for_admin
        else " 관리자에게 문의해 주세요."
    )
    return {
        "id": USER_NOTICE_ID,
        "level": "warning",
        "message": message,
        "since": None,
        # 관리자에게만 갈 곳을 준다. "초기 설정 화면에서 확인하세요" 라고만 말하고 가는 길을
        # 안 주면 그 문장은 안내가 아니라 수수께끼다. 일반 사용자에게는 열리지 않는 화면이라
        # 링크를 주지 않는다(눌렀더니 권한 없음은 안내가 아니라 막다른 길이다).
        "href": SETUP_SCREEN_HREF if for_admin else None,
    }


def _effective(db: Session, cache) -> dict:
    """관리 콘솔에서 바꾼 설정값. 캐시가 없으면 DB 를 직접 읽는다."""
    from app.settings.service import SettingsCache, effective_settings

    return effective_settings(db, cache or SettingsCache())


def _blocked_by(requires: tuple[str, ...], outcomes: dict) -> str | None:
    """전제 중 **안 됨**인 첫 항목. 확인 불가는 막지 않는다(모듈 docstring 참조)."""
    for key in requires:
        if outcomes[key].state == STATE_TODO:
            return key
    return None


def _label_of(key: str) -> str:
    from app.setup.steps import STEP_BY_KEY

    return STEP_BY_KEY[key].label


__all__ = [
    "build_setup_checklist",
    "setup_notice",
    "USER_NOTICE_ID",
    "STATE_DONE",
    "STATE_TODO",
    "STATE_UNKNOWN",
]
