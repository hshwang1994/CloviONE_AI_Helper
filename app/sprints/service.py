"""주간 창 계산 — **스프린트가 아니다.**

## 이 모듈에 남은 것 하나

`default_sprint_window` 뿐이다. 「이번 주 월요일 ~ 다음 주 월요일」을 구하는 산수이고,
홈·주간 리포트·비서가 그것을 쓴다(`app/home/service.py` · `app/projects/weekly.py` ·
`app/assistant/facts.py`).

## 무엇이 없어졌나 (지시 4 회차)

`build_sprint_summary` 와 `/api/sprint/summary` 를 걷었다. 그 함수는 「그 주에 마감인
티켓 묶음」을 스프린트라고 불렀는데, 이 제품에는 이제 **회차라는 실체**가 있다
(`sprints` 표). 둘을 함께 두면 「스프린트」에 뜻이 둘이 되고, 두 화면이 같은 말로 다른
것을 세게 된다 — 상태 어휘에서 「백로그」를 상태로 두지 않기로 한 것과 같은 판단이다
(D-349).

회차를 아는 회의 화면은 `app/work/meeting.py` 다. 이 파일의 이름에 아직 「sprint」가
남아 있는 것은 위 한 함수의 호출부 넷을 건드리지 않기 위해서다 — 그 함수가 답하는
질문은 「이번 주가 언제부터 언제까지인가」이지 「회차가 무엇인가」가 아니다.
"""

from __future__ import annotations

from datetime import date, timedelta


def default_sprint_window(today: date) -> tuple[str, str]:
    """이번 주 월요일 ~ 다음 주 월요일(배타적). today 는 Asia/Seoul 기준 날짜여야 한다(주 판정)."""
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat(), (monday + timedelta(days=7)).isoformat()
