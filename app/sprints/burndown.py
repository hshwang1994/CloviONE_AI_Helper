"""스프린트 번다운 — 주 범위 티켓 DTO 만으로 그리는 소진 곡선 (순수 함수, DB·외부 호출 없음).

**이 곡선이 무엇이고 무엇이 아닌지부터.** 우리에게는 '언제 완료됐는지'가 없다. `ticket_cache`
에 있는 시각은 Notion 의 생성·최종수정 시각뿐이고, 그건 상태가 '완료'로 바뀐 시점이 아니다
(제목만 고쳐도 갱신된다). 그래서 교과서적인 '날짜별 실제 잔여 이력'은 지금 데이터로는 만들 수
없다. 없는 이력을 last_edited 로 추정해 그리면 그건 차트가 아니라 창작이다.

대신 **오늘 시점의 사실만으로** 두 선을 그린다. 둘 다 마감일이 축이다:

  * `planned` — 그날 이후로 마감이 남아 있는 업무량(취소 제외). 팀이 이 주를 어떻게 배치했는지.
  * `open`    — 그중 **아직 완료되지 않은** 것만. 지금 남아 있는 일이 어떻게 배치돼 있는지.

두 선의 세로 간격 = 이미 끝낸 일(그날 이후 마감분). 간격이 넓을수록 앞서 있고, 두 선이 붙어
있으면 그 구간의 일이 통째로 남아 있다는 뜻이다. 마지막 점(end)에서 둘 다 0으로 떨어지는 것은
"이 주에 마감인 일은 이 주에 끝난다"는 정의에서 오는 것이지 성과가 아니다 — 화면 문구가 이
뜻을 그대로 말한다.

마감일이 없는 티켓은 어느 날짜에도 놓을 수 없어 두 선에서 모두 빠진다. 주 범위 조회
(`list_for_period`)가 마감일로 거르므로 실제로는 거의 나오지 않지만, 없는 값을 start 로
밀어 넣어 첫날 막대를 부풀리지 않는다.
"""

from __future__ import annotations

from datetime import date, timedelta

STATUS_DONE = "완료"
STATUS_CANCELLED = "취소"

# 점 개수 상한. 스프린트는 한 주(8점)지만 임의 범위를 넘길 수 있는 API 라, 범위가 크면
# 점이 수백 개가 되어 SVG 가 선 하나로 뭉개진다. 상한을 넘으면 균등 간격으로 솎는다.
MAX_POINTS = 32


def _days(start: str, end: str) -> list[str]:
    """[start, end] 양끝 포함 날짜 목록. end 를 포함하는 이유: 마지막 점이 0으로 내려앉는
    모습이 있어야 '소진'으로 읽힌다(마지막 날에서 끊으면 그날 마감분만큼 떠 있는 채로 끝난다)."""
    try:
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end)
    except ValueError:
        return []
    if d1 < d0:
        return []
    span = (d1 - d0).days
    if span + 1 <= MAX_POINTS:
        step = 1
    else:
        step = span // (MAX_POINTS - 1) + 1
    out = [(d0 + timedelta(days=i)).isoformat() for i in range(0, span + 1, step)]
    if out[-1] != d1.isoformat():
        out.append(d1.isoformat())
    return out


def build_burndown(tickets, *, start: str, end: str) -> dict:
    """`{"total_est_wd": float, "points": [{"date", "planned", "open"}, …]}`.

    `tickets` 는 TicketDTO 들이다(저장소 seam 을 통과해 온 값 — 여기서는 소스가 무엇인지 모른다).
    """
    rows = [
        (t.due, float(t.est_wd or 0), t.status)
        for t in tickets
        if t.status != STATUS_CANCELLED and t.due
    ]
    total = round(sum(est for _, est, _ in rows), 1)
    points = []
    for day in _days(start, end):
        planned = 0.0
        still_open = 0.0
        for due, est, status in rows:
            if due < day:
                continue
            planned += est
            if status != STATUS_DONE:
                still_open += est
        points.append({"date": day, "planned": round(planned, 1), "open": round(still_open, 1)})
    return {"total_est_wd": total, "points": points}
