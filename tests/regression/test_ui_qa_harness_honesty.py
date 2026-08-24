"""QA 하네스가 **모르는 것을 안다고 말하지 않도록** 못 박는다.

세 가지 결함이 실제로 조사를 오염시켰다(BACKLOG `QA-10`·`QA-11`·`QA-12`):

* `QA-12` `system_admin` 전용 화면을 `admin` 계정으로 찍으면 **권한 거부 배너**가 찍히는데
  21개 검사가 그 배너를 기준으로 전부 통과하고 요약에 `ok` 로 올라갔다. 화면 2,600줄이
  "검사됨"으로 집계된 채 한 번도 보이지 않았다.
* `QA-11` `auditor` 는 `/api/admin/jobs` 가 403 인데 하네스가 **"표시할 데이터가 없어"** 라고
  적었다. 역할 매트릭스에서 "이 역할이 못 본다"와 "행이 없다"는 정반대의 사실이다.
* `QA-10` `tiny_text` 는 폭 2200 미만에서 skip 이라 1920 캡처 요약이 늘
  `통과 0 / 실패 0 / 건너뜀 N` 이었고 그것이 "문제 없음"으로 읽혔다. 3840 으로 돌리자 6/6 실패.
* `QA-13` `narrow_main` 은 3840 이상에서만 돈다. 일부(6)만 돌면 `통과 6 / 실패 0 / 건너뜀 60`
  으로 나와 `QA-10`이 고친 "전부 skip" 조건에는 안 걸린다 — "통과 6"만 보면 이번 실행 대부분을
  확인한 것 같지만, 실제로는 본 것보다 못 본 것(건너뜀)이 더 많다.

여기서 검사하는 것은 제품이 아니라 **조사 도구의 정직성**이다. 도구가 거짓을 말하면
그 위에 쌓은 결론이 전부 거짓이 된다.
"""

from __future__ import annotations

import pytest

from scripts.ui_qa import assertions
from scripts.ui_qa.capture import discover_detail_hash
from scripts.ui_qa.routes import BY_ID, Route
from scripts.ui_qa.run import check_marker


class _Resp:
    def __init__(self, status: int, payload=None) -> None:
        self.status = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _Ctx:
    """`context.request.get` 만 흉내 낸다 — 그 한 호출이 판정의 전부다."""

    def __init__(self, response: _Resp) -> None:
        self._response = response

        class _Request:
            @staticmethod
            def get(url, timeout=None):  # noqa: ARG004
                return response

        self.request = _Request()


@pytest.fixture
def detail_route() -> Route:
    return BY_ID["admin_job-detail"]


# ── QA-11: 권한 거부를 "데이터 없음" 으로 뭉개지 않는다 ──────────────────────


@pytest.mark.parametrize("status", [401, 403])
def test_permission_denial_is_not_reported_as_missing_data(detail_route, status):
    _, note = discover_detail_hash(_Ctx(_Resp(status)), "https://x", detail_route,
                                   log=lambda *a: None)
    assert "권한" in note, f"{status} 를 권한 문제로 말하지 않는다: {note}"
    assert "표시할 데이터가 없어" not in note, (
        f"{status} 를 '데이터 없음' 으로 뭉갠다 — 역할 조사에서 가장 알고 싶은 차이다: {note}"
    )
    assert str(status) in note, f"어떤 상태 코드였는지 남기지 않는다: {note}"


def test_empty_list_is_reported_as_missing_data(detail_route):
    _, note = discover_detail_hash(_Ctx(_Resp(200, {"items": []})), "https://x",
                                   detail_route, log=lambda *a: None)
    assert "표시할 데이터가 없어" in note, note
    assert "권한" not in note, f"빈 목록을 권한 문제로 말한다: {note}"


def test_found_id_still_resolves(detail_route):
    hash_path, note = discover_detail_hash(
        _Ctx(_Resp(200, {"items": [{"id": "abc"}]})), "https://x", detail_route,
        log=lambda *a: None)
    assert hash_path and "abc" in hash_path, (hash_path, note)


# ── QA-12: 역할로 볼 수 없는 라우트를 `ok` 로 세지 않는다 ────────────────────


def test_system_admin_only_routes_are_not_visible_to_admin():
    """이 넷이 `admin` 계정 캡처에서 권한 거부 배너로 찍히고도 `ok` 였다.

    넷 중 `/notion-console` 은 화면째 사라졌다(S14 · D-284). 그래서 여기서도 빠진다 —
    없는 주소를 계속 세면 이 시험은 목록이 비어도 통과하는 쪽으로 조용히 기운다.
    """
    for rid in ("admin_system", "admin_setup", "admin_llm-console"):
        route = BY_ID[rid]
        assert not route.visible_to("admin"), f"{rid} 가 admin 에게 보인다고 판정된다"
        assert route.visible_to("system_admin"), f"{rid} 가 system_admin 에게도 안 보인다"
    assert "admin_notion-console" not in BY_ID, (
        "지운 화면이 QA 라우트 목록에 돌아왔다 — 캡처가 404 를 찍고 ok 로 센다"
    )


def test_ordinary_routes_stay_visible():
    assert BY_ID["admin_users"].visible_to("admin")
    assert BY_ID["user_my-tickets"].visible_to("user")
    assert BY_ID["public_login"].visible_to("user"), "공개 화면은 역할과 무관하다"


# ── QA-13: 통과가 있어도 건너뜀이 우세하면 그 사실을 감추지 않는다 ────────────


def test_never_ran_when_all_skipped():
    mark, bucket = check_marker(0, 0, 67)
    assert bucket == "never_ran"
    assert "한 번도 돌지 않음" in mark


def test_no_marker_when_nothing_skipped():
    mark, bucket = check_marker(40, 2, 0)
    assert bucket == "" and mark == ""


def test_no_marker_when_skip_is_a_minority():
    """건너뜀이 있어도 통과·실패가 더 많으면(대부분 실제로 돌았으면) 조용하다."""
    mark, bucket = check_marker(40, 2, 10)
    assert bucket == "" and mark == ""


def test_mostly_skipped_when_skip_outweighs_actual_verdicts():
    """narrow_main처럼 일부(6)만 돌고 나머지(60)는 건너뛰면 통과 수만으로는 안 드러난다."""
    mark, bucket = check_marker(6, 0, 60)
    assert bucket == "mostly_skipped"
    assert "대부분 건너뜀" in mark


def test_never_ran_takes_priority_over_mostly_skipped():
    """전부 skip인 경우는 두 조건을 다 만족하지만 더 정확한 '한 번도 안 돎'이 이겨야 한다."""
    mark, bucket = check_marker(0, 0, 5)
    assert bucket == "never_ran"
    assert "한 번도 돌지 않음" in mark


# ── content_clipped: inert 오프스크린 자손이 조상을 오탐시키지 않는다 ─────────
# (QA-15, 2026-08-15) 닫힌 모바일 드로어(position:absolute + translateX(-100%) +
# inert)는 시각적으로만 화면 밖으로 옮겨진다 — transform은 조상의 scrollWidth
# 계산에서 자손 상자를 빼지 않는다. 그 결과 실제로는 안 보이고 닿을 수도 없는
# (inert) 드로어의 폭이 화면에 멀쩡히 보이는 조상 Paper의 "잘림"으로 오검출됐다
# (실측: /chat 390px, 조상 onscreen=true·화면 정상인데 overX=79가 정확히 닫힌
# 사이드바 폭이었다). PROBE_JS는 실브라우저 없이 실행할 수 없으므로(다른 검사들과
# 같은 이유로 이 파일이 여기서 멈추듯) 회귀 방지 대상인 제외 조건이 소스에서
# 조용히 사라지지 않았는지만 고정한다.


def test_probe_js_excludes_inert_descendants_from_clipped_detection():
    assert "el.querySelector('[inert]')" in assertions.PROBE_JS


def test_visible_to_uses_allowed_roles_when_present():
    """`allowed_roles` 가 있으면 등급이 아니라 **그 집합**이 정답이다.

    등급으로만 판정하면 `auditor`(rank 2) 가 `operator`(rank 1) 전용 화면을 볼 수 있다고
    잘못 말한다 — 두 역할은 상하 관계가 아니다.
    """
    route = Route(id="x", hash_path="/x", console="admin", label="x",
                  min_role="operator", allowed_roles=("operator", "system_admin"))
    assert route.visible_to("operator")
    assert route.visible_to("system_admin")
    assert not route.visible_to("auditor")
    assert not route.visible_to("admin")
