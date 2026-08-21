"""미할당 티켓을 둘이 동시에 잡는 경합 (Z1).

## 왜 아픈가

`claim_ticket` 은 담당자를 **읽고 → Notion 에 쓴다.** 그 사이 왕복이 두 번(0.5~3초) 들어간다.

    A: 담당자를 읽는다 -> []          B: 담당자를 읽는다 -> []
    A: [A] 로 쓴다                    B: [B] 로 쓴다      <- A 를 덮어쓴다
    A: "배정됐습니다"                  B: "배정됐습니다"    <- **둘 다 성공 토스트**

A 는 자기 티켓이라고 믿고 일을 시작하는데 실제 담당자는 B 다. 오류는 어디에도 안 뜬다.
회의 중 트리아지에서 실제로 자주 일어나는 모양이다.

## 이 테스트가 헛것이 되지 않으려면

**두 요청이 실제로 겹쳐야** 한다. 순서대로 부르면 두 번째가 "이미 배정됨" 으로 막혀서
경합과 무관하게 통과한다. 그래서 저장소를 느리게 만들어(읽기 뒤에 대기) 겹치는 창을 강제로
벌리고, 스레드 둘로 동시에 부른다.
"""

from __future__ import annotations

import threading
from datetime import datetime

import pytest

# 이 파일은 **전용 DB** 가 필요하다(D-190). 스레드 여럿이 각자 세션을 열어 경합을
# 만드는데, 공유 DB 계층에서는 그 세션들이 **같은 커넥션 하나**를 나눠 쓴다 —
# 경합이 재현되기는커녕 커넥션이 엉켜 엉뚱한 오류가 난다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

PAGE = "page-claim"


# 잠금 표를 비우는 픽스처가 여기 있었다. **이제 필요 없다** — 잠금은 프로세스 메모리가
# 아니라 PostgreSQL 이 들고 있고(D-192), `pg_advisory_xact_lock` 은 트랜잭션이 끝나는
# 순간 DB 가 놓는다. 앞 시험이 남긴 잠금이 다음 시험을 막을 자리 자체가 없다.


class _SlowRepo:
    """읽기와 쓰기 사이를 **실제로 벌리는** 가짜 저장소.

    `gate` 가 열릴 때까지 읽기가 돌아오지 않으므로, 두 요청이 같은 창 안에 들어간다.
    """

    def __init__(self, gate: threading.Event) -> None:
        self.gate = gate
        self.assignees: list[str] = []
        self.writes: list[list[str]] = []
        self._guard = threading.Lock()

    def get_live(self, db, *, page_id):
        from app.tickets.repository import TicketDTO

        with self._guard:
            current = list(self.assignees)
        self.gate.wait(timeout=5)
        return TicketDTO(page_id=page_id, title="미할당 티켓", url=None,
                         assignee_ids=tuple(current))

    def update(self, db, *, page_id, changes, now):
        from app.tickets.repository import TicketDTO

        people = [p["id"] if isinstance(p, dict) else p
                  for p in changes.get("assignee_notion_ids") or []]
        with self._guard:
            self.assignees = list(people)
            self.writes.append(list(people))
        return TicketDTO(page_id=page_id, title="미할당 티켓", url=None,
                         assignee_ids=tuple(people))


@pytest.fixture()
def world(db, make_user, make_project):
    """앱 사용자 둘 + Notion 연결. 둘 다 미할당 티켓을 잡을 자격이 있다.

    **미할당은 소속이 없다는 뜻이 아니다** (0060 §12). 담당자가 없을 뿐 프로젝트는 있다 —
    프로젝트가 없으면 그 티켓은 애초에 아무에게도 안 보이고, 그러면 "둘이 동시에 잡는다"
    라는 상황 자체가 만들어지지 않는다.
    """
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.tickets.models import PROJECT_LINK_OK, TicketCache

    project = make_project(name="클레임 프로젝트")
    first = make_user("claim-a@goodmit.co.kr", role="user", display_name="가")
    second = make_user("claim-b@goodmit.co.kr", role="user", display_name="나")
    db.add_all([
        UserNotionMapping(user_id=first.id, notion_user_id="n-a", status=STATUS_VERIFIED),
        UserNotionMapping(user_id=second.id, notion_user_id="n-b", status=STATUS_VERIFIED),
        TicketCache(
            notion_page_id=PAGE, title="미할당 티켓", org_id=DEFAULT_ORG_ID,
            project_uid=project.id, project_link=PROJECT_LINK_OK,
        ),
    ])
    db.commit()
    return first, second


def _claim(app, user, repo, results, index):
    from app.tickets import service

    with app.state.session_factory() as session:
        merged = session.get(type(user), user.id)
        try:
            service.claim_ticket(
                session, None, app.state.settings, merged,
                page_id=PAGE, now=datetime(2026, 8, 6, 9, 0, 0), repo=repo,
            )
            results[index] = "ok"
        except Exception as exc:  # noqa: BLE001 - 무엇이 났는지 보려고 담는다
            results[index] = type(exc).__name__


def test_two_people_claiming_at_once_do_not_both_win(app, world):
    """🔴 핵심 - 한 사람만 성공하고, 진 사람은 **실패를 본다.**"""
    first, second = world
    gate = threading.Event()
    repo = _SlowRepo(gate)
    results: dict[int, str] = {}

    threads = [
        threading.Thread(target=_claim, args=(app, first, repo, results, 0)),
        threading.Thread(target=_claim, args=(app, second, repo, results, 1)),
    ]
    for t in threads:
        t.start()
    # 두 요청이 같은 창 안에 들어갈 시간을 준 뒤 읽기를 풀어 준다.
    threading.Timer(0.2, gate.set).start()
    for t in threads:
        t.join(timeout=10)

    outcomes = sorted(results.values())
    assert outcomes.count("ok") == 1, (
        f"둘 다 성공하거나 둘 다 실패했다: {results} / 쓰기 {repo.writes}"
    )
    assert "ClaimInProgressError" in outcomes, (
        f"진 사람이 실패를 못 봤다 - 조용히 덮어썼다는 뜻이다: {results}"
    )
    assert len(repo.writes) == 1, f"소스에 두 번 썼다: {repo.writes}"


def test_the_winner_actually_owns_the_ticket(app, world):
    """오탐 방지 - 막느라 아무도 못 잡게 되면 그건 기능 고장이다."""
    first, _second = world
    gate = threading.Event()
    gate.set()   # 이번에는 창을 벌리지 않는다
    repo = _SlowRepo(gate)
    results: dict[int, str] = {}

    _claim(app, first, repo, results, 0)

    assert results[0] == "ok", f"혼자 눌렀는데도 실패했다: {results}"
    assert repo.assignees == ["n-a"], f"담당자가 안 들어갔다: {repo.assignees}"


def test_a_second_claim_after_the_first_finishes_is_not_blocked(app, world):
    """잠금이 **끝나면 풀려야** 한다. 안 풀리면 그 티켓은 영영 못 잡는다."""
    first, second = world
    gate = threading.Event()
    gate.set()
    repo = _SlowRepo(gate)
    results: dict[int, str] = {}

    _claim(app, first, repo, results, 0)
    _claim(app, second, repo, results, 1)

    assert results[0] == "ok", results
    # 두 번째는 담당자가 이미 있으므로 잠금이 아니라 **권한 판정**에 걸린다.
    # 여기서 중요한 것은 `ClaimInProgressError` 가 아니라는 점이다.
    assert results[1] != "ClaimInProgressError", (
        f"앞 요청이 끝났는데도 잠금이 남아 있다: {results}"
    )
