"""휴지통 목록이 **말한 대로 주는가** — 정렬 · 절단 · 개수 · 미리보기.

사용자가 화면을 보고 「탭도 이상하고 정렬 안 돼 있고」라고 했다. 갈라 보니 이 응답 자체가
서로 다른 네 가지 방식으로 사실과 어긋나 있었다.

  1. **요청한 것보다 많이 준다.** 두 원천(옛 미러 표 · Native 문서)에서 각각 `limit` 만큼
     받아 이어 붙이고 **자르지 않았다.** `limit=5` 인데 10줄이 왔다. 낭비만이면 그나마
     낫다 — 두 잘린 앞토막의 합집합이라 **앞 5자리만** 전역 순서가 맞고, 그 뒤는 한쪽
     원천의 중간이 통째로 빠진 목록이었다.
  2. **정렬 축이 없었다.** 삭제 예정일이 임박한 순으로 볼 방법이 아예 없었다.
  3. **개수를 걸러진 목록에서 셌다.** 화면이 그렇게 했고 서버는 그 재료를 안 줬다.
     문서 화면의 「휴지통」이 `?kind=document` 로 여니 첫 화면부터 「티켓 0」이 떴다.
  4. **티켓과 옛 미러 문서는 제목 말고 볼 것이 없었다.** 영구 삭제는 되돌릴 수 없는데도.

각 시험에 **반례**를 함께 둔다 — 고쳐도 초록이고 되돌려도 초록인 시험은 시험이 아니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

ME = "tlc-me@goodmit.co.kr"

# 옛 미러 항목과 Native 문서를 **시간으로 엇갈리게** 놓는다. 한쪽만 먼저 자르면 목록
# 한가운데가 비는 것을 이 배치가 드러낸다 — 같은 날짜로 몰아 두면 어떤 순서든 그럴듯해 보인다.
#
# 간격이 «시간»인 이유: 전부 **하루 안에** 버려져 있어야 「아직 아무것도 급하지 않다」가
# 성립하고(보관기간 7일), 그 상태에서 시계를 엿새 옮기면 «전부 급하다»로 한 번에 넘어간다.
# 두 상태를 다 재야 늘 0 을 내는 구현과 늘 전부를 내는 구현이 함께 걸린다.
SLOTS = 12


@pytest.fixture()
def world(db, make_user, fake_clock):
    """티켓 6건과 문서 6건을 한 시간씩 번갈아 버린 상태 — 전부 지난 하루 안이다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.trash.models import TrashItem

    me = make_user(ME, role="admin", display_name="나")
    space = KnowledgeSpace(name="휴지통 공간", slug="tlc-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()

    # 열두 칸을 한 시간씩: 짝수 칸은 티켓, 홀수 칸은 문서. 최신이 11번이다.
    base = fake_clock.now() - timedelta(hours=SLOTS + 1)
    docs, tickets = [], []
    for day in range(SLOTS):
        when = base + timedelta(hours=day)
        if day % 2 == 0:
            item = TrashItem(
                item_type="ticket", notion_page_id=f"tlc-np-{day}", title=f"티켓 {day:02d}",
                deleted_by_user_id=me.id, deleted_by_name="나", deleted_at=when,
                org_id=DEFAULT_ORG_ID,
            )
            db.add(item)
            tickets.append(item)
        else:
            document = Document(
                space_id=space.id, title=f"문서 {day:02d}", created_by=me.id,
                archived=True, archived_at=when, archived_by=me.id,
            )
            db.add(document)
            docs.append(document)
    db.commit()
    return {"space": space.id, "docs": [d.id for d in docs], "me": me.id}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=ME)}


def _get(client, hdr, query=""):
    r = client.get("/api/trash" + query, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


# ── ① 요청한 것보다 많이 주지 않는다, 그리고 순서가 전역이다 ──────────────────


def test_the_response_never_exceeds_the_limit_it_was_asked_for(client, login_as, world):
    """🔴 `limit=5` 인데 10줄이 왔다 — 두 원천에서 각각 5줄씩 받아 안 잘랐다."""
    body = _get(client, _hdr(login_as), "?limit=5")
    assert len(body["items"]) == 5, (
        f"{len(body['items'])}줄이 왔다 — 두 원천을 합친 뒤 자르지 않는다"
    )
    assert body["total"] == 12, "전체 개수는 상한과 무관하게 12건이어야 한다"


def test_the_first_page_is_the_globally_newest_rows_not_the_newest_of_each_source(
    client, login_as, world
):
    """🔴 여기가 진짜 결함이다 — 앞 5줄이 **두 원천을 통틀어** 가장 최근이어야 한다.

    반례가 이 자리에 있다: 각 원천의 앞 5줄을 그냥 이어 붙이면 티켓 10·8·6·4·2 와
    문서 11·09·07·05·03 이 와서, 자른 앞 5줄은 그중 아무거나가 된다. 전역 순서라면
    11·10·09·08·07 이다.
    """
    items = _get(client, _hdr(login_as), "?limit=5")["items"]
    assert [r["title"] for r in items] == [
        "문서 11", "티켓 10", "문서 09", "티켓 08", "문서 07",
    ], "두 원천을 각각 자른 앞토막의 합집합이다 — 전역 순서가 아니다"


def test_load_more_extends_the_same_list_instead_of_inserting_rows_in_the_middle(
    client, login_as, world
):
    """「더 보기」로 늘린 목록의 앞부분은 **그대로**여야 한다.

    안 자르던 시절에는 늘리는 순간 없던 줄이 목록 한가운데에 나타나 아래가 전부 밀렸다 —
    체크박스를 고르는 중이면 고른 줄이 바뀌었다.
    """
    hdr = _hdr(login_as)
    first = [r["id"] for r in _get(client, hdr, "?limit=5")["items"]]
    wider = [r["id"] for r in _get(client, hdr, "?limit=10")["items"]]
    assert wider[:5] == first, "상한을 늘리자 앞 5줄이 달라졌다"


# ── ② 정렬 축 ────────────────────────────────────────────────────────────────


def test_sorting_by_deleted_at_ascending_puts_the_oldest_first(client, login_as, world):
    items = _get(client, _hdr(login_as), "?limit=5&sort=deleted_at&dir=asc")["items"]
    assert [r["title"] for r in items] == [
        "티켓 00", "문서 01", "티켓 02", "문서 03", "티켓 04",
    ]


def test_sorting_by_title_orders_across_both_sources(client, login_as, world):
    """제목 축은 두 원천이 **서로 섞여야** 옳다. 한쪽만 정렬하면 티켓이 통째로 먼저 온다."""
    items = _get(client, _hdr(login_as), "?limit=12&sort=title&dir=asc")["items"]
    titles = [r["title"] for r in items]
    assert titles == sorted(titles), "제목 오름차순이 아니다"
    assert titles[0].startswith("문서"), "제목순인데 종류로 갈려 있다"


def test_rows_with_the_same_timestamp_keep_one_stable_order(client, login_as, world, db):
    """🔴 동점 묶음이 새로고침마다 다른 순서를 내면 상한 경계에서 행이 사라진다.

    일괄 삭제는 여러 행에 **같은 시각**을 찍는다. 두 원천을 각각 잘라 합치는 자리라,
    동점 안의 순서가 흔들리면 그 묶음이 상한에 걸릴 때 새로고침마다 다른 행이 잘려 나간다 —
    사용자에게는 「방금 있던 것이 사라졌다」로 보이고 재현도 안 된다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.trash.models import TrashItem
    from datetime import datetime as _dt

    same = _dt(2026, 7, 1, 0, 0, 0)
    from app.users.models import User
    from sqlalchemy import select

    me = db.execute(select(User).where(User.email == ME)).scalar_one()
    for n in range(6):
        db.add(TrashItem(
            item_type="ticket", notion_page_id=f"tlc-tie-{n}", title=f"동점 {n}",
            deleted_by_user_id=me.id, deleted_by_name="나", deleted_at=same,
            org_id=DEFAULT_ORG_ID,
        ))
    db.commit()

    hdr = _hdr(login_as)
    seen = [[r["id"] for r in _get(client, hdr, "?limit=18")["items"]] for _ in range(3)]
    assert seen[0] == seen[1] == seen[2], "같은 요청이 판마다 다른 순서를 냈다"
    # 그리고 상한을 잘라도 **같은 앞토막**이다 — 이것이 실제로 행을 잃던 자리다.
    cut = [r["id"] for r in _get(client, hdr, "?limit=9")["items"]]
    assert cut == seen[0][:9], "상한을 줄이자 앞토막이 달라졌다"


def test_an_unknown_sort_axis_falls_back_instead_of_breaking_the_list(client, login_as, world):
    """모르는 값으로 목록을 깨뜨리지 않는다 — 옛 주소를 들고 온 사람이 있다."""
    body = _get(client, _hdr(login_as), "?limit=3&sort=' OR 1=1--&dir=up")
    assert body["sort"] == "deleted_at" and body["dir"] == "desc"
    assert [r["title"] for r in body["items"]] == ["문서 11", "티켓 10", "문서 09"]


def test_the_response_says_which_order_it_actually_used(client, login_as, world):
    """화면의 정렬 화살표가 이 값을 그린다 — 없으면 첫 화면의 화살표가 추측이다."""
    body = _get(client, _hdr(login_as), "?sort=purge_after&dir=asc")
    assert body["sort"] == "purge_after" and body["dir"] == "asc"


# ── ③ 개수는 조건·상한과 무관하다 ────────────────────────────────────────────


def test_counts_are_the_same_no_matter_which_kind_is_selected(client, login_as, world):
    """🔴 문서만 보고 있어도 「티켓 6」이라고 말해야 한다.

    예전에는 화면이 **받아 온 목록**에서 셌기 때문에 `?kind=document` 에서 티켓이 0 이었다.
    반례가 함께 있다: 목록 자체는 실제로 좁혀져야 한다(개수만 맞고 목록이 안 좁혀지면
    그것은 다른 결함이다).
    """
    hdr = _hdr(login_as)
    everything = _get(client, hdr)
    only_docs = _get(client, hdr, "?kind=document")

    assert everything["counts"] == only_docs["counts"], "조건에 따라 탭의 숫자가 달라진다"
    assert only_docs["counts"]["ticket"] == 6
    assert only_docs["counts"]["document"] == 6
    assert only_docs["counts"]["all"] == 12
    # 목록은 좁혀진다 — 개수만 맞고 목록이 안 좁혀지면 그것도 결함이다.
    assert {r["item_type"] for r in only_docs["items"]} == {"document"}


def test_counts_are_not_cut_by_the_limit(client, login_as, world):
    """상한을 3으로 줄여도 탭의 숫자는 12건 기준이다."""
    body = _get(client, _hdr(login_as), "?limit=3")
    assert len(body["items"]) == 3
    assert body["counts"]["all"] == 12


def test_urgent_counts_everything_due_within_a_day_not_only_the_loaded_rows(
    client, login_as, world, fake_clock
):
    """「24시간 내 영구 삭제」도 조건·상한과 무관하다.

    보관기간이 기본 7일이고 열둘 다 지난 하루 안에 버려졌으므로, 시계를 엿새 옮기면 전부
    급해진다. 반례로 **아무것도 안 급한 시점**도 함께 잰다 — 늘 0 을 내는
    구현과 늘 전부를 내는 구현을 이 두 시험이 함께 걸러 낸다.
    """
    hdr = _hdr(login_as)
    calm = _get(client, hdr, "?limit=1")["counts"]["urgent"]
    assert calm == 0, f"아직 아무것도 24시간 안이 아닌데 {calm}건이 급하다고 한다"

    # 전부 지난 하루 안에 버려졌고 보관기간이 7일이다 — 엿새를 넘기면 열둘 다 24시간 안이다.
    # 세션은 30분 유휴로 끊기므로(`session_idle_timeout_seconds`) 시계를 옮긴 뒤 다시 든다.
    fake_clock.advance(6 * 24 * 3600 + 3600)
    hot = _get(client, _hdr(login_as), "?limit=1")["counts"]["urgent"]
    assert hot == 12, f"상한이 1인데 급한 건수를 {hot}건으로 셌다 — 받아 온 목록만 세고 있다"


def test_documents_past_the_page_cap_are_reachable(client, login_as, world, monkeypatch):
    """🔴 「더 보기」가 문서 200건에서 멈추고 422 로 화면을 죽이던 자리.

    `list_documents` 는 한 번에 `PAGE_MAX` 까지만 준다. 예전에는 그 한 번으로 끝냈기 때문에
    보관 문서가 그 수를 넘으면 `items` 가 거기서 고정되는데 `total` 은 계속 늘어, 화면의
    「더 보기」가 영원히 수렴하지 않고 몇 번 더 누르면 상한을 넘어 422 가 났다.

    상한을 실제로 200 건 만들지 않고 **상한을 줄여서** 잰다 — 같은 갈래를 지나면서 세계가
    작다. 여섯 건짜리 세계에서 상한을 2 로 낮추면 이어 받기가 세 번 돌아야 여섯이 온다.
    반례는 그 이어 받기가 **같은 행을 두 번 주거나 빠뜨리지 않는 것**이다.
    """
    from app.knowledge import service as knowledge_service

    monkeypatch.setattr(knowledge_service, "PAGE_MAX", 2)
    body = _get(client, _hdr(login_as), "?limit=12&kind=document")
    titles = [r["title"] for r in body["items"]]
    assert titles == ["문서 11", "문서 09", "문서 07", "문서 05", "문서 03", "문서 01"], (
        "상한 너머의 문서를 못 받았거나 이어 받기가 순서를 깨뜨렸다"
    )
    assert len(set(r["id"] for r in body["items"])) == 6, "이어 받기가 같은 행을 두 번 줬다"


def test_sorting_by_purge_date_uses_the_real_purge_date_not_the_deletion_date(
    client, login_as, world, app
):
    """🔴 「삭제 예정」 축은 **두 원천의 보관기간이 다르면** 삭제일 순서와 갈라진다.

    티켓은 3일, 문서는 14일을 보관하게 두면 같은 날 버린 티켓과 문서의 삭제 예정일이
    11일 벌어진다. 그래서 「삭제 예정 빠른 순」은 **티켓이 전부 앞**이어야 한다 — 삭제일
    순서(둘이 번갈아)와 완전히 다른 목록이다. 이 시험이 없으면 두 축이 같은 값을 내는
    기본 설정(둘 다 7일)에서만 재게 되어, 축이 실제로 갈리는지 아무도 안 본다.
    """
    # 설정 캐시의 현재 값을 그대로 갈아 끼운다 — 이 캐시는 요청 길목에서 TTL 로만 다시
    # 읽으므로(`refresh_if_stale`) 시험 안에서는 안 되돌아온다.
    cache = app.state.settings_cache
    before = cache.current()
    cache._values = {**before, "trash_retention_days": 3, "document_trash_retention_days": 14}
    try:
        items = _get(client, _hdr(login_as), "?limit=12&sort=purge_after&dir=asc")["items"]
    finally:
        cache._values = before

    kinds = [r["item_type"] for r in items]
    assert kinds == ["ticket"] * 6 + ["document"] * 6, (
        "삭제 예정 축이 삭제일 축과 같은 순서를 냈다 — 보관기간 차이를 안 본다"
    )
    dates = [r["purge_after"] for r in items]
    assert dates == sorted(dates), "삭제 예정일이 오름차순이 아니다"


# ── ④ 발췌와 미리보기 ────────────────────────────────────────────────────────


def test_document_rows_carry_the_excerpt_the_server_already_computes(
    client, login_as, world, db
):
    """`list_page_extras` 가 계산해 놓고 버리던 값을 응답에 싣는다."""
    from app.knowledge import service as knowledge_service
    from app.users.models import User
    from sqlalchemy import select

    me = db.execute(select(User).where(User.email == ME)).scalar_one()
    document_id = world["docs"][0]
    # 보관된 문서에도 본문을 남길 수 있어야 이 시험이 성립한다 — 보관 전에 저장한다.
    document = knowledge_service.get_scoped_document_or_404(db, me, document_id)
    document.archived = False
    db.flush()
    knowledge_service.save_document(
        db, me, document_id,
        body={"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "본문 첫 줄입니다"}]}]},
    )
    document.archived = True
    db.commit()

    rows = _get(client, _hdr(login_as), "?limit=12")["items"]
    row = next(r for r in rows if r["id"] == "doc:" + document_id)
    assert "본문 첫 줄입니다" in row["excerpt"], "발췌를 계산해 놓고 안 싣는다"
    # 반례 — 본문이 없는 줄은 발췌를 지어내지 않는다.
    other = next(r for r in rows if r["item_type"] == "ticket")
    assert other["excerpt"] == ""
