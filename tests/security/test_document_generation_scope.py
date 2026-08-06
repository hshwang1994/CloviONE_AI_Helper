"""문서 자동 생성 이력의 **목록·단건·재시도**가 같은 범위를 지킨다 (§0-A).

`scripts/check_scope_gates.py` 가 `GET /api/admin/documents/{id}` 와
`POST /api/admin/documents/{id}/retry` 를 잡았다.

## ⚠️ 목록도 범위를 걸지 않고 있었다

과제 지시는 "목록은 범위를 거니 단건·재시도만 맞춰라" 였지만, 코드를 읽어 보니
`list_generations` 는 `select(DocumentGeneration)` 그대로였다. 검사가 이 모듈을 '범위 있는
모듈' 로 분류한 것은 `generate` 핸들러 본문에 `org_id=` 라는 글자가 있어서지(정적 검사의
한계 — 스크립트 docstring 이 스스로 적어 둔 그 한계다) 목록이 실제로 판정을 지나서가
아니다. 그래서 단건만 막으면 **판정이 두 벌이 되는 방향이 뒤집힐 뿐**이다: 목록에는
남의 팀 이력이 요청자 이메일과 함께 그대로 나오는데 상세만 404 가 된다.
이 파일은 **세 경로를 한 판정에 묶는다.**

## 무엇이 새는가

* **목록·상세** — 이력에는 요청자(라우터가 이메일까지 해석해 붙인다)와 **요청 내용**
  (`config`: 어떤 Notion DB 를 어떤 필터로 뽑아 어디에 쓰는지, 프롬프트 이름, 기간)이 실린다.
* **재시도** — 읽기 유출이 아니라 **쓰기 실행**이다. 실패한 이력을 다시 큐에 올리면 워커가
  러너(n8n)를 다시 불러 남의 팀 문서를 다시 만들고, 승인이 없는 대상이면 발행까지 간다.
  그래서 404 를 돌려주는 것만으로는 부족하고 **아무 일도 일어나지 않았음**(상태 그대로,
  잡이 큐에 없음)까지 확인한다.

## 요청자 없는 이력(`requested_by IS NULL`)은 남는다

컬럼이 nullable 이고 러너 핸들러가 그런 행을 `requester.name="system"` 으로 다룬다
(`app/jobs/handlers/document_generate.py::_requester`). 소유자 없는 자동 생성까지 가리면
부서 관리자가 자기 범위에 걸린 자동 처리 실패를 못 본다 — 잡 큐와 같은 규칙이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.security

AT = datetime(2026, 8, 1, 9, 0, 0)

# 남의 팀 이력의 요청 내용 — 응답 본문에 이 문자열이 새는지도 함께 본다.
THEIR_SECRET_TARGET = "notion-page-남의팀-실적"


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리 팀만 관리하는 관리자 + 생성 이력 넷."""
    from app.documents.models import (
        MODE_PREVIEW_THEN_APPROVE,
        STATUS_FAILED,
        STATUS_PREVIEW_READY,
        DocumentGeneration,
    )
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user("docgen-mate@goodmit.co.kr", role="user", display_name="동료")
    victim = make_user("docgen-victim@goodmit.co.kr", role="user", display_name="남")
    boss = make_user("docgen-boss@goodmit.co.kr", role="admin", display_name="팀관리자")
    mate.department_id = mine.id
    victim.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    def _gen(key: str, requested_by: str | None, status: str, target: str) -> DocumentGeneration:
        return DocumentGeneration(
            workflow_id="wf-1",
            mode=MODE_PREVIEW_THEN_APPROVE,
            idempotency_key=f"docscope:{key}",
            status=status,
            config_json=f'{{"target_parent_page": "{target}", "period": "2026-W31"}}',
            requested_by=requested_by,
            error_message="n8n 500",
            created_at=AT,
            updated_at=AT,
        )

    rows = {
        # 남의 팀 사람이 요청한 실패 이력 — 재시도하면 러너가 다시 돌아 문서가 다시 만들어진다.
        "theirs_failed": _gen("theirs-failed", victim.id, STATUS_FAILED, THEIR_SECRET_TARGET),
        # 재시도 대상이 아닌 상태(원래 409) — 범위 밖이면 409 보다 404 가 **먼저** 나와야 한다.
        "theirs_ready": _gen("theirs-ready", victim.id, STATUS_PREVIEW_READY, THEIR_SECRET_TARGET),
        "mine_failed": _gen("mine-failed", mate.id, STATUS_FAILED, "notion-page-우리팀"),
        # 요청자 없는 자동 생성 — 가리면 자기 범위의 자동 처리 실패를 못 본다.
        "system": _gen("system", None, STATUS_FAILED, "notion-page-정기보고"),
    }
    db.add_all(list(rows.values()))
    db.commit()
    return {key: row.id for key, row in rows.items()}


def _boss(login_as):
    return {"X-CSRF-Token": login_as("admin", email="docgen-boss@goodmit.co.kr")}


def _status(db, generation_id):
    from app.documents.models import DocumentGeneration

    db.expire_all()
    return db.get(DocumentGeneration, generation_id).status


def _docgen_job(db, generation_id):
    """이 이력을 실제로 실행하는 잡. 재시도가 '진짜로' 일어났는지의 증거다."""
    from sqlalchemy import select

    from app.jobs.models import Job

    db.expire_all()
    return db.execute(
        select(Job).where(Job.idempotency_key == f"docgen:{generation_id}")
    ).scalar_one_or_none()


def _list_ids(client, headers):
    body = client.get("/api/admin/documents", headers=headers).json()
    return {item["id"] for item in body["items"]}


# ── 범위 밖은 404 ────────────────────────────────────────────────────────────


def test_a_scoped_admin_cannot_read_another_teams_generation(client, login_as, world):
    """상세에는 요청 내용(config)과 실패 사유가 실린다 — 목록에서 가릴 것이 id 로 열린다."""
    r = client.get(f"/api/admin/documents/{world['theirs_failed']}", headers=_boss(login_as))
    assert r.status_code == 404, f"남의 팀 생성 이력 상세가 열린다: {r.status_code} {r.text}"
    assert THEIR_SECRET_TARGET not in r.text, "404 인데 응답 본문에 요청 내용이 남아 있다"


def test_the_list_hides_it_too(client, login_as, world):
    """목록은 요청자 **이메일까지 해석해** 붙인다 — 상세만 막으면 앞문이 열린 채다."""
    headers = _boss(login_as)
    body = client.get("/api/admin/documents", headers=headers).json()
    assert world["theirs_failed"] not in {i["id"] for i in body["items"]}, (
        "남의 팀 생성 이력이 목록에 그대로 나온다"
    )
    assert "docgen-victim@goodmit.co.kr" not in client.get(
        "/api/admin/documents", headers=headers
    ).text, "남의 팀 요청자 이메일이 목록으로 새어 나간다"


def test_the_total_matches_what_is_shown(client, login_as, world):
    """"총 4건" 이라 해 놓고 2건만 주면 사용자는 없는 것을 찾아 페이지를 넘긴다."""
    body = client.get("/api/admin/documents", headers=_boss(login_as)).json()
    assert body["total"] == len(body["items"])


def test_a_scoped_admin_cannot_rerun_another_teams_generation(client, login_as, db, world):
    """재시도는 읽기가 아니라 **쓰기 실행**이다 — 남의 팀 문서가 다시 만들어지고 발행된다."""
    gen_id = world["theirs_failed"]
    r = client.post(f"/api/admin/documents/{gen_id}/retry", headers=_boss(login_as))
    assert r.status_code == 404, f"남의 팀 생성 이력을 재시도할 수 있다: {r.status_code} {r.text}"
    # 404 를 돌려주고도 실제로 재실행됐는지 — 상태와 잡 큐 **양쪽**을 본다.
    assert _status(db, gen_id) == "failed", (
        "404 를 돌려주고도 이력이 pending 으로 되돌아갔다 — 워커가 곧 집어간다"
    )
    assert _docgen_job(db, gen_id) is None, (
        "404 를 돌려주고도 러너 호출 잡이 큐에 들어갔다 — 남의 팀 문서가 다시 만들어진다"
    )


def test_an_out_of_scope_generation_is_404_before_409(client, login_as, world):
    """상태 충돌(409)이 먼저 나오면 그 id 의 **존재와 상태**가 새어 나간다.

    실패 상태가 아닌 이력에 재시도를 걸면 원래 409 다 — 범위 밖이면 그 전에 404 여야 한다.
    """
    r = client.post(f"/api/admin/documents/{world['theirs_ready']}/retry", headers=_boss(login_as))
    assert r.status_code == 404, (
        f"409 로 답해 범위 밖 이력의 존재와 상태를 알려 준다: {r.status_code} {r.text}"
    )


# ── 오탐 방지: 정상 경로는 여전히 된다 ────────────────────────────────────────


def test_the_detail_and_the_list_agree_on_my_own_team(client, login_as, world):
    """자기 범위 이력이 막히면 그건 보안이 아니라 기능 고장이다."""
    headers = _boss(login_as)
    assert world["mine_failed"] in _list_ids(client, headers), "자기 팀 이력이 목록에서 사라졌다"
    r = client.get(f"/api/admin/documents/{world['mine_failed']}", headers=headers)
    assert r.status_code == 200, f"자기 팀 이력 상세를 못 본다: {r.status_code} {r.text}"


def test_a_scoped_admin_can_still_retry_their_own_team(client, login_as, db, world):
    """자기 범위의 재시도는 그대로 돼야 한다 — 막으면 재시도 기능 자체가 죽는다."""
    gen_id = world["mine_failed"]
    r = client.post(f"/api/admin/documents/{gen_id}/retry", headers=_boss(login_as))
    assert r.status_code == 202, f"자기 팀 이력을 재시도할 수 없다: {r.status_code} {r.text}"
    assert _status(db, gen_id) == "pending"
    assert _docgen_job(db, gen_id) is not None, "202 인데 러너 호출 잡이 큐에 없다"


def test_system_generations_stay_visible(client, login_as, world):
    """요청자 없는 자동 생성까지 가리면 자기 범위의 자동 처리 실패를 못 본다(잡 큐와 같은 규칙)."""
    headers = _boss(login_as)
    assert world["system"] in _list_ids(client, headers), "목록에서 시스템 생성 이력이 사라졌다"
    r = client.get(f"/api/admin/documents/{world['system']}", headers=headers)
    assert r.status_code == 200, (
        f"목록엔 보이는데 상세는 404 다 — 판정이 두 벌이다: {r.status_code} {r.text}"
    )


def test_a_global_admin_still_sees_and_operates_everything(client, login_as, db, world):
    """전역 관리자까지 좁히면 운영이 멈춘다."""
    headers = {"X-CSRF-Token": login_as("system_admin")}
    assert _list_ids(client, headers) >= set(world.values()), "전역 관리자 목록에서 이력이 빠졌다"
    assert client.get(
        f"/api/admin/documents/{world['theirs_failed']}", headers=headers
    ).status_code == 200
    r = client.post(f"/api/admin/documents/{world['theirs_failed']}/retry", headers=headers)
    assert r.status_code == 202, f"전역 관리자가 재시도를 못 한다: {r.status_code} {r.text}"
    assert _status(db, world["theirs_failed"]) == "pending"
