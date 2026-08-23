"""알림 설정·방해금지의 **순수 규칙** — DB도 요청도 모른다.

## 방해금지는 알림을 삼키는 기능이 아니다

방해금지(DND)를 "알림을 만들지 않는다"로 구현하면 사용자는 그 시간에 벌어진 일을
**영영 모른다**. 회의 중에 켰다가 끄면 그 사이의 멘션·승인 요청이 통째로 사라진다 —
사용자가 일을 놓치고, 그러면 아무도 이 기능을 안 켠다.

그래서 이 모듈이 판정하는 것은 **'지금 조용히 할 것인가'** 하나뿐이다:

  * 알림 행(`notifications`)은 **평소와 똑같이 만들어지고 안 읽음으로 쌓인다**.
  * DND 중에는 **배지 숫자(푸시 신호)만** 0으로 나간다. 목록에는 전부 그대로 있다.
  * DND 가 끝나면 그동안 쌓인 것이 배지에 한꺼번에 다시 나타난다 — **미뤄진 것**이지
    사라진 것이 아니다.

같은 원칙이 유형별 뮤트(`muted_types`)에도 적용된다. 뮤트한 유형도 목록에는 그대로
나오고 `muted: true` 로 표시될 뿐, 배지에서만 빠진다.

## 시간 판정은 Asia/Seoul 벽시계

'22시부터 조용히'는 사용자가 보는 시계 기준이다. DB 의 naive UTC 로 판정하면 KST 밤
10시가 UTC 13시라 하루가 통째로 어긋난다(§불변 9: 표시·경계는 Asia/Seoul).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ── 알림 유형 레지스트리 ──────────────────────────────────────────────────────
# 뮤트할 수 있는 유형을 **여기서만** 정한다. 모르는 유형은 뮤트 대상이 아니다 —
# 오타로 만든 키가 조용히 저장되면 사용자는 "껐는데 계속 온다"를 겪고, 새 유형이 생겼을 때
# 예전 오타 키가 우연히 맞아떨어져 처음부터 꺼진 채로 배포될 수도 있다.
#
# 값은 (표시 이름, 설명). 화면이 이 목록을 그대로 그린다 — 프런트에 유형 목록을 복사해 두면
# 서버가 유형을 추가해도 화면에는 영영 안 나온다.
NOTIFICATION_TYPES: dict[str, tuple[str, str]] = {
    "chat_invited": ("채팅방 초대", "누군가 나를 채팅방에 초대했을 때"),
    "chat_mentioned": ("@멘션", "채팅에서 누군가 나를 불렀을 때"),
    "approval_requested": ("승인 요청", "내가 승인해야 할 건이 생겼을 때"),
    "approval_decided": ("승인 결과", "내가 올린 건이 승인/반려되었을 때"),
    "approval_expired": ("승인 만료", "승인 대기 건이 기한을 넘겼을 때"),
    "approval_cancelled": ("승인 취소", "내가 올린 요청이 다른 사람에 의해 취소되었을 때"),
    "job_failed": ("작업 실패", "자동화 작업이 실패했을 때"),
    "schedule_failed": ("일정 실행 실패", "예약된 실행이 실패했을 때"),
    "maintenance_announcement": ("유지보수 공지", "점검 예정, 완료 공지"),
    # ── 알림 5종 신설 (X9 + §E-6 N2) ──────────────────────────────────────────
    # 이 다섯 사건은 감사에서 알림이 **0건**이었다. 여기 등록하지 않으면 알림은 오는데
    # 설정 화면에는 안 보여서 사용자가 끌 수가 없다 — "왜 이것만 못 끄지"가 남는다.
    # (뮤트해도 알림 자체는 목록에 남는다. 빠지는 것은 배지뿐이다 — 모듈 docstring.)
    "ticket_assigned": ("티켓 배정", "누군가 나를 티켓 담당자로 지정했을 때"),
    "offboarding_handover": ("업무 인수", "퇴사자의 티켓을 내가 넘겨받았을 때"),
    "ai_quota_exhausted": ("AI 사용 상한 도달", "이번 기간의 AI 호출 상한을 다 썼을 때"),
    "backup_failed": ("백업 실패", "예약 또는 수동 백업이 실패했을 때"),
    # NOTI-03 재조사: 발단이었던 chat_invited는 이미 등록돼 있었다(오래전 정정) — 재조사
    # 중 실제로 발신되는데 이 레지스트리에 없는 여섯 유형을 새로 찾았다. 여기 없으면
    # parse_muted가 "모르는 키"로 조용히 버려서 사용자가 절대로 끌 수 없다(위 다섯과
    # 같은 결함 부류, 방해금지 원칙은 동일 — 목록엔 남고 배지에서만 빠진다).
    "approval_delegated": ("승인 권한 위임받음", "다른 사람의 승인 권한을 대신 위임받았을 때"),
    "approval_overdue": ("승인 기한 초과", "내가 처리해야 할 승인 요청이 기한을 넘겼을 때"),
    "board_comment": ("게시글 댓글", "내가 쓴 게시글에 댓글이 달렸을 때"),
    "document_comment": ("문서 댓글", "내가 관련된 문서에 댓글이 달렸을 때"),
    "idea_status_changed": ("제안 상태 변경", "내가 올린 기능 개선 제안의 상태가 바뀌었을 때"),
    "ticket_comment": ("티켓 댓글", "내가 관련된 티켓에 댓글이 달렸을 때"),
    # S6. 관찰자로 등록한 티켓의 상태가 바뀔 때 온다. 담당자가 아니라 **결과를 알아야
    # 하는 사람**(요청한 영업, 검수할 PM)이 받는 알림이라 배정 알림과 다른 유형이다 —
    # 한 유형으로 묶으면 '티켓 배정'을 끄는 순간 관찰까지 함께 꺼진다.
    "ticket_status_changed": ("티켓 상태 변경", "내가 지켜보는 티켓의 상태가 바뀌었을 때"),
}

# 뮤트할 수 없는 유형 — 계정 보안에 관한 알림이다. 끌 수 있게 만들면 침해를 알리는
# 유일한 신호를 사용자가 스스로 끌 수 있게 된다.
UNMUTABLE_TYPES = frozenset({"account_locked", "password_change_required"})

_TYPE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HHMM_RE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")

# 투어 버전. 투어 내용을 크게 바꿔 다시 보여줘야 할 때만 올린다.
TOUR_VERSION = 1


def parse_muted(raw: str | None) -> list[str]:
    """저장 문자열 → 유형 키 목록. 모르는/버려진 키는 조용히 무시한다.

    무시하는 쪽이 옳다: 유형이 레지스트리에서 사라졌다는 것은 그 알림이 더는 안 온다는
    뜻이고, 남은 키 때문에 설정 화면이 깨지면 사용자가 다른 설정도 못 고친다.
    """
    if not raw:
        return []
    seen: list[str] = []
    for part in raw.split(","):
        key = part.strip()
        if key in NOTIFICATION_TYPES and key not in seen:
            seen.append(key)
    return seen


def serialize_muted(keys) -> str:
    """유형 키 목록 → 저장 문자열. 레지스트리에 없는 키는 버린다(검증은 아래 validate)."""
    return ",".join(parse_muted(",".join(str(k).strip() for k in (keys or []))))


def validate_muted(keys) -> tuple[list[str], list[str]]:
    """(유효한 키, 거부된 키). 라우터가 거부된 키를 422 로 알려 준다.

    조용히 버리지 않는 이유: 화면이 보낸 키가 서버에 없다는 것은 프런트와 서버의 목록이
    어긋났다는 뜻이고, 그건 사용자가 아니라 우리가 알아야 할 사실이다.
    """
    valid: list[str] = []
    rejected: list[str] = []
    for raw in keys or []:
        key = str(raw).strip()
        if not _TYPE_KEY_RE.match(key) or key not in NOTIFICATION_TYPES:
            rejected.append(key)
        elif key not in valid:
            valid.append(key)
    return valid, rejected


def parse_hhmm(value: str | None) -> int | None:
    """'HH:MM' → 자정 이후 분. 형식이 어긋나면 None."""
    match = _HHMM_RE.match((value or "").strip())
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def in_quiet_window(minutes: int, start: int, end: int) -> bool:
    """자정을 넘는 구간(22:00→08:00)까지 다루는 창 판정. 끝은 배타적이다.

    start == end 는 **길이 0**으로 본다(24시간이 아니라). 24시간으로 해석하면 실수로
    같은 값을 넣은 사람이 영원히 조용해지고, 그 사실을 알아챌 단서가 화면에 없다.
    """
    if start == end:
        return False
    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end


@dataclass(frozen=True, slots=True)
class QuietState:
    """지금 조용히 할 것인가 + 그 이유. 이유가 있어야 화면이 설명할 수 있다."""

    quiet: bool
    reason: str | None = None          # 'manual' | 'quiet_hours' | None
    until: datetime | None = None      # 수동 DND 의 자동 해제 시각(naive UTC)
    expired: bool = False              # dnd_until 이 지나 자동으로 풀렸다


def evaluate_quiet(
    *,
    dnd_enabled: bool,
    dnd_until: datetime | None,
    quiet_hours_enabled: bool,
    quiet_start: str,
    quiet_end: str,
    now: datetime,
    timezone_name: str = "Asia/Seoul",
) -> QuietState:
    """지금 배지를 조용히 할지 판정한다. `now` 는 naive UTC(앱 전체 규약).

    수동 DND 가 조용시간보다 우선한다 — 사용자가 방금 누른 것이 예약보다 강해야 한다.
    """
    if dnd_enabled:
        if dnd_until is None:
            return QuietState(quiet=True, reason="manual", until=None)
        if dnd_until > now:
            return QuietState(quiet=True, reason="manual", until=dnd_until)
        # 시각이 지났다 — 조용하지 않고, 서비스가 상태를 정리하도록 알린다.
        return QuietState(quiet=False, reason=None, until=None, expired=True)

    if quiet_hours_enabled:
        start = parse_hhmm(quiet_start)
        end = parse_hhmm(quiet_end)
        if start is not None and end is not None:
            local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(timezone_name))
            minutes = local.hour * 60 + local.minute
            if in_quiet_window(minutes, start, end):
                return QuietState(quiet=True, reason="quiet_hours", until=None)

    return QuietState(quiet=False)


def notification_type_catalog() -> list[dict]:
    """설정 화면이 그리는 유형 목록(서버가 정본)."""
    return [
        {"key": key, "label": label, "help": help_text}
        for key, (label, help_text) in NOTIFICATION_TYPES.items()
    ]
