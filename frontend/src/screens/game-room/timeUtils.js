import { useEffect, useState } from "react";

/* 게임방 시간 유틸 — GameRoom.jsx 구조 분리(2026-08)로 값 변경 없이 이 파일로 옮겼다.
 * 백엔드는 UTC를 tz 표기 없는 isoformat으로 준다(예: "2026-07-29T05:30:00"). Z를 붙여 UTC로
 * 파싱해야 브라우저가 로컬(KST)로 오해하지 않는다(lib/format.js와 같은 규칙). 이걸 빼먹으면
 * 마감이 9시간 과거로 계산돼 카운트다운이 즉시 0이 되고 가위바위보가 바로 자동 처리되는 버그가 난다. */
export function toDate(iso) {
  if (!iso) return null;
  const s = String(iso);
  const norm = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(norm);
  return Number.isNaN(d.getTime()) ? null : d;
}

// 채팅 시각(HH:MM). created_at는 UTC — UTC로 파싱한 뒤 브라우저 로컬 시간으로 표시.
export function fmtTime(iso) {
  const d = toDate(iso);
  if (!d) return "";
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

// 서버가 준 마감(UTC ISO)까지 남은 초. 없으면 null. 0.25초마다 다시 계산해 부드럽게 줄어든다.
export function useCountdown(deadline) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!deadline) return undefined;
    const t = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [deadline]);
  if (!deadline) return null;
  const d = toDate(deadline);
  if (!d) return null;
  return Math.max(0, Math.ceil((d.getTime() - nowMs) / 1000));
}
