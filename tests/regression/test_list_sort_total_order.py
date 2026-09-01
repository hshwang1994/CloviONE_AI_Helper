"""무한 스크롤의 **핵심 계약**: 묶음을 끝까지 이어 받으면 행 집합이 정확히 전체와 같다.

## 이 시험이 없으면 무엇을 놓치는가

목록이 쪽에서 묶음으로 바뀌면서 화면은 OFFSET 을 이어 붙인다. 정렬이 **전순서**(total order)가
아니면 — 즉 1차 키가 같은 행들 사이의 순서를 DB 가 매번 마음대로 정하면 — 같은 행이 두 묶음에
나오거나 아예 빠진다. **그리고 그 어긋남은 오류를 안 낸다.** 화면에는 「행이 하나 사라졌다」로
보이고, 새로고침하면 돌아와서 재현조차 안 된다.

## 왜 동률을 심는가

🔴 **동률 행을 안 심으면 tiebreak 가 없어도 이 시험이 통과한다.** 값이 전부 다르면 1차 키만으로
순서가 정해지기 때문이다. 그러면 검사가 아무것도 안 보면서 초록이 된다 —
`tests/security/test_search_scope_before_limit.py` 가 적어 둔 「표본이 사건을 재현하지 못하면
시험이 약한 게 아니라 뜻이 없다」가 정확히 이 자리다.

그래서 **같은 시각의 행을 여럿** 만든다(가짜 시계를 안 움직인다).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


def _walk(client, path, *, params, size):
    """묶음을 끝까지 이어 받아 (받은 id 순서, 서버가 말한 total) 을 돌려준다."""
    seen, page, total = [], 1, None
    while True:
        r = client.get(path, params={**params, "page": page, "page_size": size})
        assert r.status_code == 200, r.text
        body = r.json()
        if total is None:
            total = body["total"]
        items = body["items"]
        seen.extend(row["id"] for row in items)
        if not items or len(seen) >= total or page > 50:
            break
        page += 1
    return seen, total


def _seed_ties(client, headers, fake_clock):
    """**같은 시각**의 감사 로그를 여럿 만든다 — 동률이 있어야 tiebreak 를 잰다.

    시계를 안 움직이므로 `created_at` 이 전부 같다. 그 상태에서 순서를 정하는 것은
    tiebreak(PK) 하나뿐이다.
    """
    for i in range(7):
        r = client.post(
            "/api/admin/users",
            json={"email": f"tie{i}@goodmit.co.kr", "display_name": f"동률{i}"},
            headers=headers,
        )
        assert r.status_code in (200, 201), r.text
    # 값이 다른 행도 섞는다 — 1차 키가 실제로 쓰이는지 함께 본다.
    fake_clock.advance(60)
    r = client.post(
        "/api/admin/users",
        json={"email": "later@goodmit.co.kr", "display_name": "나중"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text


AUDIT_SORTS = ["created_at", "action", "object_type", "result"]


@pytest.mark.parametrize("sort", AUDIT_SORTS)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_audit_chunks_cover_everything_exactly_once(client, login_as, fake_clock, sort, order):
    csrf = login_as("admin")
    _seed_ties(client, {"X-CSRF-Token": csrf}, fake_clock)

    params = {"sort": sort, "order": order}
    # 묶음 크기 2 — 경계를 여러 번 지나게 한다. 크게 잡으면 경계가 한 번뿐이라 못 본다.
    chunked, total = _walk(client, "/api/admin/audit", params=params, size=2)

    assert len(chunked) == total, "받은 건수가 서버가 말한 전체와 다르다"
    assert len(set(chunked)) == len(chunked), "같은 행이 두 묶음에 나왔다"

    # 그리고 그 순서가 한 번에 받은 순서와 **완전히 같아야** 한다 — 다르면 묶음 경계에서
    # 순서가 흔들린 것이고, 그 흔들림이 곧 누락·중복의 원인이다.
    single, _ = _walk(client, "/api/admin/audit", params=params, size=100)
    assert chunked == single


def test_audit_unknown_sort_falls_back_quietly(client, login_as, fake_clock):
    """모르는 정렬 키는 **거절하지 않고** 기본 정렬로 떨어진다.

    틀린 정렬 값은 어느 행이 나오는지를 안 바꾼다 — 400 으로 거절하면 옛 저장된 뷰와
    북마크가 그 순간 통째로 죽는다.
    """
    csrf = login_as("admin")
    _seed_ties(client, {"X-CSRF-Token": csrf}, fake_clock)

    junk = client.get("/api/admin/audit", params={"sort": "password_hash", "page_size": 100})
    assert junk.status_code == 200
    default = client.get("/api/admin/audit", params={"page_size": 100})
    assert [r["id"] for r in junk.json()["items"]] == [r["id"] for r in default.json()["items"]]


def test_notifications_and_jobs_answer_sort_without_breaking(client, login_as):
    """정렬을 새로 받는 다른 목록도 200 이고 봉투 모양이 그대로다.

    자료가 없어도 의미가 있다 — 파라미터를 안 받는 라우터였다면 FastAPI 가 그것을 무시하고
    지나갔을 뿐, 정렬 절이 실제로 붙었는지는 이 호출이 500 을 안 내는 것으로 드러난다.
    """
    login_as("admin")
    for path, sort in (
        ("/api/notifications", "read_at"),
        ("/api/admin/jobs", "started_at"),
        ("/api/admin/approvals", "status"),
        ("/api/admin/announcements", "level"),
        ("/api/admin/impersonation/sessions", "ended_at"),
        ("/api/admin/offboarding", "user_name"),
        ("/api/me/activity", None),
    ):
        params = {"order": "asc"}
        if sort:
            params["sort"] = sort
        r = client.get(path, params=params)
        assert r.status_code == 200, f"{path}: {r.text}"
        body = r.json()
        assert "items" in body and "total" in body, path