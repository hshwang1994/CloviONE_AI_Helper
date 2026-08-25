"""Pilot 8 Archetype 의 Flow 표 — **모으는 곳** (W8 · S18).

어휘는 `pilot_kit.py`, 실행은 `pilot_e2e.py`, 각 원형의 Flow 는 아래 모듈들이다.
한 파일에 235개를 넣으면 아무도 읽지 않는다 — 원형 단위로 가른다.

    pilot_b1   B1 Dashboard          /me + 위젯 둘
    pilot_b2   B2 List + DataGrid    /projects · /users · 일괄 처리
    pilot_b3b4 B3 Reading · B4 Work  /board/:id · /tickets/:id
    pilot_b7b8 B7 Report · B8 Ops    /sprint · /jobs
    pilot_b9   B9 Chat               /chat-rooms + 대화 판
    pilot_b10  B10 Settings          /settings 와 그 탭들
    pilot_b11  B11 Split view        /organizations

`import` 순서가 곧 실행 순서다. 화면을 오가는 비용이 있으므로 같은 화면의 Flow 는 붙여
둔다 — 엔진은 `route` 가 비면 앞 Flow 가 남긴 화면에서 이어 간다.
"""

from __future__ import annotations

from scripts.ui_qa.pilot_kit import FLOWS, Flow  # noqa: F401

from scripts.ui_qa import pilot_b1  # noqa: F401,E402
from scripts.ui_qa import pilot_b2  # noqa: F401,E402
from scripts.ui_qa import pilot_b3b4  # noqa: F401,E402
from scripts.ui_qa import pilot_b7b8  # noqa: F401,E402
from scripts.ui_qa import pilot_b9  # noqa: F401,E402
from scripts.ui_qa import pilot_b10  # noqa: F401,E402
from scripts.ui_qa import pilot_b11  # noqa: F401,E402

__all__ = ["FLOWS", "Flow"]
