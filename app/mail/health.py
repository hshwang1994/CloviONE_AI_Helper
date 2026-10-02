"""메일 발송의 건강 상태 — 「값이 있다」와 「동작한다」를 가른다 (계획 2.4 · 3.3 · M2, D-512 · D-546).

## 다섯 상태

  사용 안 함    메일 발송이 꺼져 있다(관리자의 선택이다 — 고장이 아니다).
  설정 덜 됨    켜져 있는데 설정 문제(`configuration_problems`)가 남았다. 보낼 수 없다.
  확인 전       설정은 채워졌지만 **지금 설정으로** 성공한 발송이나 연결 확인이 없다. 설정이나 비밀번호를 바꾸면 여기로 돌아온다.
  정상          마지막 연결 확인이나 발송이 성공했다.
  발송 실패     마지막 연결 확인이나 발송이 메일 서버 문제로 실패했다.

예전에는 「설정됨」이 값이 있다는 뜻뿐이라, 비밀번호가 틀려 모든 메일이 실패해도 초기 설정과 상태 화면이 완료로
보였다. 꺼짐과 덜 채움을 한 상태로 뭉치면 「사용하지 않음」을 고른 설치가 고장으로 보였다.

## 저장된 값만 읽는다

상태는 `sync_status` 의 `mail` 행에 있다(마지막 확인 시각, 마지막 성공 시각, 마지막 오류, 연속 실패 수, 단계). 화면과 초기
설정 점검은 그 행만 읽고 요청 안에서 메일 서버에 연결하지 않는다. 행에는 그때 설정의 지문(`fingerprint`)을 적는다 —
지문이 지금 설정과 다르면 그 기록은 옛 설정의 것이라 「확인 전」이다. 지문에는 **비밀번호 파일의 표지**(수정 시각과 크기,
값은 아니다)가 든다 - 비밀번호만 바꿔도 옛 「정상」 · 「발송 실패」가 지금을 말하지 않는다(D-546).

## 무엇이 상태를 바꾸는가

연결 확인(`mail_verify` 잡)은 성공과 실패 모두 기록한다. 실제 발송은 성공과 **메일 서버 탓인 실패**(연결, 보안 연결,
로그인, 보내는 사람 거부, 임시 거절, 그 밖의 거절)만 기록한다 — 받는 사람 주소가 틀렸거나 본문을 못 만든 실패는
메일 서버가 멀쩡하다는 뜻일 수 있어서 상태를 바꾸지 않는다.

## 복구되면

**지금 지문으로 정상이 아니던 상태**(발송 실패, 설정을 고친 직후의 확인 전, 첫 확인)에서 연결 확인이나 발송이 성공하는 순간,
최대 나이(설정 `mail_notification_max_age_days`, 기본 7일) 안에 메일 서버 탓 · 설정 탓으로 실패한 메일 중 **아직 의미가 있는
것만** 다시 큐에 넣고(`app/mail/relevance.py`), 나머지는 `superseded` 로 끝낸다. 받는 사람 거부와 비밀번호 재설정은 빠진다.
그 건수는 감사에 남는다(`mail.requeue_on_recovery`). 예전에는 같은 지문의 「발송 실패 → 정상」만 복구로 봐서, 호스트나
비밀번호를 고치고 확인이 성공해도 실패한 메일이 다시 나가지 않았다.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mail.config import PASSWORD_SLOT, MailConfig, configuration_problems
from app.mail.models import (
    FAILURE_AUTH,
    FAILURE_CONFIG,
    FAILURE_CONNECT,
    FAILURE_DISCONNECTED,
    FAILURE_REJECTED,
    FAILURE_SENDER,
    FAILURE_TEMPORARY,
    FAILURE_TLS,
    MAIL_FAILED,
    MAIL_QUEUED,
    MAIL_SUPERSEDED,
    MailDelivery,
)

logger = logging.getLogger("app.mail.health")

COMPONENT = "mail"

STATE_DISABLED = "disabled"
STATE_UNCONFIGURED = "unconfigured"
STATE_UNVERIFIED = "unverified"
STATE_OK = "ok"
STATE_FAILING = "failing"

STATE_LABELS = {
    STATE_DISABLED: "사용 안 함",
    STATE_UNCONFIGURED: "설정 덜 됨",
    STATE_UNVERIFIED: "확인 전",
    STATE_OK: "정상",
    STATE_FAILING: "발송 실패",
}
STATE_KINDS = {
    STATE_DISABLED: "neutral", STATE_UNCONFIGURED: "warn", STATE_UNVERIFIED: "info", STATE_OK: "ok",
    STATE_FAILING: "danger",
}

# 메일 서버 탓인 실패 — 이것만 상태를 「발송 실패」로 바꾼다(머리말).
SERVER_FAILURE_KINDS = frozenset({
    FAILURE_AUTH, FAILURE_TLS, FAILURE_SENDER, FAILURE_CONNECT, FAILURE_TEMPORARY, FAILURE_DISCONNECTED,
    FAILURE_REJECTED,
})
# 복구 때 다시 보낼 수 있는 실패. 받는 사람 거부는 서버가 살아나도 같은 결과라 빠진다. 설정 탓(`config`)은 옛 행이다 -
# 예전에는 비밀번호가 없을 때 큐에 들어간 메일이 워커에서 `failed/config` 가 되어 한꺼번에 다시 보낼 수 없었다(D-546).
REQUEUE_ON_RECOVERY_KINDS = frozenset({
    FAILURE_AUTH, FAILURE_TLS, FAILURE_SENDER, FAILURE_CONNECT, FAILURE_TEMPORARY, FAILURE_DISCONNECTED, FAILURE_CONFIG,
})


def secret_marker(secret_provider, slot: str = PASSWORD_SLOT) -> str:
    """비밀번호 파일의 표지(값이 아니다). 제공자가 없는 자리는 `none` - 지문이 웹과 워커에서 같아야 하므로 부르는 쪽 모두가
    제공자를 넘긴다(진단 번들 포함)."""
    if secret_provider is None or not hasattr(secret_provider, "version"):
        return "none"
    try:
        return str(secret_provider.version(slot))
    except Exception:  # noqa: BLE001 - 표지를 못 읽으면 모른다고 적는다
        return "unknown"


def _secret_markers(config: MailConfig, secret_provider) -> str:
    """지문에 넣을 비밀의 표지. 외부 SMTP 는 로그인 비밀번호, 로컬 릴레이는 앱 열쇠(와 상위 SMTP 비밀번호)다."""
    if getattr(config, "local_relay", False):
        from app.core.secret_slots import SLOT_SMTP_RELAY_CLIENT, SLOT_SMTP_RELAY_PASSWORD

        relay = config.relay
        marks = [secret_marker(secret_provider, SLOT_SMTP_RELAY_CLIENT)]
        if relay.delivery == "smarthost" and relay.smarthost.username:
            marks.append(secret_marker(secret_provider, SLOT_SMTP_RELAY_PASSWORD))
        return "|".join(marks)
    return secret_marker(secret_provider) if config.username else "no-login"


def fingerprint(config: MailConfig, secret_provider=None) -> str:
    """상태 기록이 어느 설정의 것인가. 이 값이 바뀌면 옛 기록은 지금 설정을 말하지 않는다."""
    material = json.dumps([
        config.host, config.port, config.security, config.username, PASSWORD_SLOT,
        config.from_address, config.tls_verify, hashlib.sha256(config.ca_pem.encode("utf-8")).hexdigest(),
        getattr(config, "mode", "external"), getattr(config, "relay_fingerprint", ""),
        _secret_markers(config, secret_provider),
    ], ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _row(db: Session):
    from app.observability.models import SyncStatus

    return db.get(SyncStatus, COMPONENT)


def _detail(row) -> dict:
    if row is None or not row.detail_json:
        return {}
    try:
        value = json.loads(row.detail_json)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def health_state(db: Session, config: MailConfig, secret_provider=None) -> dict:
    """지금 상태 한 덩어리. **네트워크를 쓰지 않는다**(머리말). `stages` 는 마지막 확인이 지난 단계와 그 결과다."""
    from app.mail.labels import STAGE_LABELS
    from app.observability.models import SYNC_OK

    problems = configuration_problems(config, secret_provider)
    row = _row(db)
    detail = _detail(row)
    same = row is not None and detail.get("fingerprint") == fingerprint(config, secret_provider)
    base = {
        "checked_at": row.last_run_at.isoformat() if row is not None and row.last_run_at else None,
        "last_success_at": row.last_success_at.isoformat() if row is not None and row.last_success_at else None,
        "failure_kind": None, "stage": None, "consecutive_failures": 0,
        "stages": _stage_rows(detail.get("stages") if same else None, STAGE_LABELS),
    }
    if not config.enabled:
        state, message = STATE_DISABLED, "메일 발송을 사용하지 않습니다."
    elif problems:
        state, message = STATE_UNCONFIGURED, problems[0]
    elif not same:
        state = STATE_UNVERIFIED
        message = "메일 설정은 채워졌지만 지금 설정으로 아직 확인하지 않았습니다."
    elif row.status == SYNC_OK:
        state, message = STATE_OK, "메일 발송을 사용할 수 있습니다."
    else:
        state = STATE_FAILING
        message = row.error or "메일 발송이 실패하고 있습니다."
        base.update(
            failure_kind=detail.get("failure_kind"), stage=detail.get("stage"),
            consecutive_failures=int(detail.get("consecutive_failures") or 0),
        )
    return {"state": state, "label": STATE_LABELS[state], "kind": STATE_KINDS[state], "message": message,
            "problems": problems if state == STATE_UNCONFIGURED else [], **base}


def _stage_rows(raw, labels: dict) -> list[dict]:
    """저장된 단계 기록 → 화면의 줄. 모르는 단계 이름은 버린다(사람이 못 읽는 낱말을 내보내지 않는다)."""
    rows = []
    for item in raw or []:
        if not isinstance(item, dict) or item.get("key") not in labels:
            continue
        rows.append({"key": item["key"], "label": labels[item["key"]], "state": item.get("state") or "not_reached",
                     "detail": item.get("detail")})
    return rows


def record_result(
    db: Session, config: MailConfig, *, ok: bool, now: datetime, source: str,
    failure_kind: str | None = None, stage: str | None = None, summary: str | None = None,
    counts_any_failure: bool = False, secret_provider=None, stages: list[dict] | None = None,
) -> bool:
    """연결 확인이나 발송의 결과를 상태에 적는다. 지금 지문으로 정상이 아니던 상태에서 성공하면 복구 재큐를 돌리고 True 를 준다.

    `counts_any_failure` 는 연결 확인이다 — 확인 자체가 실패했으면 종류와 무관하게 실패다. `stages` 는 연결 확인이 지난 단계와
    결과(`[{key, state, detail}]`)이고 화면의 상태 면이 그대로 그린다.
    """
    from app.observability.models import SYNC_OK, SYNC_ERROR
    from app.observability.service import upsert_sync_status

    if not ok and not counts_any_failure and failure_kind not in SERVER_FAILURE_KINDS:
        return False
    stamp = fingerprint(config, secret_provider)
    row = _row(db)
    before = _detail(row)
    same_config = before.get("fingerprint") == stamp
    was_ok_now = row is not None and row.status == SYNC_OK and same_config
    failures = 0 if ok else (int(before.get("consecutive_failures") or 0) + 1 if same_config else 1)
    detail = {
        "fingerprint": stamp, "source": source, "failure_kind": None if ok else failure_kind,
        "stage": None if ok else stage, "consecutive_failures": failures,
    }
    if stages is not None:
        detail["stages"] = stages
    elif same_config and before.get("stages"):
        # 발송 결과는 단계 기록을 새로 만들지 않는다 - 같은 설정의 마지막 연결 확인 단계를 남긴다.
        detail["stages"] = before.get("stages")
    upsert_sync_status(
        db, COMPONENT, status=SYNC_OK if ok else SYNC_ERROR, now=now,
        error=None if ok else (summary or "메일 발송이 실패했습니다."), detail=detail,
    )
    if ok and not was_ok_now:
        on_recovered(db, now=now)
        return True
    return False


def _max_age_days(db: Session) -> int:
    """복구 재큐 · 쌓인 메일의 창은 관리자가 정한 최대 나이다(D-546). 예전에는 7일로 고정이라 설정과 어긋났다."""
    from app.mail.relevance import _max_age_days as max_age

    return max_age(db)


def on_recovered(db: Session, *, now: datetime) -> dict:
    """복구된 순간 — 최근 7일의 메일 서버 탓 실패 중 아직 의미가 있는 것만 다시 보낸다(머리말)."""
    from app.core.audit import record_audit
    from app.mail.relevance import still_relevant
    from app.mail.service import NOT_RESENDABLE_KINDS, _enqueue_job, record_skipped

    since = now - timedelta(days=_max_age_days(db))
    rows = list(db.execute(
        select(MailDelivery).where(
            MailDelivery.status == MAIL_FAILED,
            MailDelivery.failure_kind.in_(sorted(REQUEUE_ON_RECOVERY_KINDS)),
            MailDelivery.kind.not_in(sorted(NOT_RESENDABLE_KINDS)),
            MailDelivery.created_at >= since,
        ).order_by(MailDelivery.created_at)
    ).scalars())
    requeued = superseded = 0
    for row in rows:
        relevant, reason = still_relevant(db, row, now)
        if relevant:
            row.status = MAIL_QUEUED
            row.failure_kind = None
            row.updated_at = now
            _enqueue_job(db, row, now=now)
            requeued += 1
        else:
            record_skipped(db, row, status=MAIL_SUPERSEDED, reason=reason or "", now=now)
            superseded += 1
    if rows:
        record_audit(
            db, actor_id=None, action="mail.requeue_on_recovery", object_type="mail_delivery",
            after={"requeued": requeued, "superseded": superseded},
        )
        logger.info("메일 발송 복구: 다시 보냄 %s건, 의미가 없어 보내지 않음 %s건", requeued, superseded)
    return {"requeued": requeued, "superseded": superseded}
