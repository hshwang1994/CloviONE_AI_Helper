/* Signal — 상태와 직교하는 축 (D-349).
 *
 * ## 두 축을 섞지 않는다
 *
 * **Status** 는 「업무가 어디까지 왔는가」이고 티켓 하나가 정확히 하나를 갖는다:
 * 계획 · 진행 중 · 검증 · 완료 · 보류 · 취소.
 *
 * **Signal** 은 「그 진행에 무슨 일이 있는가」이고 동시에 여러 개가 켜진다:
 * 이슈 있음 · 차단됨 · 지연.
 *
 * 예전에는 `이슈` 가 Status 였다. 그래서 이슈가 생긴 티켓은 자기가 어디까지 왔는지를
 * 잃었고, 「진행 중인데 막혀 있다」를 적을 자리가 없었다. 서버 쪽 같은 계약은
 * `app/work/workflow.py` 다.
 *
 * ## 왜 `지연` 만 여기서 계산하는가
 *
 * 셋 중 둘은 서버가 싣는 값이고(`issue` · `blocked`) 지연은 아니다. 지연은 **오늘이
 * 며칠인지**에 달린 값이라 목록 응답에 실어 캐시하는 순간 자정에 틀린다.
 *
 * 그렇다고 화면이 상태 이름을 적지도 않는다. 「끝났는가」의 판정은 서버가 준다 —
 * `/api/work/statuses` 의 `terminal` 이 그 값이고, 이 파일은 그 목록을 받아서 쓴다.
 * 상태가 하나 늘거나 이름이 바뀌어도 이 파일은 안 고친다.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api.js";

/** 신호 셋의 표시 이름과 톤. **같은 의미는 제품 전체에서 같은 말과 같은 색이다.**
 *
 * 셋은 **서로 다른 색**이다. 예전에는 차단과 지연이 둘 다 빨강이라 표에서 구분이 안 됐다.
 * 빨강은 지금 막힌 것(차단), 주황은 시간이 지난 것(지연), 보라는 알고 있어야 하는 것(이슈). */
export const SIGNALS = {
  issue: { key: "issue", label: "이슈 있음", tone: "purple" },
  blocked: { key: "blocked", label: "차단됨", tone: "danger" },
  overdue: { key: "overdue", label: "지연", tone: "warn" },
};

export const SIGNAL_ORDER = ["blocked", "overdue", "issue"];

/** 'YYYY-MM-DD' 로 읽은 오늘. ISO 문자열은 사전순 비교가 곧 날짜순 비교라 파싱이 필요 없다. */
export function todayIso(now) {
  const d = now instanceof Date ? now : new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** `/api/work/statuses` 응답 → 종료 상태 key 집합. 목록이 없으면 **빈 집합**이다.
 *
 * 빈 집합이면 완료 티켓도 지연으로 보일 수 있다. 그래도 상태 이름을 여기 적는 것보다
 * 낫다 — 적어 두면 어휘가 바뀐 날 이 파일만 옛 이름으로 남고, 그 어긋남은 아무 오류도
 * 안 낸다. 어휘 질의는 5분 캐시라 실제로 비는 창은 첫 로드의 한순간뿐이다. */
export function terminalKeys(statusesBody) {
  const rows = statusesBody && Array.isArray(statusesBody.statuses) ? statusesBody.statuses : [];
  return new Set(rows.filter((s) => s && s.terminal === true).map((s) => s.key));
}

/** 마감이 지났는데 아직 안 끝났는가.
 *
 * 끝난 일은 마감이 지났어도 지연이 아니다 — 지난주에 끝낸 일이 오늘 빨갛게 뜨면 그
 * 색은 아무 행동도 요구하지 않고, 요구하지 않는 색은 곧 무시된다.
 * 서버 쪽 같은 규칙은 `app/work/workflow.py::is_overdue` 다. */
export function isOverdue(ticket, { today, terminal }) {
  const t = ticket || {};
  const due = t.due || t.due_date || null;
  if (!due || !today) return false;
  if (terminal && terminal.has(t.status)) return false;
  return String(due).slice(0, 10) < today;
}

/** 이 티켓에 켜져 있는 신호 전부. 순서는 급한 것부터다.
 *
 * REAUDIT A8 — `blocked_reason` 은 API 가 이미 싣는데(`app/tickets/service.py`) 어느
 * 화면도 안 썼다. `SIGNALS.blocked` 는 표에 하나뿐인 공유 어휘 항목이라(모든 차단 티켓이
 * 같은 참조를 본다) 거기 직접 사연을 못 싣는다 — 차단인 자리만 사연을 얹은 새 객체로
 * 복제해서 돌려준다. 사연이 없으면(옛 데이터) 공유 항목을 그대로 준다. */
export function ticketSignals(ticket, { today, terminal }) {
  const t = ticket || {};
  const on = {
    blocked: !!t.blocked,
    overdue: isOverdue(t, { today, terminal }),
    issue: !!t.issue,
  };
  return SIGNAL_ORDER.filter((k) => on[k]).map((k) =>
    (k === "blocked" && t.blocked_reason) ? { ...SIGNALS[k], reason: t.blocked_reason } : SIGNALS[k]
  );
}

/** 화면이 쓰는 입구 하나. 어휘 질의는 `useWorkStatuses` 와 **같은 키**라 요청은 한 번이다.
 *
 * 돌려주는 것이 배열이 아니라 함수인 이유: 목록 한 화면에 티켓이 수백 건이고, 행마다
 * 훅을 부를 수는 없다. 화면이 이 함수를 한 번 받아 행마다 부른다. */
export function useTicketSignals(todayOverride) {
  const { data } = useQuery({
    queryKey: ["work", "statuses"],
    queryFn: () => api("/api/work/statuses"),
    retry: false,
    staleTime: 300000,
  });
  // 함수 신원을 어휘 응답에 묶는다 — 매 렌더 새 함수·새 Set 를 돌려주면 이 함수를
  // prop 으로 받는 목록 화면들의 memo 가 전부 헛돈다(카드 수백 장이 매번 다시 계산).
  // 「오늘」은 기본으로 마운트 시점 기준이다 — 서버가 오늘을 함께 내려주는 화면
  // (스프린트 회의)은 `todayOverride` 로 그 값을 쓴다: 같은 응답이 만든 「지연」
  // 목록과 행의 지연 표식이 다른 시계를 보면 한 화면 안에서 서로 모순난다.
  return React.useMemo(() => {
    const terminal = terminalKeys(data);
    const today = todayOverride || todayIso();
    return (ticket) => ticketSignals(ticket, { today, terminal });
  }, [data, todayOverride]);
}
