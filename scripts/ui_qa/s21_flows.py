"""S21 Flow 표 — **모으는 곳** (W14).

어휘는 `s21_kit.py`(그 앞은 `pilot_kit.py`), 실행은 `s21_e2e.py`, 각 영역의 Flow 는 아래
모듈들이다. S18 이 `pilot_flows.py` 에 쓴 규칙을 그대로 따른다 — 한 파일에 팔백 개를 넣으면
아무도 읽지 않는다.

`import` 순서가 곧 실행 순서다. 같은 화면의 Flow 는 붙여 둔다.
"""

from __future__ import annotations

from scripts.ui_qa.s21_kit import FLOWS, Flow  # noqa: F401

from scripts.ui_qa import s21_tickets  # noqa: F401,E402
from scripts.ui_qa import s21_knowledge  # noqa: F401,E402
from scripts.ui_qa import s21_project  # noqa: F401,E402
from scripts.ui_qa import s21_chat  # noqa: F401,E402
from scripts.ui_qa import s21_admin_reg  # noqa: F401,E402
from scripts.ui_qa import s21_gameroom  # noqa: F401,E402
from scripts.ui_qa import s21_me  # noqa: F401,E402
from scripts.ui_qa import s21_admin_audit  # noqa: F401,E402
from scripts.ui_qa import s21_admin_sched  # noqa: F401,E402
from scripts.ui_qa import s21_admin_org  # noqa: F401,E402
from scripts.ui_qa import s21_admin_ops  # noqa: F401,E402

__all__ = ["FLOWS", "Flow"]
