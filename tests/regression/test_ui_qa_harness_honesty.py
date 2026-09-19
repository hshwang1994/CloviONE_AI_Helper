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
from scripts.ui_qa.capture import discover_detail_hash, split_expected_console
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


# ── 부분 캡처가 전량 Evidence 를 덮지 않는다 ────────────────────────────────


def test_missing_routes_or_full_is_a_harness_error():
    from argparse import Namespace
    from scripts.ui_qa.run import missing_capture_scope

    assert missing_capture_scope(Namespace(list=False, full=False, routes=None))
    assert missing_capture_scope(Namespace(list=False, full=False, routes=[]))
    assert missing_capture_scope(Namespace(list=True, full=False, routes=None)) is None
    assert missing_capture_scope(Namespace(list=False, full=True, routes=None)) is None
    assert missing_capture_scope(Namespace(list=False, full=False, routes=["smoke"])) is None


def test_partial_pages_merge_instead_of_replacing():
    from scripts.ui_qa.capture import merge_pages

    prior = [
        {"route": "user_me", "theme": "light", "viewport": "1920x1080", "n": 1},
        {"route": "user_chat", "theme": "light", "viewport": "1920x1080", "n": 2},
    ]
    new = [
        {"route": "user_me", "theme": "light", "viewport": "1920x1080", "n": 9},
    ]
    merged = merge_pages(prior, new)
    by_route = {row["route"]: row["n"] for row in merged}
    assert by_route["user_me"] == 9
    assert by_route["user_chat"] == 2


def test_write_manifest_merges_partial_into_existing(tmp_path):
    from scripts.ui_qa.capture import build_scope, write_manifest

    prior = {
        "scope": build_scope(routes=["a", "b"], viewports=["1920x1080"],
                             themes=["light"], page_count=2, full=True),
        "pages": [
            {"route": "a", "theme": "light", "viewport": "1920x1080", "assertions": {}},
            {"route": "b", "theme": "light", "viewport": "1920x1080", "assertions": {}},
        ],
        "notes": [],
        "run": {},
    }
    write_manifest(tmp_path, prior, replace=True)
    partial = {
        "scope": build_scope(routes=["a"], viewports=["1920x1080"],
                             themes=["light"], page_count=1, full=False),
        "pages": [
            {"route": "a", "theme": "light", "viewport": "1920x1080", "assertions": {"x": {"status": "pass"}}},
        ],
        "notes": [],
        "run": {},
    }
    path = write_manifest(tmp_path, partial, replace=False)
    import json
    payload = json.loads(path.read_text(encoding="utf-8"))
    routes = {p["route"] for p in payload["pages"]}
    assert routes == {"a", "b"}
    assert payload["scope"]["partial"] is True
    assert payload["scope"].get("merged") is True


def test_full_write_replaces_prior(tmp_path):
    from scripts.ui_qa.capture import build_scope, write_manifest
    import json

    write_manifest(tmp_path, {
        "scope": build_scope(routes=["old"], viewports=["1920x1080"],
                             themes=["light"], page_count=1, full=True),
        "pages": [{"route": "old", "theme": "light", "viewport": "1920x1080", "assertions": {}}],
        "notes": [], "run": {},
    }, replace=True)
    write_manifest(tmp_path, {
        "scope": build_scope(routes=["new"], viewports=["1920x1080"],
                             themes=["light"], page_count=1, full=True),
        "pages": [{"route": "new", "theme": "light", "viewport": "1920x1080", "assertions": {}}],
        "notes": [], "run": {},
    }, replace=True)
    payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert [p["route"] for p in payload["pages"]] == ["new"]


def test_unseen_findings_are_kept():
    from scripts.ui_qa.run import keep_unseen_findings

    prior = [
        {"id": "old", "route": "a", "theme": "light", "viewport": "1920x1080", "class": "x"},
    ]
    current = [
        {"id": "new", "route": "b", "theme": "light", "viewport": "1920x1080", "class": "y"},
    ]
    covered = {("b", "light", "1920x1080")}
    merged = keep_unseen_findings(prior, current, covered)
    assert {row["id"] for row in merged} == {"old", "new"}


# ── 기대한 콘솔 줄(음성 경로)과 다시 찾는 상세 화면 — UI 3차 P7 ─────────────────────────

CHROMIUM_404 = "Failed to load resource: the server responded with a status of 404 (Not Found)"


def test_expected_console_is_recorded_apart_but_only_for_its_own_pattern() -> None:
    """옛 문서 주소(없는 id)의 404 한 줄은 기대한 줄로 따로 남고, 다른 오류는 그대로 센다."""
    route = BY_ID["user_legacy-doc-redirect"]
    messages = [
        CHROMIUM_404,
        "Failed to load resource: the server responded with a status of 500 (Internal Server Error)",
        "TypeError: x is undefined",
    ]
    expected, counted = split_expected_console(route, messages)
    assert expected == [CHROMIUM_404]
    assert counted == messages[1:]
    # 기대 줄을 없애지 않는다 — 두 목록의 합이 원래 목록이다.
    assert sorted(expected + counted) == sorted(messages)


def test_routes_without_expected_console_count_every_line() -> None:
    route = BY_ID["user_my-tickets"]
    assert route.expected_console == ()
    expected, counted = split_expected_console(route, [CHROMIUM_404])
    assert expected == []
    assert counted == [CHROMIUM_404]


def test_expected_console_stays_on_negative_paths_only() -> None:
    """기대 줄은 음성 경로에만 둔다 — 조용히 넓어지면 진짜 404 가 가려진다."""
    with_expected = sorted(r.id for r in BY_ID.values() if r.expected_console)
    assert with_expected == ["user_legacy-doc-redirect"]


def test_game_room_is_rediscovered_per_capture_pass() -> None:
    """놀이방은 긴 실행 도중 유령 방 정리로 닫힐 수 있어 묶음마다 id 를 다시 찾는다."""
    route = BY_ID["user_game-room"]
    assert route.is_detail
    assert route.rediscover is True
    assert sorted(r.id for r in BY_ID.values() if r.rediscover) == ["user_game-room"]


def test_remote_account_guidance_keeps_secrets_off_the_command_line() -> None:
    """원격 QA 계정 안내는 환경 값을 명령행으로 펼치지 않는다 — 예전 `env $(sudo grep … DATABASE_URL …)` 는 비밀번호를 `ps` 에 올렸다."""
    from scripts.ui_qa import auth

    with pytest.raises(auth.AuthError) as caught:
        auth._provision("ui-qa@example.test", "unused", lambda *_: None,
                        base_url="https://clovirassist.gooddi.lab", role="admin")
    message = str(caught.value)
    assert "env $(" not in message and "env \\$(" not in message
    assert "grep -E '^(DATABASE_URL" not in message
    # 셸 안에서 환경 파일을 읽어 서비스 계정에 넘기는 형태(`deploy/install.sh::run_as_app`)다.
    assert "--preserve-environment" in message
    assert "done </etc/clovirassist/clovirassist.env" in message
    # sudo 비밀번호와 새 비밀번호는 stdin 으로만 간다.
    assert "sudo -S -p '' bash ~/qa-user-cli.sh passwd --email ui-qa@example.test" in message
    assert "echo" not in message
