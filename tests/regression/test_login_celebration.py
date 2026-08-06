"""로그인 성공 연출이 **끝까지 재생된 뒤** 이동하는가 (P1).

## 무엇이 문제였나

성공 표정과 배지는 `clovi-login.js` 의 `markSuccess()` 가 켜는데, 그게 `beforeunload` 에만
걸려 있었다. 그 시점은 이미 브라우저가 다음 문서를 가지러 간 뒤라, 760ms 짜리 `eye-success`
애니메이션이 뜨자마자 화면이 갈렸다. 사용자가 "로그인 이후 축하 애니메이션이 사라졌다" 고
지적한 것이 이것이다.

## 왜 텍스트 검사인가

실제로는 헤드리스 브라우저로 재 봤고(성공 연출 166ms 시작 → 891ms 유지 후 이동), 760ms 를
다 보여 주는 것을 확인했다. 그런데 그 측정을 CI 에 두면 타이밍에 흔들려 간헐적으로 깨진다.

여기서 고정하는 것은 **계약**이다: 이동 직전에 연출을 기다린다, 그리고 그 대기에 상한이
있다. 둘 중 하나가 사라지면(누가 `await` 를 지우거나 상한을 없애면) 여기서 잡힌다.
상한이 중요한 이유는 연출이 실패해도 로그인이 막히면 안 되기 때문이다 — 연출은 있으면
좋은 것이지 필수가 아니다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

STATIC = Path(__file__).resolve().parents[2] / "app" / "static" / "js"


def test_login_waits_for_the_celebration_before_navigating():
    src = (STATIC / "login.js").read_text(encoding="utf-8")

    assert "cloviLogin.celebrate" in src, (
        "이동 전에 성공 연출을 부르지 않는다 — 연출이 뜨자마자 화면이 갈린다"
    )
    # 연출을 기다린 **뒤** 이동해야 한다. 순서가 뒤집히면 기다리는 의미가 없다.
    wait_at = src.index("Promise.race")
    nav_at = src.index("window.location.href =", wait_at)
    assert wait_at < nav_at, "연출을 기다리기 전에 이동한다"


def test_the_wait_is_capped():
    src = (STATIC / "login.js").read_text(encoding="utf-8")
    assert "CELEBRATE_CAP_MS" in src, (
        "대기에 상한이 없다 — 연출이 실패하면 로그인이 영영 안 끝난다"
    )
    assert "Promise.race" in src, "상한과 경주시키지 않으면 상한이 무의미하다"


def test_celebrate_is_exposed_and_respects_reduced_motion():
    src = (STATIC / "clovi-login.js").read_text(encoding="utf-8")

    assert "celebrate: celebrate" in src, "login.js 가 부를 수 있게 노출돼 있어야 한다"
    # 동작 줄이기를 켠 사용자에게는 기다리지 않는다 — 그 설정의 뜻은 "연출을 보고 싶지
    # 않다" 이므로, 보여 주지도 않으면서 붙잡아 두면 그냥 느린 로그인이다.
    assert "prefers-reduced-motion" in src, (
        "동작 줄이기 설정을 무시하면 그 사용자는 이유 없이 더 오래 기다린다"
    )


def test_beforeunload_fallback_survives():
    """`celebrate()` 를 못 부른 경로에서도 마지막 모습이 '로딩 중'으로 남지 않아야 한다."""
    src = (STATIC / "clovi-login.js").read_text(encoding="utf-8")
    assert 'addEventListener("beforeunload", markSuccess)' in src
