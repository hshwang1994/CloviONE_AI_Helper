"""Regression tests pinned to defects found during development (spec §31 재발 방지).
Each test names the defect it guards against so a reintroduction fails loudly."""

import pytest

pytestmark = pytest.mark.regression


def test_message_ordering_stable_under_same_timestamp(db, settings, make_user):
    """Defect: Windows clock tick (~15ms) made message created_at ties common,
    so user/assistant messages sometimes rendered out of order.

    삽입 순서로 정렬해서 고쳤다 — 예전에는 SQLite 의 숨은 `rowid` 였고, 지금은
    `messages.seq`(`GENERATED ALWAYS AS IDENTITY`)다. 컬럼으로 올려 둔 덕에 어느 DB 에서도
    같은 순서가 나온다(app/conversations/models.py).
    """
    from datetime import datetime

    from app.chat.service import create_conversation, list_messages
    from app.conversations.models import Message

    user = make_user("order@goodmit.co.kr")
    conv = create_conversation(db, user)
    fixed = datetime(2026, 7, 14, 0, 0, 0)  # identical timestamp for all rows
    for i in range(10):
        db.add(Message(
            conversation_id=conv.id, message_id=f"ord-{i}", role="user",
            content=str(i), processing_status="done", created_at=fixed, updated_at=fixed,
        ))
    db.commit()
    ordered = [m.content for m in list_messages(db, conv)]
    assert ordered == [str(i) for i in range(10)]


def test_sqlite_datetime_claim_uses_microsecond_format(db, fake_clock):
    """Defect: claim_next compared datetimes as strings but used the wrong
    format, so available_at<=now never matched and no job was ever claimed.
    Fixed by strftime('%Y-%m-%d %H:%M:%S.%f')."""
    from app.jobs import repository

    now = fake_clock.now()
    repository.enqueue(db, job_type="reg", payload={}, now=now)
    db.commit()
    assert repository.claim_next(db, now) is not None


def test_router_factory_bodies_are_recognized():
    """Defect: `from __future__ import annotations` in the prompt/policy router
    factory stringified closure-typed params, so FastAPI saw the request body
    as a query param and every create returned 422. Guard: the module must NOT
    use future annotations."""
    import app.prompts.router as prompts_router

    src = open(prompts_router.__file__, encoding="utf-8").read()
    # Check for an actual import statement at the start of a line — not the
    # phrase appearing inside the explanatory module docstring.
    import_lines = [
        ln for ln in src.splitlines()
        if ln.strip() == "from __future__ import annotations"
    ]
    assert import_lines == []


def test_verify_backup_survives_malformed_image(tmp_path):
    """깨진 백업 파일을 만나도 **예외가 아니라 not-ok 로 답한다.**

    원래 결함: `PRAGMA integrity_check` 가 깨진 이미지에서 `DatabaseError` 를 던졌고,
    그것이 그대로 위로 새 나가 검증 화면이 500 이 됐다. 검증기는 «못 믿겠다» 를 말할 줄
    알아야지 터지면 안 된다.

    qa-contract-change: 대상이 `sqlite_backup.verify_backup` 에서 `pg_backup.verify_backup`
    으로 바뀌었다(D-187). 못박는 성질은 같다 — 깨진 파일에 예외가 아니라 `ok=False` 다.
    도구가 없는 개발 머신에서는 `tool_missing` 으로, 있는 서버에서는 `archive_unreadable`
    로 답하는데 **둘 다 예외가 아니고 둘 다 not-ok** 라는 점이 이 시험이 보는 것이다.
    """
    from app.backups.pg_backup import verify_backup

    bad = tmp_path / "bad.dump"
    bad.write_bytes(b"this is definitely not a pg_dump archive" * 10)
    result = verify_backup(bad)
    assert result["ok"] is False  # graceful, no exception
    assert result["reason"]  # 왜 못 믿는지 말한다


def test_login_as_tolerates_precreated_user(client, make_user, login_as):
    """Defect: login_as fixture re-created a user that make_user already made,
    raising ConflictError. Guard: pre-create then login must work."""
    make_user("precreated@goodmit.co.kr", role="operator")
    csrf = login_as("operator", email="precreated@goodmit.co.kr")
    assert csrf


def test_stuck_job_recovery_returns_list_not_count(db, fake_clock):
    """Defect: recover_stuck returned an int but callers iterated it for
    on_failure hooks; changed to return the recovered rows."""
    from datetime import timedelta

    from app.jobs import repository

    now = fake_clock.now()
    repository.enqueue(db, job_type="reg", payload={}, now=now)
    db.commit()
    repository.claim_next(db, now)
    recovered = repository.recover_stuck(db, now=now + timedelta(seconds=4000))
    assert isinstance(recovered, list)
    assert len(recovered) == 1
