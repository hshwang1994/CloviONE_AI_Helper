"""사용자 대량 작업 + CSV 가져오기/내보내기 (Phase 6).

여기서 못박는 것:
  * **부분 실패를 숨기지 않는다** — 200명 중 3명이 막히면 197명은 처리하고 3명은 사유와 함께
    돌려준다(전부 롤백하면 관리자는 197번을 손으로 다시 눌러야 한다).
  * **범위 밖 id 는 '찾을 수 없음'** — 단건 조회가 404 를 주는 것과 같은 이유로, 대량 작업의
    결과에서도 존재를 알려 주지 않는다.
  * **CSV 인젝션** — `=`/`+`/`-`/`@` 로 시작하는 셀은 엑셀이 수식으로 실행한다. 내보낸 파일이
    공격 경로가 되지 않게 문자열로 고정한다.
  * **가져오기의 기본은 미리보기** — 확인 없이 100명이 생기지 않는다.
"""

from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import select

from app.org.models import Department, JobTitle
from app.users.models import User
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(client, make_user):
    make_user(email="boss@goodmit.co.kr", role="system_admin", display_name="관리자")
    response = client.post(
        "/login", json={"email": "boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.fixture()
def org(db):
    db.add(Department(id="d-dev", name="개발팀"))
    db.add(JobTitle(id="t-lead", name="팀장"))
    db.commit()
    return {"dept": "d-dev", "title": "t-lead"}


@pytest.fixture()
def crowd(db, make_user):
    users = [
        make_user(email=f"m{i}@goodmit.co.kr", role="user", display_name=f"사람{i}")
        for i in range(3)
    ]
    db.commit()
    return [u.id for u in users]


def _bulk(client, csrf, **body):
    return client.post(
        "/api/admin/users/bulk/apply", json=body, headers={"X-CSRF-Token": csrf}
    )


# ── 대량 작업 ─────────────────────────────────────────────────────────────────

def test_bulk_disable_applies_to_every_selected_user(client, admin, crowd, db):
    response = _bulk(client, admin, user_ids=crowd, action="disable")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["applied"]) == 3 and body["failed"] == []

    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert [db.get(User, uid).active for uid in crowd] == [False, False, False]


def test_already_in_that_state_is_reported_as_unchanged_not_as_success_noise(
    client, admin, crowd
):
    _bulk(client, admin, user_ids=crowd, action="disable")
    body = _bulk(client, admin, user_ids=crowd, action="disable").json()
    assert [row["changed"] for row in body["applied"]] == [False, False, False]


def test_a_blocked_user_does_not_stop_the_rest(client, admin, crowd, db):
    """마지막 system_admin 은 비활성화가 막힌다 — 그 한 명 때문에 나머지가 통째로 롤백되면 안 된다."""
    me = db.execute(select(User).where(User.email == "boss@goodmit.co.kr")).scalar_one()
    body = _bulk(client, admin, user_ids=[*crowd, me.id], action="disable").json()

    assert len(body["applied"]) == 3
    assert [f["id"] for f in body["failed"]] == [me.id]
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(User, crowd[0]).active is False


def test_bulk_set_department_moves_everyone(client, admin, crowd, org, db):
    response = _bulk(
        client, admin, user_ids=crowd, action="set_department", value=org["dept"]
    )
    assert response.status_code == 200, response.text
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert {db.get(User, uid).department_id for uid in crowd} == {org["dept"]}


def test_unknown_action_is_rejected_before_anything_happens(client, admin, crowd, db):
    response = _bulk(client, admin, user_ids=crowd, action="delete_everything")
    # ValidationAppError = 422 (app/core/errors.py) — 이 저장소의 검증 실패 규약.
    assert response.status_code == 422, response.text
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.get(User, crowd[0]).active is True


def test_bulk_writes_one_audit_row_per_changed_user(client, admin, crowd, db):
    from app.audit.models import AuditLog

    _bulk(client, admin, user_ids=crowd, action="disable")
    rows = db.execute(
        select(AuditLog).where(AuditLog.action == "user.bulk_disable")
    ).scalars().all()
    # 한 줄로 뭉치면 "누가 언제 이 사람을 비활성화했나"를 대상 id 로 조회할 수 없다.
    assert {r.object_id for r in rows} == set(crowd)


# ── CSV 내보내기 ──────────────────────────────────────────────────────────────

def test_export_returns_a_csv_attachment_with_a_bom(client, admin, crowd):
    response = client.get("/api/admin/users/export/csv")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    # BOM 이 없으면 국내 환경의 엑셀이 CP949 로 읽어 한글이 전부 깨진다.
    assert response.text.startswith("﻿")


def test_export_respects_the_same_filters_as_the_list(client, admin, crowd):
    """필터를 걸고 내보냈는데 전 직원이 담기면, 그 사실은 파일을 열어 보기 전까지 아무도 모른다."""
    listed = client.get("/api/admin/users?role=system_admin").json()
    rows = list(csv.reader(io.StringIO(client.get(
        "/api/admin/users/export/csv?role=system_admin"
    ).text.lstrip("﻿"))))
    assert len(rows) - 1 == listed["total"] == 1
    assert rows[1][0] == "boss@goodmit.co.kr"


def test_export_neutralises_spreadsheet_formulas(client, admin, make_user, db):
    make_user(email="evil@goodmit.co.kr", role="user", display_name='=HYPERLINK("x")')
    db.commit()
    text = client.get("/api/admin/users/export/csv").text
    assert '"\'=HYPERLINK(""x"")"' in text, "수식이 그대로 나갔다"


def test_export_never_contains_a_password_hash(client, admin, crowd, db):
    text = client.get("/api/admin/users/export/csv").text
    hashes = db.execute(select(User.password_hash)).scalars().all()
    for value in hashes:
        assert value not in text


# ── CSV 가져오기 ──────────────────────────────────────────────────────────────

CSV_OK = (
    "이메일,이름,역할,부서,직책\n"
    "new1@goodmit.co.kr,신입1,user,개발팀,팀장\n"
    "new2@goodmit.co.kr,신입2,operator,,\n"
)


def _import(client, csrf, text, *, dry_run=True):
    return client.post(
        "/api/admin/users/import/csv",
        json={"csv_text": text, "dry_run": dry_run},
        headers={"X-CSRF-Token": csrf},
    )


def test_import_defaults_to_a_dry_run_and_creates_nothing(client, admin, org, db):
    body = _import(client, admin, CSV_OK).json()
    assert body["dry_run"] is True
    assert body["created"] == 2
    assert [r["status"] for r in body["results"]] == ["ready", "ready"]
    assert db.execute(
        select(User).where(User.email == "new1@goodmit.co.kr")
    ).scalar_one_or_none() is None


def test_import_applies_when_asked(client, admin, org, db):
    body = _import(client, admin, CSV_OK, dry_run=False).json()
    assert body["created"] == 2, body

    created = db.execute(
        select(User).where(User.email == "new1@goodmit.co.kr")
    ).scalar_one()
    assert created.display_name == "신입1"
    assert created.department_id == org["dept"] and created.title_id == org["title"]
    # 가져오기로 만든 계정은 임시 비밀번호 + 첫 로그인 변경 강제다.
    assert created.must_change_password is True


def test_existing_emails_are_skipped_not_overwritten(client, admin, org, db, make_user):
    make_user(email="new1@goodmit.co.kr", role="user", display_name="원래 이름")
    db.commit()
    body = _import(client, admin, CSV_OK, dry_run=False).json()

    statuses = {r["email"]: r["status"] for r in body["results"]}
    assert statuses["new1@goodmit.co.kr"] == "skipped"
    db.commit()  # 스냅샷을 새로 뜬다 — expire_all()만으로는 이미 연 트랜잭션의 스냅샷이 안 바뀐다
    db.expire_all()
    assert db.execute(
        select(User).where(User.email == "new1@goodmit.co.kr")
    ).scalar_one().display_name == "원래 이름"


def test_a_bad_row_does_not_reject_the_whole_file(client, admin, org):
    text = CSV_OK + "broken@goodmit.co.kr,없는부서사람,user,없는부서,\n"
    body = _import(client, admin, text).json()
    assert body["created"] == 2 and body["failed"] == 1
    bad = [r for r in body["results"] if r["email"].startswith("broken")][0]
    assert "부서" in bad["message"]


def test_missing_required_columns_is_a_clear_error(client, admin):
    response = _import(client, admin, "foo,bar\n1,2\n")
    assert response.status_code == 422, response.text
    assert "이메일" in response.json()["error"]["message"]


def test_duplicate_emails_inside_one_file_are_skipped(client, admin):
    text = (
        "email,display_name\n"
        "dup@goodmit.co.kr,하나\n"
        "dup@goodmit.co.kr,둘\n"
    )
    body = _import(client, admin, text).json()
    assert [r["status"] for r in body["results"]] == ["ready", "skipped"]


# ── 미리보기와 적용은 같은 검증을 쓴다 (users-03 / users-04 / xb-05) ──────────
#
# 상한을 넘는 값 한 줄이 있으면 미리보기는 「추가 예정」이라고 말하고 적용은 500 을 내며
# **파일 전체가 롤백**됐다(DB 컬럼 길이는 스키마 밖이라 아무도 안 보고 있었다). 이메일 형태
# 검사도 단건 생성(pydantic)에만 있어서, 단건이 422 로 막는 주소가 CSV 로는 계정이 됐다.
# 두 경로가 `app/users/schemas.py` 의 같은 규칙을 쓰게 하고, 나쁜 줄만 실패로 보고한다.

def test_a_too_long_name_fails_only_that_row(client, admin, db):
    from app.users.schemas import DISPLAY_NAME_MAX_LENGTH

    text = (
        "이메일,이름,역할\n"
        "csvok1@goodmit.co.kr,정상1,user\n"
        f"csvlong@goodmit.co.kr,{'가' * (DISPLAY_NAME_MAX_LENGTH + 1)},user\n"
        "csvok2@goodmit.co.kr,정상2,user\n"
    )

    preview = _import(client, admin, text)
    assert preview.status_code == 200, preview.text
    assert [r["status"] for r in preview.json()["results"]] == ["ready", "failed", "ready"]

    applied = _import(client, admin, text, dry_run=False)
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["created"] == 2 and body["failed"] == 1
    assert [r["status"] for r in body["results"]] == ["created", "failed", "created"]
    assert str(DISPLAY_NAME_MAX_LENGTH) in body["results"][1]["message"]

    # 정상 두 줄은 **실제로 남아야** 한다 — 예전에는 요청 예외로 함께 사라졌다.
    db.commit()
    db.expire_all()
    emails = set(db.execute(select(User.email)).scalars().all())
    assert {"csvok1@goodmit.co.kr", "csvok2@goodmit.co.kr"} <= emails
    assert "csvlong@goodmit.co.kr" not in emails


def test_a_too_long_email_fails_only_that_row(client, admin, db):
    from app.users.schemas import EMAIL_MAX_LENGTH

    long_email = "e" * (EMAIL_MAX_LENGTH + 1) + "@goodmit.co.kr"
    text = (
        "이메일,이름,역할\n"
        "csvok3@goodmit.co.kr,정상3,user\n"
        f"{long_email},긴메일,user\n"
    )
    body = _import(client, admin, text, dry_run=False).json()
    assert body["created"] == 1 and body["failed"] == 1
    assert str(EMAIL_MAX_LENGTH) in body["results"][1]["message"]

    db.commit()
    db.expire_all()
    assert db.execute(
        select(User).where(User.email == "csvok3@goodmit.co.kr")
    ).scalar_one_or_none() is not None


def test_an_email_shape_the_single_form_refuses_is_refused_here_too(client, admin, db):
    """단건 생성은 422 로 막는 주소다 — 같은 규칙을 CSV 도 써야 두 문이 하나가 된다.

    `validate_company_email` 은 마지막 '@' 기준으로 도메인만 보므로 "a@b@회사.com" 을
    통과시킨다. 정확히 하나의 '@' 를 요구하는 형태 검사가 그 틈을 막는 자리다.
    """
    single = client.post(
        "/api/admin/users",
        json={"email": "two@at@goodmit.co.kr", "display_name": "투앳", "role": "user"},
        headers={"X-CSRF-Token": admin},
    )
    assert single.status_code == 422, single.text

    text = (
        "이메일,이름,역할\n"
        "two@at@goodmit.co.kr,투앳,user\n"
        "notanemail,노앳,user\n"
        "csvok4@goodmit.co.kr,정상4,user\n"
    )
    body = _import(client, admin, text, dry_run=False).json()
    assert [r["status"] for r in body["results"]] == ["failed", "failed", "created"]
    assert body["results"][0]["message"] == "이메일 형식이 올바르지 않습니다."

    db.commit()
    db.expire_all()
    emails = set(db.execute(select(User.email)).scalars().all())
    assert "two@at@goodmit.co.kr" not in emails
    assert "notanemail" not in emails
    assert "csvok4@goodmit.co.kr" in emails


def test_an_oversized_cell_is_a_validation_error_not_a_crash(client, admin):
    """`csv` 모듈은 한 칸이 131072자를 넘으면 `_csv.Error` 를 던진다 — 그대로 두면 500 이라
    붙여 넣은 사람은 자기 파일의 어디가 문제인지 알 수 없다."""
    import csv as csv_module

    huge = "x" * (csv_module.field_size_limit() + 1)
    r = _import(client, admin, f"email,display_name\n{huge}@goodmit.co.kr,Big\n")
    assert r.status_code == 422, r.text
    assert "CSV" in r.json()["error"]["message"]


def test_a_good_file_still_imports(client, admin, org, db):
    """오탐 방지 — 검증을 넣었다고 정상 파일이 막히면 안 된다."""
    body = _import(client, admin, CSV_OK, dry_run=False).json()
    assert body["created"] == 2 and body["failed"] == 0


# ── 일괄 작업: 보관된 계정과 실패 건의 신원 (xb-14 / users-06) ────────────────

def test_bulk_actions_skip_an_archived_user(client, admin, crowd, org, db):
    """화면이 편집 동작을 숨긴 보관 행이 일괄 작업으로는 그대로 바뀌었다 — 단건 경로와 같은
    판정(404)을 하고, 일괄에서는 실패 건으로 보고한다."""
    victim = crowd[0]
    assert client.post(
        f"/api/admin/users/{victim}/archive", headers={"X-CSRF-Token": admin}
    ).status_code == 200

    body = _bulk(
        client, admin, user_ids=[victim], action="set_department", value=org["dept"]
    ).json()
    assert body["applied"] == []
    assert [f["id"] for f in body["failed"]] == [victim]
    assert body["failed"][0]["error"] == "사용자를 찾을 수 없습니다."
    # 404 는 존재를 숨기는 답이다 — 그 줄에 이름·이메일을 실으면 가린 것이 다시 새 나간다.
    assert "email" not in body["failed"][0]

    db.commit()
    db.expire_all()
    assert db.get(User, victim).department_id is None

    assert _bulk(client, admin, user_ids=[victim], action="enable").json()["failed"]
    assert _bulk(client, admin, user_ids=[victim], action="disable").json()["failed"]


def test_bulk_unarchive_still_finds_the_archived_user(client, admin, crowd, db):
    """오탐 방지 — 복구는 보관된 행이 대상이다. 여기까지 막으면 일괄 복구가 사라진다."""
    victim = crowd[0]
    client.post(f"/api/admin/users/{victim}/archive", headers={"X-CSRF-Token": admin})

    body = _bulk(client, admin, user_ids=[victim], action="unarchive").json()
    assert body["failed"] == []
    assert [row["changed"] for row in body["applied"]] == [True]

    db.commit()
    db.expire_all()
    assert db.get(User, victim).archived_at is None


def test_a_failed_row_says_who_it_was(client, admin, crowd, db):
    """토스트가 「2명 실패」까지만 말할 수 있으면 관리자는 40명 중 어느 둘이 남았는지 알
    방법이 없다 — 실패 건에도 이름과 이메일을 싣는다(CSV 결과표가 이미 그렇게 한다)."""
    me = db.execute(select(User).where(User.email == "boss@goodmit.co.kr")).scalar_one()
    body = _bulk(client, admin, user_ids=[*crowd, me.id], action="disable").json()

    assert [f["id"] for f in body["failed"]] == [me.id]
    row = body["failed"][0]
    assert row["email"] == "boss@goodmit.co.kr"
    assert row["display_name"] == "관리자"
    assert row["error"] == "본인 계정은 비활성화할 수 없습니다."
