"""실브라우저 골든 패스 smoke (`QA-02`) — 로그인 → 사용자 콘솔 → 관리자 콘솔 → 팀 문서.

전수 검증(70라우트 × 뷰포트 × 테마)은 `scripts/ui_qa/run.py`가 이미 한다 — 여기는 그 반대
극단으로, **CI/수동 게이트에서 몇 초 안에 도는 최소 골든 패스**다. 실패하면 화면이 통째로
깨졌다는 뜻이고, 통과해도 `ui_qa` 전수 실행을 대체하지 않는다(`docs/QA_COVERAGE.md` 참고).

각 테스트는 콘솔 오류와 4xx/5xx 네트워크 응답을 **실제로 수집**해서 없음을 확인한다 —
"페이지가 열렸다"만으로는 안 속는다(`DECISIONS.md` D-27: 도구가 성공이라 해도 직접 본다).

`browser`는 세션 스코프 fixture(`conftest.py`)가 이미 `sync_playwright()` 를 열어 두고 준다 —
여기서 또 열면(중첩) "Sync API inside the asyncio loop" 로 죽는다(실제로 겪은 실패, 고치고
확인함). 테스트마다 새 `BrowserContext`만 열고 닫는다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


class _PageProbe:
    """한 페이지 방문 동안의 콘솔 오류·실패 네트워크 응답을 모은다."""

    def __init__(self, page):
        self.console_errors: list[str] = []
        self.failed_responses: list[str] = []
        page.on("console", self._on_console)
        page.on("response", self._on_response)

    def _on_console(self, msg) -> None:
        if msg.type == "error":
            self.console_errors.append(msg.text)

    def _on_response(self, response) -> None:
        if response.status >= 400:
            self.failed_responses.append(f"{response.status} {response.request.method} {response.url}")


def _visit(browser, storage_state: str, base_url: str, hash_route: str):
    ctx = browser.new_context(storage_state=storage_state)
    page = ctx.new_page()
    probe = _PageProbe(page)
    page.goto(f"{base_url.rstrip('/')}/#{hash_route}", wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(1500)  # SPA 라우팅 + 초기 데이터 fetch가 끝날 시간
    return ctx, page, probe


def test_user_console_home_loads_clean(browser, qa_session, smoke_base_url):
    """로그인한 계정이 사용자 콘솔 홈(`/me`)을 콘솔 오류·네트워크 오류 없이 그린다."""
    ctx, page, probe = _visit(browser, qa_session.storage_state, smoke_base_url, "/me")
    try:
        assert "/login" not in page.url, f"인증이 안 돼 로그인으로 튕겼다: {page.url}"
        assert page.inner_text("body").strip(), "홈 화면 본문이 비어 있다"
        assert probe.console_errors == [], f"콘솔 오류: {probe.console_errors}"
        assert probe.failed_responses == [], f"실패한 네트워크 요청: {probe.failed_responses}"
    finally:
        ctx.close()


def test_admin_console_dashboard_loads_clean(browser, qa_session, smoke_base_url):
    """`system_admin` 세션이 관리자 콘솔 대시보드를 콘솔·네트워크 오류 없이 그린다."""
    assert qa_session.role in {"system_admin", "admin", "operator"}, (
        f"기본 QA 계정 역할이 관리자 콘솔에 못 들어가는 역할이다: {qa_session.role}"
    )
    ctx, page, probe = _visit(browser, qa_session.storage_state, smoke_base_url, "/dashboard")
    try:
        assert "/login" not in page.url, f"인증이 안 돼 로그인으로 튕겼다: {page.url}"
        assert page.inner_text("body").strip(), "대시보드 본문이 비어 있다"
        assert probe.console_errors == [], f"콘솔 오류: {probe.console_errors}"
        assert probe.failed_responses == [], f"실패한 네트워크 요청: {probe.failed_responses}"
    finally:
        ctx.close()


def test_team_docs_list_loads_clean(browser, qa_session, smoke_base_url):
    """문서 목록 화면(`SEC-13` 부서 스코프 판정을 실제로 지나는 경로)이 정상 렌더된다."""
    ctx, page, probe = _visit(browser, qa_session.storage_state, smoke_base_url, "/team-docs")
    try:
        assert "/login" not in page.url, f"인증이 안 돼 로그인으로 튕겼다: {page.url}"
        assert page.inner_text("body").strip(), "문서 목록 본문이 비어 있다"
        assert probe.console_errors == [], f"콘솔 오류: {probe.console_errors}"
        assert probe.failed_responses == [], f"실패한 네트워크 요청: {probe.failed_responses}"
    finally:
        ctx.close()
