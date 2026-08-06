"""문서 댓글 (사용자 지적 #9).

`app/team_docs/` 전체에 comment 문자열이 **0건**이었다. 티켓에는 논의를 남길 곳이 있는데
문서에는 없어서, 설계서 한 장에 대한 질문이 전부 채팅으로 흩어졌다.

규약은 티켓 댓글을 그대로 옮겼고, 이 파일이 그 **같음**을 고정한다:

  * 삭제는 툼스톤이다 - 행이 사라지지 않고 본문만 빠진다. 조용히 없어지면 이미 목록을 받아
    둔 사람은 자기가 잘못 봤다고 생각한다.
  * 쓰기마다 목록 전체를 돌려준다 - 클라이언트가 목록을 기워 맞추면 툼스톤 규약이 두 벌이 된다.
  * 수정은 작성자 본인만(운영자 우회 없음), 삭제는 작성자 또는 운영자군.
  * **범위 밖은 403 이 아니라 404**, 그리고 목록, 작성, 수정, 삭제가 전부 같은 판정을 지난다.
    티켓 댓글에서 정확히 이 자리가 뚫려 있었다(목록은 막고 삭제는 안 막음).

## 🔴 여기서 헛것을 조심한 자리

`test_the_notification_reaches_the_document_author` 는 문서에 **작성자 Notion id 를 실제로
매핑해 둔 뒤** 확인한다. 매핑이 없으면 알림 코드가 조용히 넘어가도록 되어 있어서(그게 정상
동작이다), 매핑 없는 문서로 시험하면 "알림이 0건" 인 것과 "알림 기능이 없는" 것이 구별되지
않는다. 그래서 아래에 **0건이어야 하는 경우**(내가 쓴 것)와 **1건이어야 하는 경우**를 나란히
둔다 - 한쪽만 있으면 단정이 참인지 알 수 없다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

NID_AUTHOR = "notion-dc-author"
NID_OTHER = "notion-dc-other"

MINE = "dc-mine"        # 우리팀 문서(작성자 = AUTHOR)
THEIRS = "dc-theirs"    # 남의팀 문서
FREE = "dc-free"        # 작성자를 해석할 수 없는 문서(동기화가 아직 id 를 안 채운 상태)

AUTHOR = "dc-author@goodmit.co.kr"   # 우리팀 일반 사용자, MINE 의 작성자
MATE = "dc-mate@goodmit.co.kr"       # 우리팀 일반 사용자(작성자 아님)
BOSS = "dc-boss@goodmit.co.kr"       # 우리팀만 보는 부서 범위 관리자
OUTSIDER = "dc-out@goodmit.co.kr"    # 남의팀 일반 사용자


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 사람 넷 + 문서 셋."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.team_docs.models import DocumentCache

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    author = make_user(AUTHOR, role="user", display_name="문서작성자")
    mate = make_user(MATE, role="user", display_name="같은팀동료")
    boss = make_user(BOSS, role="admin", display_name="우리팀장")
    outsider = make_user(OUTSIDER, role="user", display_name="남의팀사람")
    author.department_id = mine.id
    mate.department_id = mine.id
    outsider.department_id = theirs.id
    # 역할로는 모더레이션이 되지만 범위는 우리팀뿐이다. 이 조합이 범위 구멍의 주인공이다.
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id

    db.add(UserNotionMapping(
        user_id=author.id, notion_user_id=NID_AUTHOR, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(
        user_id=outsider.id, notion_user_id=NID_OTHER, status=STATUS_VERIFIED))
    db.add_all([
        DocumentCache(notion_page_id=MINE, title="우리팀 설계서",
                      author_notion_ids=NID_AUTHOR),
        DocumentCache(notion_page_id=THEIRS, title="남의팀 3분기 실적 보고서",
                      author_notion_ids=NID_OTHER),
        DocumentCache(notion_page_id=FREE, title="작성자 미해석 문서", author_notion_ids=""),
    ])
    db.commit()
    return {"author_id": author.id, "mate_id": mate.id, "outsider_id": outsider.id}


def _hdr(login_as, email, role="user"):
    return {"X-CSRF-Token": login_as(role, email=email)}


def _write(client, hdr, page_id, body):
    r = client.post(f"/api/team-docs/{page_id}/comments", json={"body": body}, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def _bodies(payload):
    return [c["body"] for c in payload["comments"]]


# ── 작성, 목록 ────────────────────────────────────────────────────────────────

def test_a_comment_can_be_written_and_read_back(client, login_as, world):
    hdr = _hdr(login_as, AUTHOR)
    created = _write(client, hdr, MINE, "이 설계 근거가 궁금합니다.")
    assert created["comment_id"]
    # 쓰기 응답이 이미 목록 전체다 - 클라이언트가 기워 맞출 것이 없다.
    assert _bodies(created) == ["이 설계 근거가 궁금합니다."]

    listed = client.get(f"/api/team-docs/{MINE}/comments")
    assert listed.status_code == 200, listed.text
    assert _bodies(listed.json()) == ["이 설계 근거가 궁금합니다."]
    only = listed.json()["comments"][0]
    assert only["author_name"] == "문서작성자"
    assert only["can_edit"] is True and only["can_delete"] is True


def test_a_teammate_who_did_not_write_the_document_can_still_comment(client, login_as, world):
    """문서는 팀 전체 조회 대상이다. 댓글만 작성자로 좁히면 물어볼 곳이 없어진다."""
    _write(client, _hdr(login_as, MATE), MINE, "옆 팀에서 참고해도 될까요?")
    r = client.get(f"/api/team-docs/{MINE}/comments")
    assert _bodies(r.json()) == ["옆 팀에서 참고해도 될까요?"]


def test_comments_come_back_oldest_first(client, login_as, world):
    """시계가 멈춘 테스트에서는 created_at 이 전부 같다 - tie-break 가 삽입 순서여야 한다.
    id(UUID4)로 깨면 목록이 절반의 확률로 뒤집힌다."""
    hdr = _hdr(login_as, AUTHOR)
    for text in ("하나", "둘", "셋", "넷", "다섯"):
        _write(client, hdr, MINE, text)
    r = client.get(f"/api/team-docs/{MINE}/comments")
    assert _bodies(r.json()) == ["하나", "둘", "셋", "넷", "다섯"]


def test_an_empty_body_is_rejected(client, login_as, world):
    r = client.post(f"/api/team-docs/{MINE}/comments", json={"body": "   "},
                    headers=_hdr(login_as, AUTHOR))
    assert r.status_code == 422, r.text


# ── 수정 ──────────────────────────────────────────────────────────────────────

def test_the_author_can_edit_their_own_comment(client, login_as, world):
    hdr = _hdr(login_as, AUTHOR)
    cid = _write(client, hdr, MINE, "처음 쓴 문장")["comment_id"]

    r = client.patch(f"/api/team-docs/comments/{cid}", json={"body": "고쳐 쓴 문장"},
                     headers=hdr)
    assert r.status_code == 200, r.text
    assert _bodies(r.json()) == ["고쳐 쓴 문장"]


def test_an_operator_cannot_rewrite_someone_elses_sentence(client, login_as, world):
    """남의 말을 바꾸는 것은 지우는 것보다 나쁘다 - 누가 썼는지는 그대로인데 내용만 달라진다.

    범위 **안**이므로 404 가 아니라 403 이다. 그 선을 여기서 지킨다.
    """
    cid = _write(client, _hdr(login_as, AUTHOR), MINE, "작성자의 문장")["comment_id"]

    r = client.patch(f"/api/team-docs/comments/{cid}", json={"body": "관리자가 고침"},
                     headers=_hdr(login_as, BOSS, role="admin"))
    assert r.status_code == 403, f"운영자가 남의 문장을 고쳐 썼다: {r.status_code} {r.text}"

    still = client.get(f"/api/team-docs/{MINE}/comments")
    assert _bodies(still.json()) == ["작성자의 문장"]


# ── 삭제(툼스톤) ──────────────────────────────────────────────────────────────

def test_a_deleted_comment_stays_as_a_tombstone(client, login_as, world):
    """행이 그냥 사라지면 사용자는 자기가 잘못 봤다고 생각한다. 자리는 남고 본문만 빠진다."""
    hdr = _hdr(login_as, AUTHOR)
    cid = _write(client, hdr, MINE, "지워질 문장")["comment_id"]

    r = client.delete(f"/api/team-docs/comments/{cid}", headers=hdr)
    assert r.status_code == 200, r.text
    rows = r.json()["comments"]
    assert len(rows) == 1, f"삭제된 댓글이 목록에서 통째로 사라졌다: {rows}"
    assert rows[0]["deleted"] is True
    assert rows[0]["body"] == "", "지운 내용이 계속 내려온다 - 그건 삭제가 아니다"
    assert rows[0]["deleted_at"]
    assert rows[0]["can_edit"] is False and rows[0]["can_delete"] is False

    # 목록 조회에서도 같은 모양이어야 한다(쓰기 응답만 툼스톤이면 규약이 두 벌이다).
    again = client.get(f"/api/team-docs/{MINE}/comments").json()["comments"]
    assert len(again) == 1 and again[0]["deleted"] is True and again[0]["body"] == ""


def test_an_operator_can_moderate_someone_elses_comment(client, login_as, world):
    """지우는 것은 운영자군도 할 수 있다(모더레이션). 고치는 것과 다른 축이다."""
    cid = _write(client, _hdr(login_as, MATE), MINE, "중재 대상")["comment_id"]

    r = client.delete(f"/api/team-docs/comments/{cid}",
                      headers=_hdr(login_as, BOSS, role="admin"))
    assert r.status_code == 200, f"범위 안인데 운영자가 못 지운다: {r.text}"
    assert r.json()["comments"][0]["deleted"] is True


def test_a_plain_user_cannot_delete_someone_elses_comment(client, login_as, world):
    cid = _write(client, _hdr(login_as, AUTHOR), MINE, "남의 문장")["comment_id"]
    r = client.delete(f"/api/team-docs/comments/{cid}", headers=_hdr(login_as, MATE))
    assert r.status_code == 403, f"일반 사용자가 남의 댓글을 지웠다: {r.status_code}"


def test_deleting_twice_is_idempotent_and_editing_a_dead_comment_fails(
    client, login_as, world
):
    """수정으로 삭제를 되돌리는 뒷문을 만들지 않는다."""
    hdr = _hdr(login_as, AUTHOR)
    cid = _write(client, hdr, MINE, "한 번만 지워진다")["comment_id"]
    first = client.delete(f"/api/team-docs/comments/{cid}", headers=hdr)
    assert first.status_code == 200
    stamp = first.json()["comments"][0]["deleted_at"]

    second = client.delete(f"/api/team-docs/comments/{cid}", headers=hdr)
    assert second.status_code == 200
    assert second.json()["comments"][0]["deleted_at"] == stamp, "두 번째 삭제가 시각을 바꿨다"

    revive = client.patch(f"/api/team-docs/comments/{cid}", json={"body": "부활"},
                          headers=hdr)
    assert revive.status_code == 404, f"삭제된 댓글이 수정으로 되살아났다: {revive.status_code}"


# ── 범위: 403 이 아니라 404, 그리고 네 경로가 전부 같은 판정 ─────────────────

def test_listing_another_teams_document_comments_is_404(client, login_as, world):
    r = client.get(f"/api/team-docs/{THEIRS}/comments", headers=_hdr(login_as, BOSS, role="admin"))
    assert r.status_code == 404, f"남의 팀 문서의 논의가 그대로 나간다: {r.status_code} {r.text}"


def test_writing_on_another_teams_document_is_404(client, login_as, db, world):
    from app.team_docs.models import DocumentComment

    r = client.post(f"/api/team-docs/{THEIRS}/comments", json={"body": "끼어들기"},
                    headers=_hdr(login_as, BOSS, role="admin"))
    assert r.status_code == 404, f"범위 밖 문서에 댓글이 달렸다: {r.status_code} {r.text}"
    db.expire_all()
    assert db.query(DocumentComment).count() == 0, "404 를 돌려주고도 행이 남았다"


def test_editing_and_deleting_a_comment_that_moved_out_of_scope_is_404(
    client, login_as, db, world
):
    """**이 테스트가 티켓에서 뚫려 있던 그 자리다.**

    수정, 삭제는 comment_id 만 받는다. 권한 판정(`ensure_can_edit`)만 지나면 통과하므로,
    내가 쓴 댓글이 붙은 문서가 나중에 남의 부서 것이 되어도 계속 고칠 수 있게 된다.
    그리고 응답이 **목록 전체**라 삭제 한 번에 그 문서의 논의가 통째로 새어 나온다.
    """
    from app.team_docs.models import DocumentCache, DocumentComment

    hdr = _hdr(login_as, BOSS, role="admin")
    cid = _write(client, hdr, FREE, "아직 어느 팀 것도 아닐 때 쓴 댓글")["comment_id"]

    # 다음 동기화가 작성자를 채웠고, 그 사람은 남의 팀이다.
    db.query(DocumentCache).filter(DocumentCache.notion_page_id == FREE).one() \
        .author_notion_ids = NID_OTHER
    db.commit()

    edit = client.patch(f"/api/team-docs/comments/{cid}", json={"body": "고침"}, headers=hdr)
    assert edit.status_code == 404, f"범위 밖으로 나간 내 댓글을 고칠 수 있다: {edit.status_code}"
    assert "comments" not in edit.json(), f"404 인데 목록이 실려 나갔다: {edit.text}"

    gone = client.delete(f"/api/team-docs/comments/{cid}", headers=hdr)
    assert gone.status_code == 404, f"범위 밖 댓글을 지울 수 있다: {gone.status_code}"
    db.expire_all()
    assert db.query(DocumentComment).one().deleted_at is None, \
        "404 를 돌려주고도 실제로 지워졌다"


def test_a_missing_document_and_a_hidden_one_answer_the_same(client, login_as, world):
    """두 답이 다르면 id 를 찍어 보며 **존재하는 문서를 열거**할 수 있다."""
    hdr = _hdr(login_as, BOSS, role="admin")
    missing = client.get("/api/team-docs/no-such-page/comments", headers=hdr)
    hidden = client.get(f"/api/team-docs/{THEIRS}/comments", headers=hdr)
    assert missing.status_code == hidden.status_code == 404
    assert missing.json()["error"]["message"] == hidden.json()["error"]["message"], (
        f"응답 문구가 달라 존재 여부가 새어 나간다: {missing.text} vs {hidden.text}"
    )


def test_a_document_without_resolvable_authors_still_accepts_comments(client, login_as, world):
    """**가장 중요한 오탐 검사.** `author_notion_ids` 는 다음 동기화가 채우므로 지금 대부분
    비어 있다 - 그걸 범위 밖으로 치면 아무도 자기 문서에 댓글을 못 단다."""
    r = client.post(f"/api/team-docs/{FREE}/comments", json={"body": "여긴 써져야 한다"},
                    headers=_hdr(login_as, BOSS, role="admin"))
    assert r.status_code == 200, f"작성자 미해석 문서에 댓글을 못 단다: {r.status_code} {r.text}"


def test_a_global_admin_still_sees_everything(client, login_as, world):
    """전역 관리자까지 좁히면 운영이 멈춘다."""
    hdr = {"X-CSRF-Token": login_as("system_admin")}
    r = client.post(f"/api/team-docs/{THEIRS}/comments", json={"body": "전역 관리자"},
                    headers=hdr)
    assert r.status_code == 200, r.text


# ── 알림 ──────────────────────────────────────────────────────────────────────

def _notifications(app, user_id):
    from app.notifications.models import Notification

    with app.state.session_factory() as s:
        return (
            s.query(Notification)
            .filter(Notification.user_id == user_id, Notification.type == "document_comment")
            .count()
        )


def test_the_notification_reaches_the_document_author(client, login_as, app, world):
    """문서 작성자는 자기 문서에 논의가 붙은 것을 스스로 열어 보지 않고도 알아야 한다."""
    _write(client, _hdr(login_as, MATE), MINE, "여기 근거가 뭔가요?")
    assert _notifications(app, world["author_id"]) == 1, "내 문서에 댓글이 달렸는데 알림이 없다"
    # 쓴 사람에게는 가지 않는다.
    assert _notifications(app, world["mate_id"]) == 0


def test_my_own_comment_does_not_notify_me(client, login_as, app, world):
    """내가 쓴 것을 나에게 알리면 배지가 늘 켜져 있다."""
    _write(client, _hdr(login_as, AUTHOR), MINE, "제가 쓴 문서에 제가 남기는 메모")
    assert _notifications(app, world["author_id"]) == 0, "내 댓글이 나에게 알림으로 왔다"
