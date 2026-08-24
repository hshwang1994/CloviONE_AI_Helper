"""AI 도우미 심화 API — 브리핑 / 스탠드업 / 주간 다이제스트 / 미할당 트리아지.

계획서 Phase 5 의 두 약속을 계약으로 고정한다:

  1. **숫자 먼저, 문장은 나중.** 문장 생성이 꺼져 있어도(기본) 네 엔드포인트 모두 완전한
     숫자를 낸다. 러너를 부르지도 않는다.
  2. **러너가 죽어도 숫자는 그대로.** `?narrate=true` 로 부르고 러너가 타임아웃/연결거부/
     5xx/빈 응답을 내도, 응답의 숫자 필드는 문장을 안 켰을 때와 **완전히 동일**하고
     `narrative.text` 만 None 이 된다. 이 동치를 dict 비교로 직접 확인한다.

  그리고 트리아지는 **제안만** 한다 — `auto_assign: false` 이고 쓰기 라우트가 없다.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import pytest

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = pytest.mark.real_db

from app.board.models import Post
from app.core.security import hash_password
from app.knowledge import blocks
from app.knowledge.models import Document, DocumentVersion, KnowledgeSpace
from app.notifications.models import Notification
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.tickets.models import (
    PROJECT_LINK_MISSING,
    PROJECT_LINK_OK,
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketSyncState,
    join_names,
)
from app.users.models import User
from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.clock import FakeClock
from tests.fakes.notion import FakeNotionTasksDB

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 8, 3, 1, 0, 0)      # UTC → KST 2026-08-03(월) 10:00
TODAY = "2026-08-03"
SYNCED_AT = datetime(2026, 8, 3, 0, 57, 0)
TOKEN_REF = "notion_report_token"

U_ME = "00000000-0000-4000-8000-0000000a0001"
U_MATE = "00000000-0000-4000-8000-0000000a0002"
N_ME = "notion-user-asst-me"
N_MATE = "notion-user-asst-mate"
EMAIL = "asst-me@goodmit.co.kr"
MATE_EMAIL = "asst-mate@goodmit.co.kr"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(rows=[]).install(fake_http)


def _cache(uid, page, *, tid, title, status, due, people, est=None, priority=None,
           project_uid=None):
    """티켓 미러 한 행.

    `project_uid` 는 **소속**이다 (0060 §11). 없으면 그 티켓은 전역 관리자 말고는 아무에게도
    안 보이고, 그러면 도우미가 아무것도 못 읽어 이 파일이 무엇을 재는지 흐려진다.
    """
    return TicketCache(
        id=uid, notion_page_id=page, notion_ticket_number=tid,
        url=f"https://www.notion.so/{page}", title=title, status=status,
        due_date=due, est_wd=est, priority=priority,
        project_ids="", project_names=join_names(["도우미 프로젝트"]),
        project_uid=project_uid,
        project_link=PROJECT_LINK_OK if project_uid else PROJECT_LINK_MISSING,
        assignee_notion_ids=join_names(people),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _doc(db, space_id, *, page_id, title, owner_id, updated_at):
    """다이제스트 시험용 문서 한 건. 정본은 `documents`(S14) — `document_cache`
    (`app.team_docs.models.DocumentCache`)에 심으면 다이제스트가 안 읽는다.
    """
    document = Document(
        space_id=space_id, title=title, doc_type="회의록",
        legacy_page_id=page_id, created_by=owner_id,
    )
    db.add(document)
    db.flush()
    derived = blocks.derive(blocks.from_plain_text(title))
    version = DocumentVersion(
        id=str(uuid.uuid4()), document_id=document.id, version_no=1,
        body=derived.body, body_markdown=derived.markdown, body_text=derived.text,
        author_id=owner_id,
    )
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    document.updated_at = updated_at
    return document


def _seed(db) -> None:
    from app.org.constants import DEFAULT_ORG_ID
    from app.projects.models import Project

    # 티켓이 매달릴 프로젝트. 부서를 안 주므로 **조직 공통**이다 — 조직에 속한 사람이면
    # 누구나 보이는 상태라, 소속 게이트가 아니라 도우미 로직이 검사된다.
    project = Project(name="도우미 프로젝트", org_id=DEFAULT_ORG_ID)
    db.add(project)
    for uid, email, name in ((U_ME, EMAIL, "도우미 나"), (U_MATE, MATE_EMAIL, "도우미 동료")):
        db.add(User(id=uid, email=email, display_name=name, role="user", active=True,
                    # 소속(0060) — 조직 직속. 미지정이면 조직 데이터를 아무것도 못 본다.
                    membership_kind="organization", org_id=DEFAULT_ORG_ID,
                    password_hash=hash_password(DEFAULT_TEST_PASSWORD),
                    must_change_password=False))
    db.flush()
    for uid, nid, email in ((U_ME, N_ME, EMAIL), (U_MATE, N_MATE, MATE_EMAIL)):
        db.add(UserNotionMapping(user_id=uid, notion_user_id=nid, notion_email=email,
                                 status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                                 last_verified_at=SYNCED_AT))
    db.add_all([
        _cache("a-uid-1", "a-1", tid=1, title="오늘 마감", status="진행",
               due=TODAY, people=[N_ME], est=1.0, project_uid=project.id),
        _cache("a-uid-2", "a-2", tid=2, title="지연", status="진행",
               due="2026-07-30", people=[N_ME], est=2.0, project_uid=project.id),
        _cache("a-uid-3", "a-3", tid=3, title="막힘", status="이슈",
               due="2026-08-06", people=[N_ME], project_uid=project.id),
        _cache("a-uid-4", "a-4", tid=4, title="이번 주 완료", status="완료",
               due="2026-08-04", people=[N_ME], est=1.5, project_uid=project.id),
        # 동료는 활성 2건 — 트리아지 후보 정렬에서 '나'(활성 3건)보다 앞서야 한다.
        _cache("a-uid-5", "a-5", tid=5, title="동료 1", status="진행",
               due="2026-08-05", people=[N_MATE], project_uid=project.id),
        _cache("a-uid-6", "a-6", tid=6, title="동료 2", status="진행",
               due="2026-08-07", people=[N_MATE], project_uid=project.id),
        # 미할당 3건 — 지연 > 긴급 > 나머지 순으로 제안돼야 한다.
        _cache("a-uid-7", "a-7", tid=7, title="미할당 보통", status="진행",
               due="2026-08-20", people=[], priority="보통", project_uid=project.id),
        _cache("a-uid-8", "a-8", tid=8, title="미할당 긴급", status="진행",
               due="2026-08-20", people=[], priority="긴급", project_uid=project.id),
        _cache("a-uid-9", "a-9", tid=9, title="미할당 지연", status="진행",
               due="2026-07-20", people=[], priority="낮음", project_uid=project.id),
    ])
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = SYNC_OK
    state.last_run_at = SYNCED_AT
    state.last_success_at = SYNCED_AT
    state.ticket_count = 9
    state.truncated = False
    state.error = None
    db.add(state)
    db.add(Notification(user_id=U_ME, type="ticket_assigned", title="알림", created_at=SYNCED_AT))
    db.add(Post(id="asst-post-1", author_user_id=U_MATE, category="자유", title="이번 주 글",
                body="본문", created_at=SYNCED_AT, updated_at=SYNCED_AT))
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="도우미 공간", slug="asst-space",
        owner_kind="organization",
    )
    db.add(space)
    db.flush()
    _doc(db, space.id, page_id="asst-doc-1", title="이번 주 문서", owner_id=U_MATE,
         updated_at=datetime(2026, 8, 3, 2, 0, 0))
    db.commit()


def _login(client, settings):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    response = client.post("/login", json={"email": EMAIL, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@pytest.fixture()
def asst_client(client, db, settings, notion):
    _seed(db)
    return _login(client, settings)


# ── 문장 생성이 꺼진 기본 상태: 숫자만 나온다 ──────────────────────────────────

def _get(client, path) -> dict:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def test_briefing_gives_the_same_numbers_as_home_today(asst_client):
    briefing = _get(asst_client, "/api/assistant/briefing")
    home = _get(asst_client, "/api/home/today")
    assert briefing["kind"] == "briefing"
    # 브리핑이 홈과 다른 숫자를 말하면 사용자는 둘 중 하나를 거짓말로 받아들인다.
    assert briefing["tickets"] == home["tickets"]
    assert briefing["sprint"] == home["sprint"]
    assert briefing["narrative"] is None      # narrate 를 안 켰으면 블록 자체가 없다


def test_standup_splits_done_plan_blocked_without_any_llm(asst_client, fake_http):
    fake_http.requests.clear()
    body = _get(asst_client, "/api/assistant/standup")
    assert body["kind"] == "standup"
    assert body["author"]["display_name"] == "도우미 나"
    assert body["recently_done"]["count"] == 1             # 창 안 완료 1건
    assert {i["tid"] for i in body["today_plan"]["items"]} == {1, 2}  # 오늘 마감 + 지연
    assert body["blocked"]["count"] == 1
    assert fake_http.requests == []                        # 외부 호출 0회


def test_weekly_digest_reports_mine_team_and_changed_content(asst_client):
    body = _get(asst_client, "/api/assistant/weekly-digest")
    assert body["window"] == {"start": "2026-08-03", "end_exclusive": "2026-08-10"}
    assert body["mine"]["assigned"] == 3 and body["mine"]["done"] == 1
    # 팀 합계는 창 안 티켓 전체 = 내 3건 + 동료 2건. 미할당 3건은 마감이 창 밖이라 안 센다
    # (팀 합계는 티켓 단위 중복 없이 — 담당자별 합과 다른 게 정상이다).
    assert body["team"]["total"] == 5
    assert body["team"]["done"] == 1
    assert [c["name"] for c in body["top_contributors"]][:1] == ["도우미 나"]
    assert body["documents_changed"]["count"] == 1
    assert body["board"]["count"] == 1


def test_weekly_digest_cuts_documents_at_kst_midnight_on_both_sides(asst_client, db):
    """M4 의 **배선** 확인. 순수 함수가 옳아도 여기서 안 부르면 화면은 여전히 틀린다.

    KST 창 [08-03, 08-10) 은 UTC 로 [08-02 15:00, 08-09 15:00) 이다. 예전 코드는 KST 달력일
    문자열('2026-08-03')을 Notion 이 준 UTC 문자열과 그대로 비교했고 위쪽 경계는 아예
    없었다. 그래서 **양쪽 끝**에 표본을 놓는다 - 한쪽만 보면 반쪽만 고치고 통과한다.
    """
    from app.org.constants import DEFAULT_ORG_ID

    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="도우미 경계 공간", slug="asst-space-boundary",
        owner_kind="organization",
    )
    db.add(space)
    db.flush()
    # KST 2026-08-03(월) 06:00 = UTC 08-02 21:00. 예전 비교에서는 사라지던 문서다.
    _doc(db, space.id, page_id="asst-doc-mon", title="월요일 오전 문서", owner_id=U_ME,
         updated_at=datetime(2026, 8, 2, 21, 0, 0))
    # KST 2026-08-10(월) 06:00 = UTC 08-09 21:00. 예전에는 위쪽 경계가 없어 끼어들었다.
    _doc(db, space.id, page_id="asst-doc-next", title="다음 주 문서", owner_id=U_ME,
         updated_at=datetime(2026, 8, 9, 21, 0, 0))
    db.commit()

    changed = _get(asst_client, "/api/assistant/weekly-digest")["documents_changed"]
    titles = {d["title"] for d in changed["items"]}
    assert "월요일 오전 문서" in titles, "KST 월요일 오전 9시간이 다시 사라졌다(M4)"
    assert "다음 주 문서" not in titles, "다음 주 문서가 이번 주에 꼈다"
    assert changed["count"] == 2      # 기존 '이번 주 문서' 1건 + 월요일 오전 1건


# UA-05: weekly_digest_facts used to check only my_state["configured"] before making a
# *second*, independent Notion query (list_period_tickets) for the team/contributors
# section — even when the first query had already come back with ok=False (Notion
# configured but currently failing). That second call's NotionQueryError was unguarded
# and propagated all the way to a 502 for the whole endpoint, wiping out documents_changed
# and board too even though neither has anything to do with Notion being down.
def test_weekly_digest_degrades_team_section_instead_of_502ing_when_notion_is_down(
    asst_client, monkeypatch
):
    from app.core.errors import NotionQueryError
    from app.tickets import service as tickets_service

    def _boom(*args, **kwargs):
        raise NotionQueryError("Notion 다운")

    monkeypatch.setattr(tickets_service, "list_my_tickets", _boom)
    # The bug's second call site — must never be reached once my_state.ok is False.
    monkeypatch.setattr(
        tickets_service,
        "list_period_tickets",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError(
            "list_period_tickets was called even though load_my_tickets already failed"
        )),
    )

    body = _get(asst_client, "/api/assistant/weekly-digest")
    assert body["tickets"]["ok"] is False
    assert body["team"] is None
    assert body["top_contributors"] == []
    # Notion being down must not take documents/board down with it.
    assert body["documents_changed"]["count"] == 1
    assert body["board"]["count"] == 1


def test_triage_suggests_order_and_candidates_but_assigns_nothing(asst_client, db):
    before = {
        row.notion_page_id: row.assignee_notion_ids
        for row in db.query(TicketCache).all()
    }
    body = _get(asst_client, "/api/assistant/triage")
    assert body["auto_assign"] is False
    assert body["total"] == 3
    # 지연 → 긴급 → 보통. 우선순위가 낮아도 지연이 맨 앞이다.
    assert [i["tid"] for i in body["items"]] == [9, 8, 7]
    assert body["items"][0]["overdue"] is True
    # 후보는 활성 담당이 적은 순 — 동료(2건)가 나(3건)보다 앞이다.
    assert [c["display_name"] for c in body["candidates"]][:2] == ["도우미 동료", "도우미 나"]
    assert body["candidates"][0]["active_tickets"] == 2
    db.expire_all()
    after = {
        row.notion_page_id: row.assignee_notion_ids
        for row in db.query(TicketCache).all()
    }
    assert after == before, "트리아지가 담당자를 건드렸다 — '제안만' 계약 위반"


def test_narrate_flag_off_by_default_never_calls_the_runner(asst_client, fake_http):
    fake_http.requests.clear()
    body = _get(asst_client, "/api/assistant/briefing?narrate=true")
    # 기능 플래그(assistant_narrative_enabled)가 기본 false 라 호출 자체가 나가지 않는다.
    assert body["narrative"]["enabled"] is False
    assert body["narrative"]["text"] is None
    assert fake_http.requests == []


def test_assistant_requires_authentication(client):
    for path in ("/briefing", "/standup", "/weekly-digest", "/triage"):
        assert client.get("/api/assistant" + path).status_code == 401


# ── 문장 생성을 켠 상태: **모델이 죽어도 숫자는 살아남는다** ──────────────────
#
# S11 이전에는 이 절이 러너 HTTP(`assistant_runner_url`)를 가짜로 세웠다. 지금은 요약
# 문장이 `Gateway.generate()` 를 지나므로(D-266) 가짜를 세울 자리도 Gateway 다. 지키는
# 것은 한 글자도 안 바뀌었다: **숫자는 언제나 완전하고, 빠지는 것은 문장뿐이다.**


class ScriptedGenerate:
    """넘어온 (system, user) 쌍을 그대로 들고 있는다. 상태는 시험이 정한다."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, *, status=None, text="요약 문장입니다."):
        from app.ai.gateway import contract

        self._status = status or contract.STATUS_OK
        self._text = text
        self.calls: list[tuple[str, str]] = []

    def capability(self):
        from app.ai.gateway import contract

        if self._status != contract.STATUS_OK:
            return contract.unavailable(contract.CAP_GENERATE, self._status, model=self.model)
        return contract.available(contract.CAP_GENERATE, model=self.model)

    def generate(self, *, system: str, user: str):
        from app.ai.gateway import contract

        self.calls.append((system, user))
        return contract.GenerateResult(
            status=self._status, model=self.model,
            text=self._text if self._status == contract.STATUS_OK else None,
        )


def _use(app, adapter):
    """이 앱의 Gateway 를 그 Adapter 하나짜리로 바꾼다."""
    from app.ai.gateway import contract

    app.state.ai_gateway = contract.Gateway(enabled=True, generate_adapter=adapter)
    return adapter


def _narrative_app(db_url, tmp_path, fake_clock, fake_http):
    """assistant_narrative_enabled=true 로 켠 별도 앱."""
    from app.core.config import Settings
    from app.main import create_app

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    flags = json.loads((cfg / "feature-flags.json").read_text(encoding="utf-8"))
    flags["assistant_narrative_enabled"] = True
    (cfg / "feature-flags.json").write_text(json.dumps(flags), encoding="utf-8")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    (secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as session:
        _seed(session)
    return app, settings


@pytest.fixture()
def narrative_client(db_url, tmp_path, fake_clock, fake_http, notion):
    from fastapi.testclient import TestClient

    app, settings = _narrative_app(db_url, tmp_path, fake_clock, fake_http)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post("/login", json={"email": EMAIL, "password": DEFAULT_TEST_PASSWORD})
        assert response.status_code == 200, response.text
        test_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield test_client, app


def _facts_only(body: dict) -> dict:
    return {k: v for k, v in body.items() if k != "narrative"}


def test_narrative_is_added_when_the_model_answers(narrative_client):
    client, app = narrative_client
    _use(app, ScriptedGenerate(text="오늘 마감 1건, 지연 1건입니다."))
    body = _get(client, "/api/assistant/briefing?narrate=true")
    assert body["narrative"]["enabled"] is True
    assert body["narrative"]["text"] == "오늘 마감 1건, 지연 1건입니다."
    assert body["narrative"]["error"] is None
    assert body["tickets"]["due_today"]["count"] == 1


@pytest.mark.parametrize("break_model", ["timeout", "busy", "not_logged_in", "empty"])
def test_numbers_survive_every_model_failure_mode(narrative_client, break_model):
    """계획서 Phase 5: '러너가 죽어도 숫자는 그대로 보여야 한다(문장만 빠진다).'

    문장을 끄고 받은 응답과 모델이 죽은 채로 받은 응답의 **사실 부분이 바이트 동일**한지
    dict 비교로 직접 확인한다. 한 필드라도 사라지면 여기서 깨진다.
    """
    from app.ai.gateway import contract

    client, app = narrative_client
    _use(app, ScriptedGenerate())
    baseline = _facts_only(_get(client, "/api/assistant/briefing"))

    status = {
        "timeout": contract.STATUS_TIMEOUT,
        "busy": contract.STATUS_BUSY,
        "not_logged_in": contract.STATUS_NOT_LOGGED_IN,
        "empty": contract.STATUS_EMPTY,
    }[break_model]
    _use(app, ScriptedGenerate(status=status))

    body = _get(client, "/api/assistant/briefing?narrate=true")
    assert _facts_only(body) == baseline               # 숫자는 한 글자도 안 변했다
    assert body["narrative"]["enabled"] is True
    assert body["narrative"]["text"] is None
    assert body["narrative"]["error"]                  # 왜 문장이 없는지 화면이 말할 수 있다


def test_an_unconfigured_model_reports_that_not_a_generic_failure(narrative_client):
    """「아직 설정 안 됨」과 「지연/실패」는 운영자가 할 일이 다르다. 예전에는 러너 토큰
    파일이 없는 상태가 애매한 실패 문구로 뭉개졌다 — 지금은 Gateway 의 상태 어휘가
    그 구별을 들고 온다."""
    from app.ai.gateway import contract

    client, app = narrative_client
    # 어댑터가 아예 없는 앱 — 모델을 안 넣은 설치다.
    app.state.ai_gateway = contract.Gateway(enabled=True, generate_adapter=None)
    body = _get(client, "/api/assistant/briefing?narrate=true")
    assert body["narrative"]["enabled"] is True
    assert body["narrative"]["text"] is None
    assert "설정되지 않았습니다" in body["narrative"]["error"]


def test_model_output_is_not_trusted_verbatim(narrative_client):
    """모델 출력 불신(§11): 제어문자는 버리고 길이는 자른다."""
    from app.assistant.narrate import MAX_TEXT_CHARS

    esc, nul = chr(27), chr(0)
    client, app = narrative_client
    _use(app, ScriptedGenerate(text=f"머리{esc}[31m글{nul}자" + "가" * (MAX_TEXT_CHARS + 500)))
    out = _get(client, "/api/assistant/briefing?narrate=true")["narrative"]["text"]
    assert esc not in out and nul not in out
    assert len(out) == MAX_TEXT_CHARS


def test_the_model_receives_only_precomputed_facts(narrative_client):
    """모델은 숫자를 다시 세지 않는다 — 우리가 계산한 사실만 넘어간다.

    그리고 그 사실은 **`data` 로** 간다(D-202) — 시스템 쪽에는 우리 문장만 있다.
    """
    client, app = narrative_client
    adapter = _use(app, ScriptedGenerate())
    _get(client, "/api/assistant/standup?narrate=true")

    assert len(adapter.calls) == 1
    system, user = adapter.calls[0]
    assert '"kind": "standup"' in user
    assert '"blocked"' in user
    # 원본 Notion 사용자 id 는 절대 나가지 않는다(§12.3).
    assert N_ME not in user and N_ME not in system
    # 사실은 데이터 쪽에만 있다 — 지시문 자리에 섞이면 그 값이 지시가 된다.
    assert '"blocked"' not in system


def test_narrate_is_rate_limited_per_user(narrative_client):
    client, app = narrative_client
    _use(app, ScriptedGenerate())
    statuses = [client.get("/api/assistant/briefing?narrate=true").status_code for _ in range(9)]
    assert 429 in statuses, "문장 생성에 레이트리밋이 걸려 있지 않다"
    # 문장을 끄면 리미터를 지나지 않으므로 계속 200 이다(숫자는 언제나 볼 수 있어야 한다).
    assert client.get("/api/assistant/briefing").status_code == 200
