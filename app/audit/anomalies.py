"""감사 로그 이상 탐지 — **결정적 규칙만** (0033, PLAN Phase 6).

## 왜 통계 모델이나 LLM 이 아닌가

이 화면의 출력은 "이 사람을 조사하라"에 가깝다. 그런 결론은 **왜 그렇게 판단했는지 한 줄로
설명할 수 있어야** 하고, 같은 데이터에 대해 항상 같은 답이 나와야 한다(내일 다시 열었을 때
어제의 경보가 사라져 있으면 아무도 안 믿는다). 그래서 규칙은 전부 셀 수 있는 사실이고,
각 소견에 근거(`evidence`)와 임계값(`threshold`)이 함께 나간다.

## 규칙 다섯 가지

1. `failure_burst`   — 한 행위자의 실패(result != success)가 창 안에서 임계 이상
2. `volume_spike`    — 한 행위자의 행위 수가 창 안에서 임계 이상
3. `off_hours`       — KST 심야(22:00~07:00)에 일어난 **위험 동작**
4. `critical_action` — 권한·계정에 관한 동작(역할 변경, 임퍼소네이션 등)
5. `new_actor_action`— 그 행위자가 **처음** 하는 동작 유형(비교 구간에 전례 없음)

임계값은 조직 규모(1000명 미만)에 맞춘 보수적인 값이다. 낮게 잡으면 매일 경보가 수십 개
쌓여 아무도 안 보고, 그러면 없는 것과 같다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.actions import SENSITIVE_ACTION_PREFIXES, with_cli_variants
from app.audit.models import AuditLog
from app.audit.repository import apply_scope

_KST = ZoneInfo("Asia/Seoul")

# 기본 조회 창(시간). 하루보다 조금 길게 잡아 밤샘 작업이 두 조각으로 갈리지 않게 한다.
DEFAULT_WINDOW_HOURS = 24
MAX_WINDOW_HOURS = 24 * 30

FAILURE_BURST_THRESHOLD = 5
VOLUME_SPIKE_THRESHOLD = 200

# 심야로 보는 KST 시각(시작 포함, 끝 미포함으로 두 구간).
OFF_HOURS_START = 22
OFF_HOURS_END = 7

# 심야에 일어나면 눈에 띄어야 하는 동작들. 조회는 포함하지 않는다 — 밤에 대시보드를 본 것은
# 이상이 아니다. **상태를 바꾸거나 권한에 닿는 것**만 본다.
# (SEC-22: app/audit/actions.py 에서 가져온다 - app/health/service.py 의 "최근 주요
# 변경" 위젯과 같은 목록을 봐야, CLI(cli.user.*)로 한 동작이 이 화면에서만 조용히
# 빠지는 사각지대가 다시 생기지 않는다.)

# 그 자체로 항상 보고 대상인 동작(웹 스펠링). CLI 는 대부분 다른 철자를 쓰므로
# (SEC-22, app/audit/actions.py 참조) 아래에서 with_cli_variants() 로 넓힌 뒤에 쓴다.
CRITICAL_ACTIONS = (
    "user.role_change",
    "impersonation.start",
    "approval_delegation.create",
    "feature_flag.update",
)
CRITICAL_ACTIONS_MATCH = with_cli_variants(CRITICAL_ACTIONS)

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"


def _is_off_hours(created_at: datetime) -> bool:
    local = created_at.replace(tzinfo=timezone.utc).astimezone(_KST)
    return local.hour >= OFF_HOURS_START or local.hour < OFF_HOURS_END


def _is_sensitive(action: str) -> bool:
    return any(action.startswith(prefix) for prefix in SENSITIVE_ACTION_PREFIXES)


def _finding(
    kind: str,
    severity: str,
    actor_id: str | None,
    title: str,
    detail: str,
    *,
    count: int,
    threshold: int | None,
    evidence: list[str],
    first_at: datetime | None,
    last_at: datetime | None,
) -> dict:
    return {
        # id 는 안정적이어야 한다 — 화면이 새로 고쳐도 같은 소견이 같은 키를 갖는다.
        "id": f"{kind}:{actor_id or 'system'}:{title}",
        "kind": kind,
        "severity": severity,
        "actor_id": actor_id,
        "title": title,
        "detail": detail,
        "count": count,
        "threshold": threshold,
        "evidence": evidence[:5],
        "first_at": first_at.isoformat() if first_at else None,
        "last_at": last_at.isoformat() if last_at else None,
    }


def detect(
    db: Session,
    *,
    now: datetime,
    actor_ids: frozenset[str] | None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> dict:
    """창 안의 감사 로그에서 소견 목록을 만든다. 부작용 없음(읽기 전용).

    ``actor_ids`` 는 **보는 사람이 볼 수 있는 행위자 집합**이다(전역이면 ``None``).
    기본값을 두지 않은 것은 일부러다 — 기본값이 있으면 새 호출부가 인자를 잊었을 때
    조용히 **전량 조회**로 열린다. 이 화면이 정확히 그렇게 새고 있었다.
    """
    window_hours = max(1, min(int(window_hours), MAX_WINDOW_HOURS))
    since = now - timedelta(hours=window_hours)
    # UA-17: `select(AuditLog)`는 전체 컬럼(특히 `before_json`/`after_json` — 설정·사용자
    # 변경 diff를 통째로 담는 무제한 Text)을 30일치까지 ORM 객체로 그대로 적재했다. 아래
    # 다섯 규칙 전부 이 함수가 실제로 읽는 컬럼은 user_id/action/result/created_at/
    # object_type/object_id 여섯 개뿐이다(diff 본문은 한 번도 안 읽는다) — 그 컬럼만
    # 골라 선택한다. `Row`도 `AuditLog` 인스턴스와 똑같이 `.user_id`/`.action`처럼 속성
    # 접근이 되므로(SQLAlchemy 2.0 네임드터플형 Row) 아래 다섯 규칙의 `e.xxx` 코드는
    # 한 줄도 안 바뀐다 — 창 안 전체 행을 보는 판정 범위(기간을 자르지 않는다)는 그대로
    # 유지하면서 행마다 실어 나르는 바이트만 줄인다.
    rows = (
        db.execute(
            apply_scope(
                select(
                    AuditLog.user_id, AuditLog.action, AuditLog.result,
                    AuditLog.created_at, AuditLog.object_type, AuditLog.object_id,
                ).where(AuditLog.created_at >= since),
                actor_ids,
            ).order_by(AuditLog.created_at)
        )
        .all()
    )

    by_actor: dict[str | None, list[AuditLog]] = defaultdict(list)
    for row in rows:
        by_actor[row.user_id].append(row)

    findings: list[dict] = []

    for actor_id, entries in by_actor.items():
        failures = [e for e in entries if e.result != "success"]
        if len(failures) >= FAILURE_BURST_THRESHOLD:
            findings.append(_finding(
                "failure_burst", SEVERITY_HIGH, actor_id,
                "실패가 몰려 있습니다",
                f"{window_hours}시간 안에 실패한 동작이 {len(failures)}건입니다. "
                "권한 부족을 반복해 시도했거나, 자동화가 잘못된 값으로 계속 재시도하고 있을 수 있습니다.",
                count=len(failures), threshold=FAILURE_BURST_THRESHOLD,
                evidence=[f"{e.action} ({e.result})" for e in failures],
                first_at=failures[0].created_at, last_at=failures[-1].created_at,
            ))

        if len(entries) >= VOLUME_SPIKE_THRESHOLD:
            findings.append(_finding(
                "volume_spike", SEVERITY_MEDIUM, actor_id,
                "평소보다 동작이 많습니다",
                f"{window_hours}시간 안에 {len(entries)}건입니다. 대량 작업이나 스크립트일 수 있습니다.",
                count=len(entries), threshold=VOLUME_SPIKE_THRESHOLD,
                evidence=sorted({e.action for e in entries}),
                first_at=entries[0].created_at, last_at=entries[-1].created_at,
            ))

        night = [e for e in entries if _is_off_hours(e.created_at) and _is_sensitive(e.action)]
        if night:
            findings.append(_finding(
                "off_hours", SEVERITY_MEDIUM, actor_id,
                "심야에 설정, 권한을 바꿨습니다",
                f"한국 시간 {OFF_HOURS_START}시~{OFF_HOURS_END}시 사이에 {len(night)}건입니다.",
                count=len(night), threshold=1,
                evidence=[f"{e.action} @{e.created_at.replace(tzinfo=timezone.utc).astimezone(_KST):%m-%d %H:%M}" for e in night],
                first_at=night[0].created_at, last_at=night[-1].created_at,
            ))

        critical = [e for e in entries if e.action in CRITICAL_ACTIONS_MATCH]
        if critical:
            findings.append(_finding(
                "critical_action", SEVERITY_HIGH, actor_id,
                "권한, 계정에 관한 동작이 있었습니다",
                "역할 변경, 임퍼소네이션, 승인 위임, 기능 플래그는 한 건이라도 확인 대상입니다.",
                count=len(critical), threshold=1,
                evidence=[f"{e.action} → {e.object_type}/{e.object_id or '-'}" for e in critical],
                first_at=critical[0].created_at, last_at=critical[-1].created_at,
            ))

    # 5) 처음 하는 동작 유형 — 창 이전 30일을 비교 구간으로 쓴다.
    #
    # 비교 구간에도 **같은 범위**를 건다. 소견은 어차피 범위 안 행위자에 대해서만 나오므로
    # 안 걸어도 새지는 않지만, 이 함수가 읽는 행이 한 종류라도 범위를 벗어나면 다음 규칙을
    # 추가하는 사람이 그 행을 그대로 소견에 실어 버린다 — '이 함수는 볼 수 있는 것만 읽는다'
    # 가 규칙이어야 그런 실수가 생길 자리가 없다.
    baseline_since = since - timedelta(days=30)
    baseline = {
        (r[0], r[1])
        for r in db.execute(
            apply_scope(
                select(AuditLog.user_id, AuditLog.action).where(
                    AuditLog.created_at >= baseline_since, AuditLog.created_at < since
                ),
                actor_ids,
            )
        ).all()
    }
    if baseline:  # 비교 구간이 비어 있으면 '전부 처음'이 되어 소음만 만든다
        for actor_id, entries in by_actor.items():
            fresh = sorted({e.action for e in entries if (actor_id, e.action) not in baseline})
            sensitive_fresh = [a for a in fresh if _is_sensitive(a)]
            if sensitive_fresh:
                matching = [e for e in entries if e.action in set(sensitive_fresh)]
                findings.append(_finding(
                    "new_actor_action", SEVERITY_LOW, actor_id,
                    "이 계정이 처음 하는 동작입니다",
                    "최근 30일 동안 이 계정이 한 적 없던 설정, 권한 관련 동작입니다.",
                    # UA-27: sensitive_fresh는 **동작 종류**(집합, 중복 제거)라 count에 그 길이를
                    # 쓰면 실제 발생 건수가 아니라 종류 수가 된다 — 같은 새 동작을 5번 해도
                    # 화면의 "건수" 열엔 1이 뜬다. 형제 소견 4종은 전부 원시 이벤트 목록의
                    # 길이를 쓰므로(failures/entries/night/critical), 여기만 다른 축을 쓰면
                    # 같은 "건수" 열이 소견 종류마다 다른 것을 센다 — 실제 이벤트 목록인
                    # matching으로 맞춘다(evidence는 여전히 "어떤 새 동작들이었는가"를 보여줘야
                    # 하므로 종류 목록 그대로 둔다).
                    count=len(matching), threshold=1,
                    evidence=sensitive_fresh,
                    first_at=matching[0].created_at if matching else None,
                    last_at=matching[-1].created_at if matching else None,
                ))

    order = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["kind"], f["actor_id"] or ""))
    return {
        "findings": findings,
        "window_hours": window_hours,
        "since": since.isoformat(),
        "until": now.isoformat(),
        "scanned": len(rows),
        "thresholds": {
            "failure_burst": FAILURE_BURST_THRESHOLD,
            "volume_spike": VOLUME_SPIKE_THRESHOLD,
            "off_hours_kst": [OFF_HOURS_START, OFF_HOURS_END],
        },
    }
