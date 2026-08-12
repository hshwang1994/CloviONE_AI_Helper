"""최초 실행 셋업 체크리스트 (9-3, P3).

## 이 파일이 막는 것

설치가 끝나고 관리자가 로그인해도 **그다음이 없었다.** 조직·Notion·매핑·LLM·연동을 전부
서버 파일을 고치고 재시작해야 했고, 무엇이 남았는지 화면 어디에도 없었다. 화면은 그냥 빈
목록을 보여 주고 운영자는 "연결은 됐는데 안 된다" 로 읽는다.

여기서 못박는 성질은 다섯이다.

  ① **"안 됨" 과 "확인 불가" 를 합치지 않는다.** 전자는 사람이 할 일이고 후자는 물어볼
     일이다. 둘을 하나로 뭉개면 화면은 "안 됨" 이라 말하면서 정작 사람이 할 수 있는 일이
     없는 항목(TLS 를 앞단 프록시가 끊는 설치)을 빨갛게 세운다.
  ② **안내 순서는 의존 순서다.** 조직 → Notion → 매핑 → LLM → 연동. 앞이 안 됐는데 뒤를
     물으면 사용자는 막힌 이유를 모른다. 그래서 막힌 항목은 **무엇 때문에 막혔는지**를
     스스로 말해야 한다.
  ③ **설정을 하나 채우면 그 항목만 바뀐다.** 판정이 서로 새면 부서 하나 만들었는데 Notion
     항목이 초록으로 변한다 - 그러면 아무도 이 화면을 안 믿는다.
  ④ **끝난 뒤에도 남은 항목이 계속 보인다.** 한 번 닫으면 다시 못 보는 마법사는 설정을
     미룬 사람에게 아무 도움이 안 된다. 그래서 done 항목도 목록에서 사라지지 않는다.
  ⑤ **누가 보는가.** 시스템 설정(app/sysops/router.py)과 같은 근거로 system_admin 만이다.
     admin 은 부서 범위로 좁혀질 수 있는데(admin_scope="dept") 여기 담긴 것은 조직 단위가
     아니라 **서버 한 대 전체**의 상태라 범위라는 개념 자체가 없다.

그리고 ⑥ 셋업이 안 끝난 동안 **일반 사용자에게 조용히 빈 목록을 주지 않는다** -
그게 지금 상태이고, 이 과제가 없애려는 바로 그 침묵이다.
"""

from __future__ import annotations

import pytest

from app.setup.checklist import SETUP_SCREEN_HREF, USER_NOTICE_ID

pytestmark = pytest.mark.integration

CHECKLIST = "/api/admin/setup/checklist"

# 안내 순서 = 의존 순서. 이 목록의 순서가 곧 계약이다.
EXPECTED_ORDER = [
    "admin_account",
    "mail",
    "organization",
    "notion",
    "user_mapping",
    "llm",
    "integrations",
    "tls",
]

STATE_DONE = "done"
STATE_TODO = "todo"
STATE_UNKNOWN = "unknown"
STATES = {STATE_DONE, STATE_TODO, STATE_UNKNOWN}


@pytest.fixture()
def sysadmin(login_as):
    return login_as("system_admin")


def _items(client):
    r = client.get(CHECKLIST)
    assert r.status_code == 200, r.text
    return r.json()


def _by_key(payload):
    return {item["key"]: item for item in payload["items"]}


def _write_notion_tokens(settings):
    """Notion 토큰 파일 두 개를 채운다(app/core/secret_refs.py 의 파일 참조 방식)."""
    for ref in (settings.notion_report_token_ref, settings.notion_docs_token_ref):
        (settings.secrets_dir / ref).write_text("secret-token-value", encoding="utf-8")


# ── ② 의존 순서 ──────────────────────────────────────────────────────────────


def test_items_come_back_in_dependency_order(client, sysadmin):
    payload = _items(client)
    assert [i["key"] for i in payload["items"]] == EXPECTED_ORDER


def test_every_prerequisite_appears_before_the_item_that_needs_it(client, sysadmin):
    """순서가 의존을 **실제로** 위상정렬한 것인지 본다.

    상수 목록만 비교하면 상수를 잘못 적었을 때 테스트도 같이 틀린다.
    """
    payload = _items(client)
    seen: list[str] = []
    for item in payload["items"]:
        for required in item["requires"]:
            assert required in seen, (
                f"{item['key']} 가 아직 안내하지 않은 {required} 를 전제로 삼는다"
            )
        seen.append(item["key"])


def test_a_blocked_item_says_what_blocks_it(client, sysadmin):
    """앞이 안 됐는데 뒤를 물으면 사용자는 막힌 이유를 모른다."""
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app)  # mail은 organization과 독립이라 이 검사의 관심사가 아니다.
    items = _by_key(_items(client))
    # 갓 설치한 상태: 부서가 하나도 없어서 조직이 '안 됨' 이다.
    assert items["organization"]["state"] == STATE_TODO
    # 그 뒤 항목들은 스스로 '무엇 때문에 막혔는지' 를 말해야 한다.
    assert items["notion"]["blocked_by"] == "organization"
    assert items["user_mapping"]["blocked_by"] is not None
    # 그리고 지금 안내할 항목은 막히지 않은 첫 항목이다.
    assert _items(client)["next_key"] == "organization"


def test_the_next_step_moves_forward_only_when_the_one_before_it_is_done(
    client, db, sysadmin
):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app)  # mail은 organization과 독립이라 이 검사의 관심사가 아니다.
    assert _items(client)["next_key"] == "organization"

    db.add(Department(name="개발팀", org_id=DEFAULT_ORG_ID))
    db.commit()

    payload = _items(client)
    assert payload["next_key"] == "notion"
    assert _by_key(payload)["notion"]["blocked_by"] is None


# ── ① 됨 / 안 됨 / 확인 불가 ─────────────────────────────────────────────────


def test_every_item_is_exactly_one_of_the_three_states(client, sysadmin):
    for item in _items(client)["items"]:
        assert item["state"] in STATES, f"{item['key']} 의 상태가 셋 중 하나가 아니다"


def test_a_fresh_install_shows_both_todo_and_unknown(client, sysadmin):
    """둘이 합쳐져 있으면 이 단정 중 하나는 반드시 깨진다."""
    states = {i["key"]: i["state"] for i in _items(client)["items"]}
    assert STATE_TODO in states.values(), "사람이 할 일이 하나도 없다고 말한다"
    # TLS: 이 서버가 인증서를 직접 들고 있지 않다. 앞단 프록시가 끊는 설치일 수도 있어
    # 앱은 **알 수 없다** - '안 됨' 이 아니라 '확인 불가' 다.
    assert states["tls"] == STATE_UNKNOWN


def test_todo_tells_you_what_to_do_and_unknown_tells_you_what_to_check(client, sysadmin):
    """상태 이름만 다르고 문구가 같으면 합쳐 놓은 것과 다를 바 없다."""
    for item in _items(client)["items"]:
        if item["state"] == STATE_TODO:
            assert item["action"], f"{item['key']} 가 '안 됨' 인데 할 일을 말하지 않는다"
            assert item["question"] is None
        elif item["state"] == STATE_UNKNOWN:
            assert item["question"], f"{item['key']} 가 '확인 불가' 인데 물을 것이 없다"
            assert item["action"] is None
        else:
            assert item["action"] is None and item["question"] is None


def test_todo_and_unknown_are_counted_separately(client, sysadmin):
    payload = _items(client)
    todo = [i["key"] for i in payload["items"] if i["state"] == STATE_TODO]
    unknown = [i["key"] for i in payload["items"] if i["state"] == STATE_UNKNOWN]
    assert payload["todo"] == todo
    assert payload["unknown"] == unknown
    assert set(payload["todo"]) & set(payload["unknown"]) == set()


def test_configured_but_never_synced_notion_is_unknown_not_done(
    client, db, settings, sysadmin
):
    """토큰과 DB id 가 채워졌다는 것만으로 '됨' 이라 말하면 거짓말이다.

    그 토큰이 실제로 통하는지는 **한 번이라도 동기화가 성공해야** 알 수 있다.
    """
    assert _by_key(_items(client))["notion"]["state"] == STATE_TODO  # 토큰 파일이 없다

    _write_notion_tokens(settings)
    assert _by_key(_items(client))["notion"]["state"] == STATE_UNKNOWN

    from app.observability.models import COMPONENT_TICKETS, SYNC_OK, SyncStatus

    db.add(
        SyncStatus(
            component=COMPONENT_TICKETS,
            status=SYNC_OK,
            last_success_at=client.app.state.clock.now(),
            item_count=3,
        )
    )
    db.commit()
    assert _by_key(_items(client))["notion"]["state"] == STATE_DONE


# ── ③ 하나를 채우면 그 항목만 바뀐다 ─────────────────────────────────────────


def test_creating_a_department_flips_only_the_organization_item(client, db, sysadmin):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    before = {i["key"]: i["state"] for i in _items(client)["items"]}
    assert before["organization"] == STATE_TODO

    db.add(Department(name="개발팀", org_id=DEFAULT_ORG_ID))
    db.commit()

    after = {i["key"]: i["state"] for i in _items(client)["items"]}
    assert after["organization"] == STATE_DONE
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"organization"}, f"부서 하나를 만들었는데 {changed} 가 함께 변했다"


def test_registering_a_runner_flips_only_the_llm_item(client, db, sysadmin):
    from app.runners.models import Runner

    before = {i["key"]: i["state"] for i in _items(client)["items"]}
    assert before["llm"] == STATE_TODO

    db.add(
        Runner(
            name="claude-ticket-runner",
            provider_type="http_service",
            base_url="http://127.0.0.1:8787",
            enabled=True,
            last_health_status="up",
        )
    )
    db.commit()

    after = {i["key"]: i["state"] for i in _items(client)["items"]}
    assert after["llm"] == STATE_DONE
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"llm"}, f"러너 하나를 등록했는데 {changed} 가 함께 변했다"


def test_healthy_runner_detail_does_not_imply_real_dispatch(client, db, sysadmin):
    """RN-10: "모두 정상"은 헬스체크 응답일 뿐이다. 이 레지스트리는 지금 실제 업무 처리
    경로에 연결돼 있지 않으므로(app/jobs/handlers/의 어떤 핸들러도 러너를 부르지 않는다),
    상태 문구가 그 사실과 무관하다는 것을 밝혀야 관리자가 등록 개수만큼 실제로 일이
    나뉘어 처리된다고 오해하지 않는다."""
    from app.runners.models import Runner

    db.add(
        Runner(
            name="claude-ticket-runner",
            provider_type="http_service",
            base_url="http://127.0.0.1:8787",
            enabled=True,
            last_health_status="up",
        )
    )
    db.commit()

    item = _by_key(_items(client))["llm"]
    assert item["state"] == STATE_DONE
    assert "실제 업무 처리 여부와는 별개" in item["detail"]


def test_a_registered_but_never_health_checked_runner_is_unknown(client, db, sysadmin):
    """등록됐다는 사실과 살아 있다는 사실은 다르다."""
    from app.runners.models import Runner

    db.add(
        Runner(
            name="claude-ticket-runner",
            provider_type="http_service",
            base_url="http://127.0.0.1:8787",
            enabled=True,
            last_health_status="unknown",
        )
    )
    db.commit()
    assert _by_key(_items(client))["llm"]["state"] == STATE_UNKNOWN


# ── ④ 끝난 뒤에도 계속 보인다 ────────────────────────────────────────────────


def test_a_finished_item_stays_on_the_list(client, db, sysadmin):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    db.add(Department(name="개발팀", org_id=DEFAULT_ORG_ID))
    db.commit()

    payload = _items(client)
    assert [i["key"] for i in payload["items"]] == EXPECTED_ORDER
    assert _by_key(payload)["organization"]["state"] == STATE_DONE
    # 남은 항목은 done 이 아닌 것 전부. 한 번 닫으면 끝나는 마법사가 아니다.
    assert "organization" not in payload["remaining"]
    assert payload["remaining"] == [
        i["key"] for i in payload["items"] if i["state"] != STATE_DONE
    ]
    assert payload["complete"] is False


# ── ⑤ 권한 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("user", 403),
        ("operator", 403),
        ("auditor", 403),
        ("admin", 403),
        ("system_admin", 200),
    ],
)
def test_only_the_system_admin_sees_the_wizard(client, login_as, role, expected):
    login_as(role)
    assert client.get(CHECKLIST).status_code == expected


def test_anonymous_cannot_read_the_checklist(client):
    assert client.get(CHECKLIST).status_code == 401


def test_a_department_scoped_admin_is_refused(client, db, login_as, make_user):
    """범위가 없는 대상에 범위 있는 역할을 들이지 않는다(app/sysops/router.py 와 같은 근거)."""
    from app.users.models import ADMIN_SCOPE_DEPT, User

    login_as("admin", email="deptadmin@goodmit.co.kr")
    row = db.query(User).filter(User.email == "deptadmin@goodmit.co.kr").one()
    row.admin_scope = ADMIN_SCOPE_DEPT
    db.commit()
    assert client.get(CHECKLIST).status_code == 403


# ── ⑥ 셋업이 안 끝난 동안 일반 사용자에게 무엇을 말하는가 ────────────────────


def test_a_regular_user_is_told_why_the_screens_are_empty(client, login_as):
    """로그인은 막지 않는다. 대신 **왜 비어 있는지** 를 말한다.

    조용히 빈 목록을 주는 것이 이 과제가 없애려는 바로 그 상태다.
    """
    login_as("user")
    r = client.get("/api/system/status")
    assert r.status_code == 200
    notices = r.json()["notices"]
    setup = [n for n in notices if n["id"] == USER_NOTICE_ID]
    assert setup, "셋업이 안 끝났는데 일반 사용자 화면에 아무 말도 없다"
    assert setup[0]["message"]


def test_the_user_notice_does_not_leak_internals(client, login_as):
    """일반 사용자에게 항목 키·설정 키·경로를 노출하지 않는다(app/observability 와 같은 선)."""
    login_as("user")
    message = [
        n for n in client.get("/api/system/status").json()["notices"]
        if n["id"] == USER_NOTICE_ID
    ][0]["message"]
    for leak in ("notion_tasks_database_id", "secrets_dir", "/api/admin", "Runner"):
        assert leak not in message


def test_the_user_notice_disappears_once_the_visible_items_are_done(
    client, login_as, setup_complete
):
    """정상인데도 배너가 남으면 아무도 배너를 안 믿는다."""
    login_as("user")
    notices = client.get("/api/system/status").json()["notices"]
    assert [n for n in notices if n["id"] == USER_NOTICE_ID] == []


def test_a_new_unmapped_user_does_not_reopen_the_banner(client, login_as, setup_complete):
    """반년 뒤 신입 한 명이 전 직원 배너를 다시 띄우면 안 된다.

    개별 미연결은 설치 문제가 아니라 운영 문제다(app/setup/probes.py 의 같은 주석).
    """
    login_as("user")  # 매핑이 없는 새 계정
    notices = client.get("/api/system/status").json()["notices"]
    assert [n for n in notices if n["id"] == USER_NOTICE_ID] == []


def test_the_user_banner_reopens_when_the_only_gap_is_an_unknown_runner(
    client, login_as, setup_complete, db
):
    """setup_complete 는 러너를 헬스체크 통과(up) 상태로 만든다. 그 러너를 '아직 헬스체크
    안 됨(unknown)' 으로 되돌리면, 사람이 할 일은 없지만(확인 불가) AI 기능은 실제로
    답하지 않을 수 있다 - 배너 문구("AI 기능이 답하지 않을 수 있습니다")가 그대로 말하는
    상황이다.

    setup_notice() 가 STATE_TODO 만 보고 STATE_UNKNOWN 을 빼먹으면 이 상태에서 배너가
    조용해진다 - 이 기능이 없애려던 바로 그 침묵이다.
    """
    from app.runners.models import Runner

    runner = db.query(Runner).one()
    runner.last_health_status = "unknown"
    db.commit()

    login_as("user")
    notices = client.get("/api/system/status").json()["notices"]
    setup = [n for n in notices if n["id"] == USER_NOTICE_ID]
    assert setup, "러너가 확인 불가(unknown) 상태인데도 사용자 배너가 조용하다"


def test_the_admin_notice_points_at_the_wizard(client, login_as):
    """관리자에게는 "관리자에게 문의하세요" 가 아무 도움이 안 된다.

    갈 곳을 주지 않고 "화면에서 확인하세요" 라고만 하면 그 문장은 안내가 아니라 수수께끼다.
    """
    login_as("system_admin")
    notices = client.get("/api/system/status").json()["notices"]
    setup = [n for n in notices if n["id"] == USER_NOTICE_ID]
    assert setup, "셋업이 안 끝났는데 관리자 화면에도 아무 말이 없다"
    assert "초기 설정" in setup[0]["message"]
    assert "문의" not in setup[0]["message"]
    assert setup[0]["href"] == SETUP_SCREEN_HREF


def test_the_regular_user_notice_has_no_link(client, login_as):
    """열리지 않는 화면으로 보내는 링크는 안내가 아니라 막다른 길이다."""
    login_as("user")
    setup = [
        n for n in client.get("/api/system/status").json()["notices"]
        if n["id"] == USER_NOTICE_ID
    ][0]
    assert setup["href"] is None
    assert "문의" in setup["message"]


# ── 나머지 가지 (안 밟아 본 판정은 안 만든 판정과 같다) ──────────────────────
#
# 위 테스트만으로는 각 항목의 '가장 흔한 두 가지'만 지난다. 나머지 가지(중단, 미점검,
# 충돌, 비활성, 만료)는 실제로 장애가 났을 때 처음 실행되는 코드다 - 그때 처음 실행되면
# 그때 처음 틀린다.


def test_a_sync_error_after_configuration_is_a_persons_problem(
    client, db, settings, sysadmin
):
    """토큰은 넣었는데 동기화가 실패한다면 그건 물어볼 일이 아니라 고칠 일이다."""
    from app.observability.models import COMPONENT_TICKETS, SYNC_ERROR, SyncStatus

    _write_notion_tokens(settings)
    db.add(
        SyncStatus(component=COMPONENT_TICKETS, status=SYNC_ERROR, error="401 unauthorized")
    )
    db.commit()
    notion = _by_key(_items(client))["notion"]
    assert notion["state"] == STATE_TODO
    assert notion["action"]
    # 사람에게 보이는 문구에 원본 예외를 그대로 싣지 않는다.
    assert "401" not in notion["detail"]


def test_a_disabled_runner_is_not_an_llm(client, db, sysadmin):
    from app.runners.models import Runner

    db.add(
        Runner(
            name="off-runner", provider_type="http_service",
            base_url="http://127.0.0.1:8789", enabled=False, last_health_status="up",
        )
    )
    db.commit()
    assert _by_key(_items(client))["llm"]["state"] == STATE_TODO


def test_a_down_runner_beats_an_unchecked_one(client, db, sysadmin):
    """죽은 것이 하나라도 있으면 '미점검' 이 아니라 '안 됨' 이다."""
    from app.runners.models import Runner

    db.add_all(
        [
            Runner(
                name="down-runner", provider_type="http_service",
                base_url="http://127.0.0.1:8787", enabled=True, last_health_status="down",
            ),
            Runner(
                name="new-runner", provider_type="http_service",
                base_url="http://127.0.0.1:8789", enabled=True,
                last_health_status="unknown",
            ),
        ]
    )
    db.commit()
    assert _by_key(_items(client))["llm"]["state"] == STATE_TODO


def test_a_departed_users_stale_mapping_does_not_count_as_connected(
    client, db, sysadmin, make_user
):
    """오프보딩은 UserNotionMapping 행을 지우거나 재설정하지 않는다
    (app/offboarding/service.py 는 그 행을 읽기만 한다). 유일하게 verified 였던 사람이
    archived 되면, 실제로 연결된 활성 사용자는 0명인데 그 행만 영원히 남아 '활성 사용자
    N명 중 1명 연결' 이라고 거짓말하면 안 된다.
    """
    from datetime import datetime

    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    left = make_user(email="left-already@goodmit.co.kr", display_name="퇴사자")
    db.add(
        UserNotionMapping(
            user_id=left.id, notion_user_id="left-notion-id", status=STATUS_VERIFIED
        )
    )
    db.commit()
    # 아직 활성이니 지금은 '됨' 이어야 한다 - 이 검사가 아래 회귀를 실제로 잡는지 보증한다.
    assert _by_key(_items(client))["user_mapping"]["state"] == STATE_DONE

    left.active = False
    left.archived_at = datetime(2026, 1, 1)
    db.commit()

    mapping = _by_key(_items(client))["user_mapping"]
    assert mapping["state"] != STATE_DONE, (
        "연결된 유일한 사람이 퇴사했는데 여전히 '됨' 이라고 말한다"
    )


def test_an_unchecked_integration_is_a_question_not_a_failure(client, db, sysadmin):
    from app.integrations.models import Integration

    db.add(
        Integration(
            name="n8n", provider_type="n8n", base_url="http://127.0.0.1:5678",
            capabilities_json="{}", enabled=True, last_health_status="unknown",
        )
    )
    db.commit()
    integrations = _by_key(_items(client))["integrations"]
    assert integrations["state"] == STATE_UNKNOWN
    assert integrations["question"]


def test_only_conflicts_and_nobody_connected_is_a_persons_problem(client, db, sysadmin):
    from app.notion_mapping.models import STATUS_CONFLICT, UserNotionMapping
    from app.users.models import User
    from sqlalchemy import select

    me = db.execute(select(User)).scalars().first()
    db.add(
        UserNotionMapping(
            user_id=me.id, status=STATUS_CONFLICT, candidates_json='["a", "b"]'
        )
    )
    db.commit()
    mapping = _by_key(_items(client))["user_mapping"]
    assert mapping["state"] == STATE_TODO
    assert "충돌" in mapping["action"] or "정리" in mapping["action"]


def test_an_admin_who_never_changed_the_temp_password_is_not_done(app, db, make_user):
    """seed_admin.py 만 돌고 아무도 로그인하지 않은 설치의 상태다.

    이 가지는 **API 로는 볼 수 없다**: 그 상태의 관리자는 로그인 직후 비밀번호 변경에
    막혀 이 화면에 닿지 못한다(app/core/deps.py). 그래도 판정은 돌아간다 - 사용자 배너가
    같은 체크리스트를 계산한다. 그래서 판정 함수를 직접 부른다. 화면으로 못 본다고
    검사하지 않으면 그 설치에서 처음 실행되면서 그때 처음 틀린다.
    """
    from app.setup.checklist import build_setup_checklist

    make_user(
        email="fresh-admin@goodmit.co.kr", role="system_admin", must_change_password=True
    )
    checklist = build_setup_checklist(
        db,
        app.state.settings,
        secrets=app.state.secret_provider,
        cache=app.state.settings_cache,
    )
    admin = {i["key"]: i for i in checklist["items"]}["admin_account"]
    assert admin["state"] == STATE_TODO
    assert "비밀번호" in admin["action"]


def test_mail_unconfigured_is_a_persons_problem(client, sysadmin):
    """ADM-02R: 메일 항목이 아예 없었다 — 이제 있고, 기본 설치에서는 '안 됨'이다."""
    mail = _by_key(_items(client))["mail"]
    assert mail["state"] == STATE_TODO
    assert mail["action"]
    assert mail["question"] is None


def test_mail_configured_is_done(client, sysadmin):
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app)
    mail = _by_key(_items(client))["mail"]
    assert mail["state"] == STATE_DONE
    assert "smtp.internal" in mail["detail"]


def test_mail_with_a_username_but_no_password_secret_is_still_todo(client, sysadmin):
    """`app/mail/config.py::configuration_problems`를 그대로 부른다는 것을 실제로 본다 —
    새 판정을 만들지 않는다는 모듈 docstring의 약속이 실제로 지켜지는지."""
    from tests.integration.test_password_reset import configure_smtp

    configure_smtp(client.app, username="mailer", password_ref="")
    mail = _by_key(_items(client))["mail"]
    assert mail["state"] == STATE_TODO
    assert "비밀번호" in mail["detail"]


def test_mail_is_not_counted_as_user_visible(client, login_as, setup_complete):
    """메일이 안 돼도 화면이 비지는 않는다 — 일반 사용자 배너의 이유가 아니다.

    `setup_complete`는 의도적으로 메일을 설정하지 않는다(conftest 주석). 그런데도 배너가
    조용해야 이 성질이 실제로 지켜지는 것이다.
    """
    from app.setup.checklist import USER_NOTICE_ID

    login_as("system_admin")
    assert _by_key(_items(client))["mail"]["state"] == STATE_TODO  # 전제 확인

    login_as("user")
    notices = client.get("/api/system/status").json()["notices"]
    assert [n for n in notices if n["id"] == USER_NOTICE_ID] == []


def test_a_configured_cert_path_with_no_file_is_a_persons_problem(
    client, tmp_path, sysadmin
):
    """경로를 적어 두고 파일이 없는 것은 '확인 불가' 가 아니라 '안 됨' 이다."""
    client.app.state.settings.tls_cert_path = str(tmp_path / "missing.crt")
    tls = _by_key(_items(client))["tls"]
    assert tls["state"] == STATE_TODO
    assert tls["action"]


def test_a_self_signed_cert_is_unknown_not_done(client, tmp_path, sysadmin):
    """SYS-05: 만료 전이라도 자체서명이면 "됨"이 아니다 — 브라우저는 오늘 이미 경고를
    띄우는데 초록으로 뭉개면 이 화면의 다른 문구(만료 시 경고를 띄운다는 안내)와
    정면으로 어긋난다. `_TEST_CERT_PEM`은 자체서명(issuer==subject)이다."""
    from tests.integration.test_health_worker_hardening import _TEST_CERT_PEM

    cert = tmp_path / "server.crt"
    cert.write_text(_TEST_CERT_PEM, encoding="utf-8")
    client.app.state.settings.tls_cert_path = str(cert)
    tls = _by_key(_items(client))["tls"]
    assert tls["state"] == STATE_UNKNOWN
    assert "자체서명" in tls["detail"]
    assert "일" in tls["detail"]  # 남은 날짜 자체는 여전히 말해 준다


def test_a_ca_signed_cert_is_still_done(client, tmp_path, sysadmin, monkeypatch):
    """자체서명이 아니면(issuer != subject) 예전처럼 그대로 "됨"이다 — 이번 정정이
    자체서명 케이스만 좁혀 잡았는지, 일반 CA 서명 인증서까지 덩달아 unknown으로
    끌고 가지 않았는지를 확인한다."""
    import app.health.service as health_service
    from tests.integration.test_health_worker_hardening import _TEST_CERT_PEM

    cert = tmp_path / "server.crt"
    cert.write_text(_TEST_CERT_PEM, encoding="utf-8")
    client.app.state.settings.tls_cert_path = str(cert)

    # notAfter는 실제 파싱 결과를 그대로 쓰되(cert_days_remaining이 계속 정상 동작하도록),
    # subject/issuer만 CA 서명처럼 다르게 흉내 낸다.
    real = health_service.ssl._ssl._test_decode_cert(str(cert))
    fake = {**real, "issuer": ((("commonName", "Some Trusted CA"),),)}
    monkeypatch.setattr(health_service.ssl._ssl, "_test_decode_cert", lambda path: fake)

    tls = _by_key(_items(client))["tls"]
    assert tls["state"] == STATE_DONE
    assert "일" in tls["detail"]


def test_a_garbage_cert_file_is_unanswerable_not_missing(client, tmp_path, sysadmin):
    cert = tmp_path / "server.crt"
    cert.write_text("PEM 이 아닙니다", encoding="utf-8")
    client.app.state.settings.tls_cert_path = str(cert)
    tls = _by_key(_items(client))["tls"]
    assert tls["state"] == STATE_UNKNOWN
    assert tls["question"]
