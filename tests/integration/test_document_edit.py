"""문서를 **포털에서 편집**한다 (사용자 지적 #9).

사용자 보고는 "문서 편집이 정상적으로 동작하지 않는다" 였지만, 확인해 보니 **편집 기능이
아예 없었다.** 문서 상세는 Notion 미러를 읽기만 했다.

배관은 티켓 본문이 이미 갖고 있다(`app/tickets/service.py::save_ticket_body`). 여기서
고정하는 것은 그 배관이 문서에도 **같은 성질**로 붙었는가다:

1. 저장이 정말로 원본(Notion)까지 간다. 우리 DB 에만 쓰고 성공이라 말하면, 노션을 보는
   사람과 포털을 보는 사람이 다른 문서를 읽는다.
2. **낙관적 잠금이 충돌을 잡는다.** 문서는 범위 안이면 누구나 편집한다 - 두 사람이 동시에
   저장하면 나중 사람이 앞사람 글을 통째로 지우고 **양쪽 다 성공 토스트를 본다.**
3. 범위 밖은 404. 목록·상세를 좁혀 놓고 편집만 열어 두면 좁힌 의미가 없다(§0-A).
4. **작성자를 해석할 수 없는 문서는 편집된다.** `author_notion_ids` 는 다음 동기화가
   채우므로 지금 대부분 비어 있다 - 그걸 막으면 아무도 문서를 못 고친다.
5. push 실패를 삼키지 않는다. 정본은 살아 있으니 오류로 던질 수 없고, 그렇다고 성공이라
   말하면 원본과 어긋난 사실을 숨기는 거짓말이 된다.

## 소스가 갈린다 (S14)

위 다섯 중 **1 과 5 만 미러(Notion) 경로의 성질**이다. 둘 다 「정본과 원본이 다른 곳에
있다」를 전제로 하는 말이라 자체 DB 소스에서는 확인할 대상 자체가 없다. 그래서 그 두 절의
시험에 하나씩 `@pytest.mark.notion_source` 를 붙여 소스를 되돌린다. 나머지(CSRF·낙관적
잠금·범위 404·작성자 미해석·휴지통·감사)는 소스와 무관한 성질이므로 **제품 기본값인 자체
DB 위에서 그대로 선다** — 파일째 되돌리면 그 시험들이 실제로 배포되는 경로를 안 보게 된다.

표가 붙은 시험이 곧 **Notion 을 걷어낼 때 지울 목록**이다.
"""

from __future__ import annotations

import json

import pytest

from app.core.models_base import utcnow
from app.team_docs.models import DocumentCache

pytestmark = pytest.mark.integration

PAGE = "doc-edit-1"
BLOCKS_URL = "https://api.notion.com/v1/blocks/"


class FakeDocsPage:
    """문서 한 건의 본문 블록을 들고 있는 Notion 대역.

    URL 접두사만 보는 `fake_http.on` 으로는 GET(읽기)과 PATCH(쓰기)가 구별되지 않아
    "저장이 원본을 불렀는가" 를 물어볼 수 없다. 그래서 요청 전체를 보는 handler 를 쓴다.
    """

    def __init__(self) -> None:
        self.blocks = [
            {"id": "b1", "type": "paragraph",
             "paragraph": {"rich_text": [{"plain_text": "원래 본문"}]}},
            # 이미지는 편집기가 표현할 수 없다. 저장이 이걸 지우면 사용자 데이터가 사라진다.
            {"id": "b2", "type": "image", "image": {}},
        ]
        self.deleted: list[str] = []
        self.pushed: list[dict] = []
        self.push_fails = False

    def install(self, fake_http):
        fake_http.on_handler(BLOCKS_URL, self._handle)
        return self

    def _handle(self, request):
        method = request.method
        if method == "GET":
            return {"results": self.blocks, "has_more": False}
        if method == "DELETE":
            self.deleted.append(str(request.url).rsplit("/", 1)[-1])
            return {}
        if method == "PATCH":
            if self.push_fails:
                return (500, {"message": "boom"})
            self.pushed.append(json.loads(request.content.decode("utf-8")))
            return {}
        return None

    @property
    def pushed_text(self) -> str:
        return json.dumps(self.pushed, ensure_ascii=False)


@pytest.fixture()
def notion(fake_http, settings) -> FakeDocsPage:
    (settings.secrets_dir / "notion_docs_token").write_text("faketoken", encoding="utf-8")
    return FakeDocsPage().install(fake_http)


def _add_doc(db, page_id=PAGE, title="네트워크 설계서", **over):
    # 소속(0060)은 문서 자신이 든다. 이 파일이 검사하는 것은 소속 게이트가 아니라
    # 편집·목록 동작이므로 조직 공통으로 둔다 — 소속을 안 주면 전역 관리자만 보인다.
    over.setdefault("owner_kind", "organization")
    row = DocumentCache(notion_page_id=page_id, title=title, synced_at=utcnow(), **over)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def csrf(client, login_as, db, notion):
    token = login_as("user", email="docedit@goodmit.co.kr")
    _add_doc(db)
    return token


def _detail(client, page_id=PAGE):
    r = client.get("/api/team-docs/" + page_id)
    assert r.status_code == 200, r.text
    return r.json()


def _save(client, csrf, body, *, base_version=None, page_id=PAGE):
    payload = {"body_markdown": body}
    if base_version is not None:
        payload["base_version"] = base_version
    return client.put("/api/team-docs/" + page_id + "/body", json=payload,
                      headers={"X-CSRF-Token": csrf})


# ── 1) 저장이 원본까지 간다 ───────────────────────────────────────────────────
#
# **이 절의 세 시험은 소스를 미러로 되돌린다** (S14). 「원본까지 간다」는 말이 성립하려면
# 원본이 우리 밖에 있어야 하는데, 자체 DB 소스에는 밀어 넣을 상대가 없다. 표를 안 붙이면
# 저장이 아무 데도 안 가는 것이 정상 동작이 되어, 이 시험들이 텅 빈 요청 기록을 보고도
# 조용히 통과한다. 바로 아래 CSRF 시험은 소스와 무관하므로 표를 붙이지 않는다.


@pytest.mark.notion_source
def test_the_detail_hands_the_editor_a_body_and_a_version(client, csrf):
    """편집기를 열려면 마크다운이 필요하고, 저장하려면 그때의 지문이 필요하다.

    `body_is_local is False` 가 미러 경로의 말이다 — 「아직 우리가 저장한 적 없는 본문을
    원본에서 되읽었다」는 상태는 원본이 따로 있을 때만 존재한다. 자체 DB 에서 저장된 본문을
    여는 쪽은 `tests/integration/test_native_document_repository.py` 가 본다.
    """
    detail = _detail(client)
    assert detail["body_markdown"] == "원래 본문", detail
    assert detail["body_version"], "지문이 없으면 낙관적 잠금을 걸 수 없다"
    assert detail["body_is_local"] is False, "아직 우리 정본이 아니라 원본에서 되읽은 값이다"


@pytest.mark.notion_source
def test_saving_pushes_the_new_body_to_notion(client, csrf, notion):
    version = _detail(client)["body_version"]
    r = _save(client, csrf, "# 새 제목\n새 본문", base_version=version)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["synced"] is True, body
    assert body["body_sync_error"] is None, body
    assert notion.pushed, "저장이 원본(Notion)을 부르지 않았다 - 우리 DB 에만 남는다"
    assert "새 본문" in notion.pushed_text, notion.pushed_text
    # 우리 정본으로도 남는다.
    after = _detail(client)
    assert after["body_markdown"] == "# 새 제목\n새 본문", after
    assert after["body_is_local"] is True, after


@pytest.mark.notion_source
def test_saving_does_not_delete_the_image_block(client, csrf, notion):
    """편집기가 표현할 수 없는 블록은 사용자가 지운 적이 없다 - 저장이 지우면 안 된다.

    지울 블록이 있는 곳은 원본 페이지뿐이라 이것도 미러 경로의 성질이다. 표가 없으면
    `notion.deleted` 가 언제나 비어 있어 이 단언이 저절로 참이 된다.
    """
    _save(client, csrf, "새 본문", base_version=_detail(client)["body_version"])
    assert "b2" not in notion.deleted, f"이미지 블록을 지웠다: {notion.deleted}"


def test_saving_needs_csrf(client, csrf):
    r = client.put("/api/team-docs/" + PAGE + "/body", json={"body_markdown": "무단"})
    assert r.status_code == 403, r.text


# ── 2) 낙관적 잠금 ────────────────────────────────────────────────────────────

def test_a_stale_version_is_refused(client, csrf):
    """앞사람이 이미 저장한 뒤 옛 지문으로 저장하면 **막힌다.**"""
    version = _detail(client)["body_version"]
    first = _save(client, csrf, "앞사람 글", base_version=version)
    assert first.status_code == 200, first.text

    second = _save(client, csrf, "뒷사람 글", base_version=version)
    assert second.status_code == 409, f"앞사람 글이 조용히 지워진다: {second.status_code}"
    assert "먼저 저장" in second.text

    # 막았는데 지워졌으면 소용없다.
    assert _detail(client)["body_markdown"] == "앞사람 글"


def test_the_response_carries_the_new_version(client, csrf):
    """저장 뒤 지문을 돌려주지 않으면 화면이 다음 저장에서 반드시 충돌한다."""
    version = _detail(client)["body_version"]
    body = _save(client, csrf, "새 글", base_version=version).json()
    assert body.get("body_version") and body["body_version"] != version


def test_the_version_from_the_reloaded_detail_saves_again(client, csrf):
    """충돌 뒤 새로고침 - 그 지문으로는 저장돼야 한다. 아니면 영원히 못 고친다."""
    _save(client, csrf, "앞사람 글", base_version=_detail(client)["body_version"])
    again = _save(client, csrf, "합친 글", base_version=_detail(client)["body_version"])
    assert again.status_code == 200, again.text


# ── 3) 범위 밖은 404 ──────────────────────────────────────────────────────────

NID_MINE, NID_THEIRS = "notion-de-mine", "notion-de-theirs"
OP = "de-op@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user, notion):
    """부서 둘 + 우리팀만 보는 운영자 + 문서 셋(우리팀·남의팀·작성자 미해석)."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    op = make_user(OP, role="operator", display_name="부서운영자")
    author = make_user("de-author@goodmit.co.kr", role="user", display_name="작성자")
    other = make_user("de-other@goodmit.co.kr", role="user", display_name="남")
    op.department_id = mine.id
    op.admin_scope = "dept"
    op.scope_dept_id = mine.id
    author.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=author.id, notion_user_id=NID_MINE,
                             status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS,
                             status=STATUS_VERIFIED))
    # 소속(0060)은 문서 자신이 든다 — 작성자가 정하지 않는다. 마지막 문서는 작성자를
    # 앱 계정으로 해석할 수 없는 경우인데, 소속이 우리 팀이라 우리 팀은 그대로 편집한다.
    _add_doc(db, "dm", "우리팀 문서", author_notion_ids=NID_MINE,
             owner_kind="department", owner_dept_id=mine.id)
    _add_doc(db, "dt", "남의팀 3분기 실적 보고서", author_notion_ids=NID_THEIRS,
             owner_kind="department", owner_dept_id=theirs.id)
    _add_doc(db, "dn", "작성자 미해석 문서", author_notion_ids="",
             owner_kind="department", owner_dept_id=mine.id)
    db.commit()


def test_editing_another_teams_document_is_a_404(client, login_as, db, world):
    csrf = login_as("operator", email=OP)
    r = _save(client, csrf, "남의 문서에 쓴 글", page_id="dt")
    assert r.status_code == 404, f"남의 팀 문서를 편집할 수 있다: {r.status_code} {r.text}"
    db.expire_all()
    row = db.query(DocumentCache).filter_by(notion_page_id="dt").one()
    assert row.body_markdown is None, "404 를 돌려주고도 본문이 저장됐다"


def test_a_missing_page_is_the_same_404_as_an_out_of_scope_one(client, login_as, world):
    """두 답이 다르면 id 를 찍어 보며 **존재하는 문서를 열거**할 수 있다."""
    csrf = login_as("operator", email=OP)
    missing = _save(client, csrf, "글", page_id="no-such-page")
    hidden = _save(client, csrf, "글", page_id="dt")
    assert missing.status_code == hidden.status_code == 404
    assert missing.json()["error"]["message"] == hidden.json()["error"]["message"], (
        f"응답 문구가 달라 존재 여부가 새어 나간다: {missing.text} vs {hidden.text}"
    )


def test_the_operator_can_still_edit_their_own_team(client, login_as, world):
    csrf = login_as("operator", email=OP)
    r = _save(client, csrf, "우리팀 글", page_id="dm")
    assert r.status_code == 200, f"자기 팀 문서를 못 고친다: {r.status_code} {r.text}"


# ── 4) 작성자 미해석 문서는 편집된다 (가장 중요한 오탐 검사) ─────────────────

def test_a_document_without_resolvable_authors_can_still_be_edited(client, login_as, world):
    """`author_notion_ids` 는 다음 동기화가 채운다 - 지금 막으면 아무도 문서를 못 고친다."""
    csrf = login_as("operator", email=OP)
    r = _save(client, csrf, "미해석 문서 글", page_id="dn")
    assert r.status_code == 200, f"작성자 미해석 문서를 못 고친다: {r.status_code} {r.text}"


def test_a_plain_user_can_edit_a_document_they_did_not_write(client, login_as, world):
    """문서는 팀이 함께 쓴다. 편집을 작성자로 좁히면 위키가 아니라 개인 메모가 된다.
    (삭제는 여전히 작성자·운영자만이다 - 다른 축이다.)"""
    csrf = login_as("user", email="de-author@goodmit.co.kr")
    r = _save(client, csrf, "동료가 고친 글", page_id="dn")
    assert r.status_code == 200, f"작성자가 아니면 못 고친다: {r.status_code} {r.text}"


# ── 5) push 실패가 화면에 보인다 ──────────────────────────────────────────────
#
# **이 절 전체가 미러 경로다** (S14). push 라는 구간이 없으면 실패도 없고, 그래서 자체 DB
# 소스는 저장할 때마다 `body_sync_error` 를 오히려 **비운다** — 원본이 없어진 뒤에도 그
# 배너를 띄우면 사용자가 고칠 수 없는 경고를 영원히 보기 때문이다. 표를 안 붙이면 세 시험이
# 전부 「어긋난 적이 없으니 어긋나지 않았다」로 통과한다. 자체 DB 쪽에서 남은 오류가 지워지는
# 것은 `tests/integration/test_native_document_repository.py` 가 따로 본다.


@pytest.mark.notion_source
def test_a_failed_push_is_reported_not_swallowed(client, csrf, notion):
    notion.push_fails = True
    r = _save(client, csrf, "원본에 못 간 글", base_version=_detail(client)["body_version"])
    assert r.status_code == 200, f"정본은 저장됐는데 오류로 던지면 그 글이 롤백된다: {r.text}"
    body = r.json()
    assert body["synced"] is False, body
    assert body["body_sync_error"], "어긋난 이유를 말하지 않으면 화면이 배너를 그릴 수 없다"
    # 우리 글은 살아 있다.
    assert body["body_markdown"] == "원본에 못 간 글"


@pytest.mark.notion_source
def test_the_sync_error_survives_a_reload(client, csrf, notion):
    """토스트는 사라진다. 다시 열었을 때도 어긋난 사실이 보여야 한다."""
    notion.push_fails = True
    _save(client, csrf, "원본에 못 간 글", base_version=_detail(client)["body_version"])
    detail = _detail(client)
    assert detail["body_sync_error"], detail
    assert detail["body_markdown"] == "원본에 못 간 글", detail


@pytest.mark.notion_source
def test_a_later_successful_save_clears_the_sync_error(client, csrf, notion):
    notion.push_fails = True
    _save(client, csrf, "첫 시도", base_version=_detail(client)["body_version"])
    notion.push_fails = False
    r = _save(client, csrf, "첫 시도", base_version=_detail(client)["body_version"])
    assert r.status_code == 200, r.text
    assert r.json()["synced"] is True, r.text
    assert _detail(client)["body_sync_error"] is None


# ── 6) 휴지통 문서는 편집 불가 ────────────────────────────────────────────────

def test_a_trashed_document_cannot_be_edited(client, csrf, db):
    """지운 문서가 계속 고쳐지면, 그렇게 고친 내용은 보관기간이 끝나면 함께 사라진다(H2)."""
    # 삭제는 작성자·운영자만이다(편집과 다른 축). 이 사람이 작성자라고 해 둔다.
    from app.team_docs.models import join_names

    row = db.query(DocumentCache).filter_by(notion_page_id=PAGE).one()
    row.author_names = join_names(["테스트 사용자"])
    db.commit()

    r = client.post("/api/team-docs/" + PAGE + "/trash", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    r = _save(client, csrf, "지운 문서에 쓴 글")
    assert r.status_code == 404, f"휴지통 문서가 편집된다: {r.status_code} {r.text}"


# ── 감사 로그 ─────────────────────────────────────────────────────────────────

def test_the_save_is_audited(client, csrf, db):
    _save(client, csrf, "감사되는 글", base_version=_detail(client)["body_version"])
    from app.audit.models import AuditLog

    db.expire_all()
    actions = [a.action for a in db.query(AuditLog).all()]
    assert "team_docs.body.update" in actions, actions
