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
from app.setup.steps import CHOICE_DEFAULTS, CHOICE_VALUES, SETUP_STEPS, USER_VISIBLE_KEYS

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
    """선택 값 — 메일 · AI 는 「사용」 · 「사용하지 않음」, TLS 는 「이 서버의 인증서」 · 「외부 프록시가 맡음」. 값이 없거나 모르면
    기본값(사용 · 이 서버)이다.

    `effective` 는 `effective_settings` 의 모양이다(키 → {"value": 값, "type": …}).
    """
    entry = effective.get(CHOICES_KEY) if isinstance(effective, dict) else None
    raw = entry.get("value") if isinstance(entry, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    return {key: (raw.get(key) if raw.get(key) in CHOICE_VALUES[key] else CHOICE_DEFAULTS[key]) for key in CHOICE_VALUES}

# 화면의 상태(D-534) — 서버가 고르고 화면은 그대로 그린다. 상태를 색으로만 말하지 않는다(낱말이 함께 간다).
STATUS_DONE = "done"          # ✓ 완료
STATUS_TODO = "todo"          # ! 해야 함(필수 할 일 · 비어 있는 선택 항목을 쓰기로 한 경우)
STATUS_CHECK = "check"        # ? 확인 필요(설정은 됐지만 실제로 확인하기 전)
STATUS_PENDING = "pending"    # ○ 정하지 않음(선택 항목을 쓸지 아직 정하지 않았다)
STATUS_PROBLEM = "problem"    # ✕ 문제 있음(동작이 실패하고 있다)
STATUS_SKIPPED = "skipped"    # – 사용하지 않음(선택 항목, 완료로 센다)
STATUS_WAITING = "waiting"    # 앞 항목 대기
STATUS_LABELS = {
    STATUS_DONE: "완료", STATUS_TODO: "해야 함", STATUS_CHECK: "확인 필요", STATUS_PENDING: "정하지 않음",
    STATUS_PROBLEM: "문제 있음", STATUS_SKIPPED: "사용하지 않음", STATUS_WAITING: "앞 항목 대기",
}
CHOICE_LABELS = {"unused": "사용하지 않음", "use": "다시 사용", "proxy": "외부 프록시가 맡음", "app": "이 서버의 인증서 사용"}


def _status(item: dict, outcome: Outcome) -> str:
    if item["state"] == STATE_DONE:
        return STATUS_DONE
    if item["state"] == STATE_SKIPPED:
        return STATUS_SKIPPED
    if item["blocked_by"] is not None:
        return STATUS_WAITING
    if item["state"] == STATE_UNKNOWN:
        return STATUS_CHECK
    if outcome.problem:
        return STATUS_PROBLEM
    if not item["required"] and not outcome.configured:
        return STATUS_PENDING
    return STATUS_TODO


def _item_choices(step, outcome: Outcome, choice: str | None) -> list[dict]:
    """이 줄에서 고를 수 있는 값 — 「사용하지 않음」은 비어 있을 때만 뜻이 있다(값을 채우면 실제 상태를 보인다)."""
    out: list[dict] = []
    if step.optional_choice:
        if outcome.state == STATE_SKIPPED:
            out.append({"key": step.optional_choice, "value": "use", "label": CHOICE_LABELS["use"]})
        elif outcome.state != STATE_DONE and not outcome.configured:
            out.append({"key": step.optional_choice, "value": "unused", "label": CHOICE_LABELS["unused"]})
    for value in outcome.choices:
        out.append({"key": step.key, "value": value, "label": CHOICE_LABELS.get(value, value)})
    return out



def build_setup_checklist(
    db: Session,
    settings: Settings,
    *,
    secrets: FileSecretReferenceProvider,
    cache=None,
    gateway=None,
    runtime=None,
    sysops=None,
) -> dict:
    """항목별 상태 + 안내 순서 + 막힌 이유 + 필수와 선택 + 요약 띠(D-534).

    ``cache``: 이미 따뜻한 ``app.state.settings_cache``. 관리 콘솔에서 바꾼 값이 env 보다
    우선하므로(app/core/tenant_config.py) 넘기지 않으면 관리자가 콘솔에서 채워 둔 설정을
    "설정 안 함" 이라고 잘못 말한다. 캐시가 없는 호출부(ad-hoc 스크립트)만 None 이다.
    """
    effective = _effective(db, cache)
    choices = optional_choices(effective)
    ctx = ProbeContext(
        db=db, settings=settings, secrets=secrets, effective=effective, gateway=gateway, runtime=runtime,
        sysops=sysops, choices=choices, base_url=str(getattr(settings, "app_base_url", "") or ""),
    )

    outcomes: dict[str, Outcome] = {}
    for step in SETUP_STEPS:
        outcome = PROBES[step.key](ctx)
        if (step.optional_choice and choices.get(step.optional_choice) == CHOICE_UNUSED
                and outcome.state != STATE_DONE and not outcome.configured):
            outcome = Outcome(state=STATE_SKIPPED, detail=SKIPPED_DETAIL, href=outcome.href,
                              link_label=outcome.link_label, checked_at=outcome.checked_at, configured=False,
                              notes=outcome.notes)
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
                # 펼친 칸 — 상태를 바꾸지 않는 덧붙임과 복사할 명령(D-534).
                "notes": list(outcome.notes),
                "command": outcome.command,
                # 이 줄에서 고를 수 있는 값(「사용하지 않음」 · 「다시 사용」 · 「외부 프록시가 맡음」 …).
                "choices": _item_choices(step, outcome, choices.get(step.optional_choice) if step.optional_choice else None),
            }
        )
        items[-1]["status"] = _status(items[-1], outcome)
        items[-1]["status_label"] = STATUS_LABELS[items[-1]["status"]]

    open_items = [i for i in items if i["state"] not in (STATE_DONE, STATE_SKIPPED)]
    required_remaining = [i["key"] for i in open_items if i["required"]]
    required_total = sum(1 for i in items if i["required"])
    next_key = next(
        (i["key"] for i in open_items if i["blocked_by"] is None and i["required"]),
        next((i["key"] for i in open_items if i["blocked_by"] is None), None),
    )
    for item in items:
        item["current"] = item["key"] == next_key
    headline, subline = _band(items, required_remaining, required_total, next_key)
    return {
        "items": items,
        "remaining": [i["key"] for i in open_items],
        "todo": [i["key"] for i in items if i["state"] == STATE_TODO],
        "unknown": [i["key"] for i in items if i["state"] == STATE_UNKNOWN],
        "skipped": [i["key"] for i in items if i["state"] == STATE_SKIPPED],
        "required_remaining": required_remaining,
        "optional_pending": [i["key"] for i in open_items if not i["required"]],
        # 지금 안내할 항목 = 아직 안 끝났고 막히지도 않은 첫 항목. 필수 항목이 남아 있으면 그것이 먼저다.
        "next_key": next_key,
        "current_key": next_key,
        "required_total": required_total,
        "required_done": required_total - len(required_remaining),
        # 요약 띠의 두 줄(D-534) — 지금 상태 한 문장과 필수 진행 · 다음 할 일(또는 선택 기능의 상태).
        "headline": headline,
        "subline": subline,
        "required_complete": not required_remaining,
        # 설치가 끝났는가 - 필수 항목만 본다(D-520). 메일과 AI 를 쓰지 않는 설치도 정상 설치다.
        "complete": not required_remaining,
        "summary": _summary(items, required_remaining, choices),
    }


def _band(items: list[dict], required_remaining: list[str], required_total: int, next_key: str | None) -> tuple[str, str]:
    """요약 띠. 필수가 남았으면 그 수와 다음 할 일, 끝났으면 선택 기능의 상태를 말한다 - 선택 항목이 할 일 · 문제 있음이어도
    「기본 설정이 끝났습니다」이고 둘째 줄이 그 사실을 말한다."""
    by_key = {i["key"]: i for i in items}
    if required_remaining:
        head = f"필수 설정 {len(required_remaining)}개가 남았습니다."
        sub = f"필수 {required_total}개 중 {required_total - len(required_remaining)}개가 끝났습니다."
        if next_key:
            sub += f" 다음 할 일은 {by_key[next_key]['label']}입니다."
        return head, sub
    optional = [i for i in items if not i["required"]]
    problems = [i["label"] for i in optional if i["status"] == STATUS_PROBLEM]
    undecided = [i["label"] for i in optional if i["status"] in (STATUS_PENDING, STATUS_TODO, STATUS_CHECK, STATUS_WAITING)]
    if problems:
        sub = ", ".join(problems) + "에 문제가 있습니다."
    elif undecided:
        sub = f"선택 기능 {len(undecided)}개는 아직 정하지 않았거나 확인하지 않았습니다."
    else:
        sub = "선택 기능도 모두 정했습니다."
    return "기본 설정이 끝났습니다.", sub


def _summary(items: list[dict], required_remaining: list[str], choices: dict[str, str]) -> str:
    """설치 상태 한 문장. 「사용하지 않음」은 정상 설치의 일부로 말한다."""
    if required_remaining:
        return f"필수 항목이 {len(required_remaining)}개 남았습니다."
    unused = [CHOICE_NOUNS[key] for key, value in choices.items() if value == CHOICE_UNUSED and key in CHOICE_NOUNS
              and any(i["optional_choice"] == key and i["state"] == STATE_SKIPPED for i in items)]
    if unused:
        return "정상 설치입니다(" + ", ".join(f"{noun} 사용 안 함" for noun in unused) + ")."
    return "정상 설치입니다."


NOTICE_CACHE_SECONDS = 60


def _notice_blocking(db: Session, settings: Settings, *, secrets, cache, now, holder: dict | None = None) -> bool:
    """배너를 만드는 유일한 항목(조직과 부서, 필수이면서 사용자에게 보이는 항목)만 판정한다 - 같은 앱 안에서 60초 동안 다시 쓴다.

    예전에는 모든 사용자의 120초 상태 폴링마다 여섯 판정(인증서 두 번 파싱 포함)을 다 돌았다(계획 S1). 캐시는 앱 객체
    (`app.state.setup_notice_cache`)에 둔다 - 프로세스 전역에 두면 앱을 새로 만드는 시험끼리 값이 샌다.
    """
    holder = holder if holder is not None else {}
    at = holder.get("at")
    if at is not None and holder.get("blocking") is not None and 0 <= (now - at).total_seconds() < NOTICE_CACHE_SECONDS:
        return bool(holder["blocking"])
    effective = _effective(db, cache)
    ctx = ProbeContext(db=db, settings=settings, secrets=secrets, effective=effective)
    blocking = False
    for key in USER_VISIBLE_KEYS:
        step = next(s for s in SETUP_STEPS if s.key == key)
        if step.required and PROBES[key](ctx).state not in (STATE_DONE, STATE_SKIPPED):
            blocking = True
            break
    holder.update(at=now, blocking=blocking)
    return blocking


def reset_notice_cache(holder: dict | None) -> None:
    """초기 설정의 선택을 저장한 직후 부른다 - 다음 상태 폴링이 곧바로 새로 판정한다."""
    if holder is not None:
        holder.update(at=None, blocking=None)


def setup_notice(
    db: Session,
    settings: Settings,
    *,
    secrets: FileSecretReferenceProvider,
    cache=None,
    now=None,
    for_admin: bool = False,
    holder: dict | None = None,
    gateway=None,
    runtime=None,
) -> dict | None:
    """**필수 항목**이 안 끝난 동안 모든 로그인 사용자에게 보이는 한 줄. 정상이면 None(D-520 · D-534).

    ## 왜 로그인을 막지 않는가

    셋업이 안 끝났다고 일반 사용자의 로그인을 막으면, 관리자가 설정을 미루는 동안 회사 전체가 앱을 못 쓴다. 그렇다고
    **조용히 빈 목록**을 주면 사용자는 「내 티켓이 사라졌다」로 읽는다. 그래서 들여보내되 왜 비어 있는지 말한다.

    ## 무엇을 판정하는가

    화면이 비는 이유가 될 수 있는 **필수** 항목(조직과 부서)만 본다. 선택 항목과 관리자 계정 · TLS 는 배너를 띄우지 않는다.
    판정은 프로세스 안에서 60초 동안 다시 쓴다(`_notice_blocking`).

    ## 누구에게 링크를 주는가

    초기 설정 화면은 시스템 관리자만 연다. 링크는 시스템 관리자(`for_admin`)에게만 주고, 다른 사람에게는 「시스템 관리자가
    초기 설정을 끝내야 합니다.」만 보인다 - 눌렀더니 권한 없음인 링크는 안내가 아니라 막다른 길이다.
    """
    from datetime import datetime, timezone

    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if not _notice_blocking(db, settings, secrets=secrets, cache=cache, now=moment, holder=holder):
        return None
    message = "초기 설정이 아직 끝나지 않았습니다. 목록이 비어 있을 수 있습니다."
    message += " 초기 설정 화면에서 남은 항목을 확인하세요." if for_admin else " 시스템 관리자가 초기 설정을 끝내야 합니다."
    return {
        "id": USER_NOTICE_ID,
        "level": "warning",
        "message": message,
        "since": None,
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
