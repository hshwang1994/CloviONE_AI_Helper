import React, { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import confetti from "canvas-confetti";
import { MascotPose } from "../ui/Mascot.jsx";
import { prefersReducedMotion } from "../ui/motion.js";

/* 로그인 화면과 첫 화면을 잇는 인계 연출 (12단계).
 *
 * ── 무엇이 문제였나 ─────────────────────────────────────────────────────────
 * 로그인은 서버 렌더 페이지(app/templates_html/login.html)이고 첫 화면은 SPA 다. 성공하면
 * 브라우저가 문서를 통째로 갈아 끼운다 — 클로비가 웃는 순간 화면이 하얗게 비고, 인증 조회와
 * 라우트 청크를 받는 동안 아무 말이 없다가 갑자기 목록이 나타난다. "뚝 끊긴다" 가 그것이다.
 *
 * ── 어떻게 잇는가 ───────────────────────────────────────────────────────────
 * login.js 가 이동 **직전에** sessionStorage 에 표식(시각 하나)을 남긴다. 새 문서가 뜨면
 * 이 컴포넌트가 그 표식을 보고, 로그인 화면에서 시작된 연출을 여기서 이어받아 끝낸다.
 *
 * 왜 URL 이 아니라 sessionStorage 인가: next 경로는 알림 딥링크가 쓰는 계약이라 쿼리를
 * 하나 더 붙이면 그 경로가 오염된다. 표식은 탭 하나에만 살고, 한 번 읽으면 지운다.
 *
 * ── 축하하면 안 되는 자리 ───────────────────────────────────────────────────
 * 표식은 **로그인이 실제로 성공했을 때만** 생긴다. 비밀번호 오류·잠긴 계정·만료된 세션은
 * 이동 자체를 하지 않으므로 여기까지 오지 않는다. 비밀번호 강제 변경도 제외한다 —
 * 그 사람은 아직 업무 공간에 들어온 게 아니다.
 * 그래도 표식이 남아 떠도는 경우(탭을 오래 열어 둔 채 뒤로 가기 등)를 대비해 신선도를 본다.
 */

/** 로그인 페이지와 공유하는 열쇠. app/static/js/login.js 가 같은 문자열을 쓴다 —
 *  두 층이 각자 문자열을 들고 있으면 한쪽만 바뀌는 순간 조용히 끊긴다.
 *  login-first-impression.test.jsx 가 두 값이 같은지 확인한다. */
export const LOGIN_HANDOFF_KEY = "clovirone_login_welcome";

/** 표식의 유효 시간. 이보다 오래된 표식은 이번 로그인의 것이 아니다. */
export const HANDOFF_FRESH_MS = 15000;

/* 너무 빨리 사라지면 연출이 아니라 깜빡임으로 보인다. 반대로 첫 화면이 끝내 안 와도
   여기서는 반드시 걷는다 — 연출이 화면을 붙잡고 있으면 그게 더 나쁜 첫인상이다. */
const MIN_VISIBLE_MS = 420;
const MAX_VISIBLE_MS = 2600;

const rise = keyframes`
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
`;

/** 이번 로드가 '방금 로그인한 직후'인가. 읽기만 하고 지우지는 않는다 —
 *  React 18 StrictMode 는 상태 초기화 함수를 두 번 부르므로, 읽는 자리에서 지우면
 *  두 번째 호출이 표식을 못 보고 연출이 통째로 사라진다. 지우는 것은 effect 에서 한다. */
function hasFreshHandoff() {
  try {
    const raw = window.sessionStorage.getItem(LOGIN_HANDOFF_KEY);
    if (!raw) return false;
    const at = Number(raw);
    if (!Number.isFinite(at)) return false;
    const age = Date.now() - at;
    // 음수(기기 시계가 뒤로 간 경우)도 이번 로그인의 것으로 보지 않는다.
    return age >= 0 && age < HANDOFF_FRESH_MS;
  } catch (e) {
    // 시크릿 모드/저장소 차단 — 연출이 없을 뿐 로그인은 정상이다.
    return false;
  }
}

function clearHandoff() {
  try {
    window.sessionStorage.removeItem(LOGIN_HANDOFF_KEY);
  } catch (e) {
    /* 저장소가 막혀 있으면 애초에 표식도 없다 */
  }
}

/* 환영 축포. canvas-confetti 는 CSSOM 개별 속성으로 캔버스를 꾸미고 기본은 워커를 쓰지 않아
   CSP(script-src 'self')에 안전하다. 이미 게임방이 쓰고 있어 초기 번들에 들어 있는 코드라
   여기서 새로 받는 바이트가 없다 — 느린 회선에서 첫 렌더를 막지 않는다. */
function fireWelcomeConfetti() {
  const base = { spread: 70, startVelocity: 42, ticks: 160, disableForReducedMotion: true };
  confetti({ ...base, particleCount: 70, origin: { y: 0.5 } });
  window.setTimeout(() => confetti({ ...base, particleCount: 40, angle: 62, origin: { x: 0.1, y: 0.62 } }), 130);
  window.setTimeout(() => confetti({ ...base, particleCount: 40, angle: 118, origin: { x: 0.9, y: 0.62 } }), 240);
}

/**
 * @param {boolean} ready 첫 화면이 그릴 준비가 됐는가(인증 조회가 끝났는가).
 */
export function LoginHandoff({ ready = true }) {
  const [open, setOpen] = useState(hasFreshHandoff);
  const [minElapsed, setMinElapsed] = useState(false);
  // 렌더 중에 읽는다. 마운트 이후에 이 값이 바뀌어도 이 연출은 1초 안에 끝나므로
  // 구독할 이유가 없다(구독하면 화면마다 리스너가 하나씩 는다).
  const reduced = prefersReducedMotion();

  useEffect(() => {
    if (!open) return undefined;
    // 한 번 쓰면 지운다. 새로고침마다 축하하면 그건 축하가 아니라 소음이다.
    clearHandoff();
    // 움직임에 민감한 사람에게 폭죽은 고통이다. 여기서 아예 쏘지 않는다 —
    // JS 로 그리는 캔버스에는 theme.js 의 전역 CSS 규칙이 닿지 않는다.
    if (!reduced) fireWelcomeConfetti();

    const minTimer = window.setTimeout(() => setMinElapsed(true), MIN_VISIBLE_MS);
    const maxTimer = window.setTimeout(() => setOpen(false), MAX_VISIBLE_MS);
    return () => {
      window.clearTimeout(minTimer);
      window.clearTimeout(maxTimer);
    };
    // reduced 는 마운트 시점 값 하나만 쓴다(위 주석).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (open && ready && minElapsed) setOpen(false);
  }, [open, ready, minElapsed]);

  if (!open) return null;

  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        position: "fixed",
        inset: 0,
        zIndex: (t) => t.zIndex.modal + 10,
        display: "grid",
        placeItems: "center",
        // 정보만 전하고 조작은 아래 화면이 받는다. 연출이 클릭을 먹으면 첫인상이 더 나빠진다.
        pointerEvents: "none",
        bgcolor: "background.default",
        animation: `${rise} 260ms cubic-bezier(.2,.8,.2,1) both`,
      }}
    >
      <Box sx={{ display: "grid", justifyItems: "center", gap: 1.5, px: 3, textAlign: "center" }}>
        <MascotPose mode="welcome" size={132} />
        <Typography variant="h6" fontWeight={800}>
          로그인되었습니다
        </Typography>
        <Typography variant="body2" color="text.secondary">
          업무 공간을 준비하고 있습니다
        </Typography>
        {/* 진행 막대는 움직임 그 자체라 동작 줄이기에서는 그리지 않는다. 없어지는 것이
            아니라 위의 문구가 같은 정보를 대신 전한다(사라지는 게 아니라 대체다). */}
        {reduced ? null : (
          <LinearProgress aria-label="첫 화면을 준비하는 중" sx={{ width: 180, height: 4, borderRadius: 2, mt: 0.5 }} />
        )}
      </Box>
    </Box>
  );
}

export default LoginHandoff;
