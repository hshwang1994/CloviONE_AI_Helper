"""목록 상태 일곱 갈래의 서버 쪽 계약 (F4 · D-530).

- 기능 깃발이 꺼진 기능의 문은 상태 404 그대로(꺼진 기능은 없는 것이다) `feature_disabled` 코드를 보낸다. 목록 화면은 이 코드로
  「찾을 수 없습니다」 대신 「이 기능이 꺼져 있습니다」를 그린다(`frontend/src/ui/listState.js::DISABLED_CODES`). 깃발 문이 옛
  `NotFoundError` 로 되돌아가면 화면이 다시 「찾을 수 없습니다」로 뭉친다 — 소스를 훑어 막는다.
- 조직 정합성의 「문제 종류」 칸은 검사의 짧은 이름을 쓴다(검사 제목은 문장이라 칸에서 여섯 글자 뒤로 잘렸다).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISABLED_SENTENCE = re.compile(r"raise\s+(\w+)\(\s*\"[^\"]*기능이 비활성화되어 있습니다\.\"")


def test_feature_disabled_error_keeps_404_and_names_the_reason():
    from app.core.errors import FeatureDisabledError, NotFoundError

    assert issubclass(FeatureDisabledError, NotFoundError)
    assert FeatureDisabledError.status_code == 404
    assert FeatureDisabledError.code == "feature_disabled"
    assert FeatureDisabledError("x").message == "x"


def test_every_feature_flag_gate_raises_feature_disabled():
    found: dict[str, list[str]] = {}
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in DISABLED_SENTENCE.finditer(text):
            found.setdefault(m.group(1), []).append(str(path.relative_to(ROOT)))
    # 표본이 있어야 판정이 뜻이 있다 — 깃발 문은 문서 · 게시판 · 채팅 · 놀이(둘) · 팀 채팅 여섯이다.
    assert sum(len(v) for v in found.values()) >= 6, found
    assert set(found) == {"FeatureDisabledError"}, found


def test_frontend_disabled_codes_include_the_server_code():
    src = (ROOT / "frontend" / "src" / "ui" / "listState.js").read_text(encoding="utf-8")
    assert '"feature_disabled"' in src


def test_integrity_checks_have_short_names_for_the_filter_cell():
    from app.integrity.service import CHECKS

    shorts = [c.short for c in CHECKS]
    assert all(shorts), [c.key for c in CHECKS if not c.short]
    assert len(set(shorts)) == len(shorts), shorts
    for c in CHECKS:
        # 칸(XL 16rem)에 「짧은 이름 N건」이 한 줄로 선다 — 빈칸을 넣어 열한 글자를 넘지 않는다. 가운뎃점 · em 대시를 쓰지 않는다.
        assert len(c.short) <= 11, c.short
        assert "·" not in c.short and "—" not in c.short, c.short
        assert c.short != c.title
