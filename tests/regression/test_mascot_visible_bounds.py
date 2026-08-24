"""클로비 자산의 **보이는 경계**가 잠금과 같은지 매번 다시 잰다 (지시 71 · PLAN «Clovi 계약»).

## 이 시험이 막는 것

화면은 «보이는 캐릭터 40px» 을 말하고 `Mascot.jsx` 가 자산의 여백 비율(`hfrac`)로 나눠 CSS
박스를 만든다. 그러니까 **자산을 다시 출력해 여백이 달라지면 화면의 크기가 조용히 바뀐다.**
PNG 를 갈아 끼운 사람은 자기가 크기를 바꿨다는 사실을 모르고, 화면은 여전히 «40px» 이라고
적혀 있다. 그래서 자산이 바뀌면 여기서 먼저 걸리게 한다.

동시에 이 시험은 **두 구현의 대조**다. 잠금은 Pillow 가 만들고(`scripts/gen_mascot_bounds.py`)
QA 프로브는 같은 정의를 브라우저 `<canvas>` 로 다시 구현한다(`scripts/ui_qa/mascot.py`).
둘이 갈라지면 «통과하지만 다른 것을 재는 검사» 가 된다 — 실제로 한 번 그랬다: 프로브가
알파 문턱 8 에 부유 픽셀 제거 없이 재고 있어서 `clovi-talking` 의 잉크 비율을 **1.000**
으로 봤다(참값 0.817). 그 22%p 만큼 «보이는 크기» 가 부풀어 정말 작은 마스코트가 통과한다.
정의 상수 둘을 여기서 함께 못 박는다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.gen_mascot_bounds import (  # noqa: E402
    ALPHA_MIN,
    FLOATING_ROW_FRACTION,
    JSON_OUT,
    JS_OUT,
    build,
    render_js,
    render_json,
    visible_bounds,
)

pytest.importorskip("PIL", reason="Pillow 는 개발 의존이다(requirements-dev.txt)")

LOGIN_LOCK = ROOT / "app" / "static" / "brand" / "login" / "mascot-lock.json"
PROBE = ROOT / "scripts" / "ui_qa" / "mascot.py"


def _lock() -> dict:
    return json.loads(JSON_OUT.read_text(encoding="utf-8"))


def test_lock_matches_the_assets_on_disk():
    """PNG 를 다시 재서 잠금과 대조한다. 자산이 바뀌면 여기서 걸린다."""
    lock = _lock()
    drift = []
    for name, want in lock["assets"].items():
        path = next(ROOT.glob(f"app/static/brand/*/{name}"), None)
        assert path is not None, f"{name}: 잠금에는 있는데 저장소에 없다"
        got = visible_bounds(path)
        for key in ("sha256", "size", "visibleBounds", "hfrac", "wfrac"):
            if got[key] != want[key]:
                drift.append(f"{name}.{key}: {want[key]} → {got[key]}")
    assert not drift, (
        "자산이 잠금과 다르다. 의도한 교체면 `python scripts/gen_mascot_bounds.py` 로 다시 잠그고,"
        " 화면 크기가 따라 바뀐다는 것을 알고 있어야 한다:\n" + "\n".join(drift)
    )


def test_generated_files_are_fresh():
    """생성물 둘이 지금 자산에서 나온 그대로인가 — `--check` 와 같은 판정이다."""
    doc = build()
    assert JSON_OUT.read_text(encoding="utf-8") == render_json(doc), (
        "mascot-bounds.json 이 낡았다 — python scripts/gen_mascot_bounds.py")
    assert JS_OUT.read_text(encoding="utf-8") == render_js(doc), (
        "frontend/src/ui/mascotBounds.js 가 낡았다 — python scripts/gen_mascot_bounds.py")


def test_every_runtime_pose_is_locked():
    """`lib/assets.js` 의 `MASCOT`·`ART` 가 가리키는 파일이 전부 잠겨 있는가.

    화면이 쓰는데 잠겨 있지 않은 자산은 `hfrac=1` 로 취급돼 **여백이 없다고** 계산된다 —
    그 자리만 조용히 작아진다.
    """
    assets_js = (ROOT / "frontend" / "src" / "lib" / "assets.js").read_text(encoding="utf-8")
    locked = set(_lock()["assets"])
    missing = []
    for line in assets_js.splitlines():
        if "${BRAND}/mascot/" in line or "${BRAND}/empty-states/" in line:
            name = line.rsplit("/", 1)[-1].split("`")[0]
            if name and name not in locked:
                missing.append(name)
    assert not missing, f"화면이 쓰는데 잠기지 않은 자산: {missing}"


def test_definition_matches_the_qa_probe():
    """잠금과 프로브가 **같은 정의**로 잰다.

    숫자를 두 벌로 적는 순간 한쪽만 고쳐지고, 그때 이 축은 통과하면서 다른 것을 잰다.
    """
    probe = PROBE.read_text(encoding="utf-8")
    assert f"INK_ALPHA_MIN = {ALPHA_MIN}" in probe, "프로브의 알파 문턱이 잠금과 다르다"
    assert f"INK_FLOATING_ROW_FRACTION = {FLOATING_ROW_FRACTION}" in probe, (
        "프로브의 부유 픽셀 문턱이 잠금과 다르다")


def test_floating_pixel_removal_actually_changes_a_known_asset():
    """반례. 부유 픽셀 제거를 빼면 `clovi-talking` 이 «여백이 없다» 고 나온다.

    이 시험이 없으면 누군가 문턱을 되돌려도 잠금이 조용히 다시 만들어질 뿐이다.
    """
    from PIL import Image  # noqa: PLC0415

    path = ROOT / "app" / "static" / "brand" / "mascot" / "clovi-talking.png"
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
        w, h = rgba.size
        naive = rgba.getchannel("A").point(lambda v: 255 if v >= 1 else 0)
        rows = naive.tobytes()
    naive_ys = [y for y in range(h) if rows[y * w:(y + 1) * w].count(255) > 0]
    naive_hfrac = (naive_ys[-1] - naive_ys[0] + 1) / h

    strict = visible_bounds(path)["hfrac"]
    assert naive_hfrac > 0.99, "이 자산이 더 이상 부유 픽셀을 갖지 않는다 — 반례를 다시 골라라"
    assert strict < 0.85, "부유 픽셀 제거가 동작하지 않는다"
    assert naive_hfrac - strict > 0.15, (
        f"두 정의가 이 자산에서 갈라져야 한다: 순진한 정의 {naive_hfrac:.3f} vs 잠금 {strict:.3f}")


def test_visible_bounds_sit_inside_the_login_lock_bounds():
    """로그인 정본 잠금과의 관계를 못 박는다 — **같은 값이 아니라 포함 관계**다.

    `mascot-lock.json` 의 `canonicalVisibleBounds` 는 실측하면 «알파가 0 만 아니면 잉크»
    (경계 배타 표기)다. 이쪽 잠금은 «알파 ≥ 128 이고 부유 행/열을 버린 뒤» 다. 두 정의는
    **다른 질문에 답한다**: 앞은 "이 PNG 에서 픽셀이 있는 범위" 이고 뒤는 "사람이 캐릭터라고
    보는 범위" 다. 히어로 자산은 아래쪽에 옅은 접지 그림자가 있어서 그 차이가 세로로 57px
    난다 — 그 그림자를 캐릭터로 세면 «보이는 크기» 가 그만큼 부푼다.

    그러니 요구할 것은 하나다: 엄격한 경계가 느슨한 경계 **안에** 있어야 한다. 밖으로
    나가면 어느 한쪽이 자산을 잘못 읽고 있는 것이다.
    """
    login = json.loads(LOGIN_LOCK.read_text(encoding="utf-8"))
    loose = login["canonicalVisibleBounds"]              # [left, top, right, bottom] 배타
    strict = _lock()["assets"][login["canonicalFile"]]["visibleBounds"]
    assert strict[0] >= loose[0] and strict[1] >= loose[1], f"{strict} 가 {loose} 밖으로 나갔다"
    assert strict[2] < loose[2] and strict[3] < loose[3], f"{strict} 가 {loose} 밖으로 나갔다"
    # 그리고 실제로 좁아야 한다 — 같으면 부유 픽셀 제거가 이 자산에서 아무 일도 안 한 것이다.
    assert loose[3] - strict[3] > 20, "히어로의 접지 그림자를 여전히 캐릭터로 세고 있다"
