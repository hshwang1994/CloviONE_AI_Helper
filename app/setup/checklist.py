"""남은 셋업 항목을 계산한다 - 화면과 배너의 유일한 출처 (9-3, P3 · 계획 3.5, D-520).

## 이 파일이 답하는 질문

  1. 무엇이 남았는가 (`items`, `remaining`)
  2. **지금** 무엇을 안내해야 하는가 (`next_key`)
  3. 어떤 항목이 **무엇 때문에** 막혔는가 (`blocked_by`)
  4. 설치가 끝났는가 (`complete`) - **필수 항목**만 본다(D-520)

## 막는 것은 "안 됨" 뿐이다

앞 항목이 **확인 불가**라고 해서 뒤 항목을 막지 않는다. 확인 불가는 사람이 할 일이 아니라
물어볼 일이라, 그것 때문에 다음 단계를 막으면 안내가 영원히 그 자리에 선다. 반대로 앞이
**안 됨**이면 뒤는 지금 해도 동작하지 않으므로 막고, 무엇이 막았는지 이름을 말한다.

## 필수와 선택, 그리고 「사용하지 않음」

`complete` 는 필수 항목(관리자 계정, 조직과 부서, TLS)이 모두 끝났다는 뜻이다. 메일과 AI 와 외부 연동이 남아 있어도
설치는 끝난 것이다 - 남은 선택 항목은 `optional_pending` 이 따로 말한다. 관리자가 메일이나 AI 를 「사용하지 않음」으로
표시하면(`setup_optional_choices`) 설정이 비어 있는 동안 그 항목은 `skipped` 다. 값을 채우면 선택과 무관하게 실제 상태를
보인다 - 「사용하지 않기로 했다」와 「설정했는데 실패한다」를 같은 줄에 숨기지 않는다.

## 끝난 항목도 목록에서 지우지 않는다

한 번 닫으면 다시 못 보는 마법사는 설정을 미룬 사람에게 아무 도움이 안 된다. 그래서
`items` 는 언제나 전체이고, 끝났는지는 `complete` 로만 말한다. 화면은 이 목록을 접어 둘
수는 있어도 없앨 수는 없다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.secret_refs import FileSecretReferenceProvider
from app.setup.probes import (
    PROBES,
    STATE_DONE,
    STATE_SKIPPED,
    STATE_TODO,
    STATE_UNKNOWN,
    Outcome,
    ProbeContext,
)
from app.setup.steps import SETUP_STEPS, USER_VISIBLE_KEYS

# 사용자 배너에 쓰는 알림 id. 프런트가 이 값으로 배너를 알아본다.
USER_NOTICE_ID = "setup.incomplete"
# 마법사 화면 경로(frontend/src/app/AdminRoutes.jsx 의 "/setup"). 관리자 배너가 여기로 보낸다.
SETUP_SCREEN_HREF = "#/setup"

CHOICE_USE = "use"
CHOICE_UNUSED = "unused"
CHOICES_KEY = "setup_optional_choices"
SKIPPED_DETAIL = "사용하지 않기로 했습니다. 이 기능이 필요해지면 사용하기로 바꾸고 설정을 채우세요."
# 선택 항목의 이름(화면의 「정상 설치(메일 사용 안 함)」 문장에 쓴다).
CHOICE_NOUNS = {"mail": "메일", "llm": "AI"}


def optional_choices(effective: dict) -> dict[str, str]:
    """선택 항목마다 「사용」과 「사용하지 않음」. 값이 없거나 모르면 「사용」이다.

    `effective` 는 `effective_settings` 의 모양이다(키 → {"value": 값, "type": …}).
    """
    entry = effective.get(CHOICES_KEY) if isinstance(effective, dict) else None
    raw = entry.get("value") if isinstance(entry, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    return {step.optional_choice: (CHOICE_UNUSED if raw.get(step.optional_choice) == CHOICE_UNUSED else CHOICE_USE)
            for step in SETUP_STEPS if step.optional_choice}


def build_setup_checklist(
    db: Session,
    settings: Settings,
    *,
    secrets: FileSecretReferenceProvider,
    cache=None,
    gateway=None,
    runtime=None,
) -> dict:
    """항목별 상태 + 안내 순서 + 막힌 이유 + 필수와 선택.

    ``cache``: 이미 따뜻한 ``app.state.settings_cache``. 관리 콘솔에서 바꾼 값이 env 보다
    우선하므로(app/core/tenant_config.py) 넘기지 않으면 관리자가 콘솔에서 채워 둔 설정을
    "설정 안 함" 이라고 잘못 말한다. 캐시가 없는 호출부(ad-hoc 스크립트)만 None 이다.
    """
    effective = _effective(db, cache)
    ctx = ProbeContext(
        db=db, settings=settings, secrets=secrets, effective=effective, gateway=gateway, runtime=runtime,
    )
    choices = optional_choices(effective)

    outcomes: dict[str, Outcome] = {}
    for step in SETUP_STEPS:
        outcome = PROBES[step.key](ctx)
        if (step.optional_choice and choices.get(step.optional_choice) == CHOICE_UNUSED
                and outcome.state != STATE_DONE and not outcome.configured):
            outcome = Outcome(state=STATE_SKIPPED, detail=SKIPPED_DETAIL, href=outcome.href,
                              link_label=outcome.link_label, checked_at=outcome.checked_at, configured=False)
        outcomes[step.key] = outcome

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
                "href": outcome.href,
                "link_label": outcome.link_label,
                "checked_at": outcome.checked_at,
                "required": step.required,
                # 「사용하지 않음」을 고를 수 있는 항목이면 그 이름과 지금의 선택.
                "optional_choice": step.optional_choice,
                "choice": choices.get(step.optional_choice) if step.optional_choice else None,
                # 관리자가 이 항목에 무언가를 넣었는가 - 「사용하지 않음」 단추는 비어 있을 때만 뜻이 있다.
                "configured": outcome.configured,
                "requires": list(step.requires),
                "requires_why": step.requires_why,
                "blocked_by": blocked_by,
                "blocked_by_label": (
                    _label_of(blocked_by) if blocked_by is not None else None
                ),
            }
        )

    open_items = [i for i in items if i["state"] not in (STATE_DONE, STATE_SKIPPED)]
    required_remaining = [i["key"] for i in open_items if i["required"]]
    return {
        "items": items,
        "remaining": [i["key"] for i in open_items],
        "todo": [i["key"] for i in items if i["state"] == STATE_TODO],
        "unknown": [i["key"] for i in items if i["state"] == STATE_UNKNOWN],
        "skipped": [i["key"] for i in items if i["state"] == STATE_SKIPPED],
        "required_remaining": required_remaining,
        "optional_pending": [i["key"] for i in open_items if not i["required"]],
        # 지금 안내할 항목 = 아직 안 끝났고 막히지도 않은 첫 항목. 필수 항목이 남아 있으면 그것이 먼저다.
        "next_key": next(
            (i["key"] for i in open_items if i["blocked_by"] is None and i["required"]),
            next((i["key"] for i in open_items if i["blocked_by"] is None), None),
        ),
        "required_complete": not required_remaining,
        # 설치가 끝났는가 - 필수 항목만 본다(D-520). 메일과 AI 를 쓰지 않는 설치도 정상 설치다.
        "complete": not required_remaining,
        "summary": _summary(items, required_remaining, choices),
    }


def _summary(items: list[dict], required_remaining: list[str], choices: dict[str, str]) -> str:
    """설치 상태 한 문장. 「사용하지 않음」은 정상 설치의 일부로 말한다."""
    if required_remaining:
        return f"필수 항목이 {len(required_remaining)}개 남았습니다."
    unused = [CHOICE_NOUNS[key] for key, value in choices.items() if value == CHOICE_UNUSED and key in CHOICE_NOUNS
              and any(i["optional_choice"] == key and i["state"] == STATE_SKIPPED for i in items)]
    if unused:
        return "정상 설치입니다(" + ", ".join(f"{noun} 사용 안 함" for noun in unused) + ")."
    return "정상 설치입니다."


def setup_notice(
    db: Session,
    settings: Settings,
    *,
    secrets: FileSecretReferenceProvider,
    cache=None,
    gateway=None,
    runtime=None,
    for_admin: bool = False,
) -> dict | None:
    """**필수 항목**이 안 끝난 동안 모든 로그인 사용자에게 보이는 한 줄. 정상이면 None(D-520).

    ## 왜 로그인을 막지 않는가

    셋업이 안 끝났다고 일반 사용자의 로그인을 막으면, 관리자가 설정을 미루는 동안 회사
    전체가 앱을 못 쓴다. 그건 이 과제가 고치려는 문제보다 큰 문제를 새로 만드는 일이다.
    그렇다고 **조용히 빈 목록**을 주면 사용자는 "내 티켓이 사라졌다" 로 읽고 같은 문의를 반복한다.
    그래서 셋 중 가운데를 고른다: **들여보내되 왜 비어 있는지 말한다.**

    ## 선택 항목은 배너를 띄우지 않는다

    메일과 AI 를 쓰지 않는 설치는 정상 설치다. 그 설치에서 배너가 영원히 뜨면 사람들은 배너를 안 읽게 된다. 화면이 비는
    이유가 될 수 있는 **필수** 항목(조직과 부서)이 남았을 때만 말한다.

    ## 무엇을 말하지 않는가

    항목 키, 설정 키, 파일 경로는 내보내지 않는다. 일반 사용자에게 그것은 무엇을 하라는 지시도 못 되면서 내부 구조만
    알려 준다(app/observability/router.py 와 같은 선). 관리자에게만 어디로 가면 되는지 한 문장을 덧붙인다.
    """
    checklist = build_setup_checklist(db, settings, secrets=secrets, cache=cache, gateway=gateway, runtime=runtime)
    blocking = [
        item
        for item in checklist["items"]
        # 확인 불가(unknown)도 화면이 비는 이유일 수 있으므로 「끝나지 않음」은 done 이 아닌 모든 상태다.
        if item["required"] and item["key"] in USER_VISIBLE_KEYS and item["state"] not in (STATE_DONE, STATE_SKIPPED)
    ]
    if not blocking:
        return None
    message = "초기 설정이 아직 끝나지 않았습니다. 목록이 비어 있을 수 있습니다."
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
    "optional_choices",
    "USER_NOTICE_ID",
    "STATE_DONE",
    "STATE_TODO",
    "STATE_UNKNOWN",
    "STATE_SKIPPED",
]
