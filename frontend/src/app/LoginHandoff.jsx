import React, { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { MascotPose } from "../ui/Mascot.jsx";

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
export const LOGIN_HANDOFF_KEY = "clovirassist_login_welcome";

/** 표식의 유효 시간. 이보다 오래된 표식은 이번 로그인의 것이 아니다. */
export const HANDOFF_FRESH_MS = 15000;

/* 너무 빨리 사라지면 연출이 아니라 깜빡임으로 보인다. 반대로 첫 화면이 끝내 안 와도
   여기서는 반드시 걷는다 — 연출이 화면을 붙잡고 있으면 그게 더 나쁜 첫인상이다. */
const MIN_VISIBLE_MS = 420;
const MAX_VISIBLE_MS = 2600;

/* 이 판이 서는 층. 폭죽도 같은 값에서 계산하므로 한 곳에만 적는다. */
const HANDOFF_Z_OVER_MODAL = 10;

/* 🔴 **폭죽은 이 판보다 위에 떠야 한다.**
 *
 * canvas-confetti 는 자기 캔버스를 `z-index: 100` 으로 만든다. 이 판은 `inset: 0` 인
 * **불투명** 면이고 층이 modal+10 = 1310 이라, 폭죽이 판 **뒤에서** 터지고 있었다.
 * 코드는 돌고 시험도 통과하는데 사람 눈에는 아무것도 안 보이는 상태다 — 사용자가
 * 「로그인 이후 폭죽이 사라졌다」고 한 것이 이것이다.
 *
 * 판이 걷힌 뒤에는 보이지 않느냐: 첫 화면이 빨리 오면 그렇다. 그런데 폭죽이 뜨는 자리는
 * 언제나 **차가운 첫 로드**다(방금 문서를 통째로 갈아 끼웠다). 인증 조회와 라우트 청크가
 * 늦으면 판은 상한(2.6초)까지 서 있고, 폭죽 수명(160틱 ≈ 2.7초)이 그 아래에서 다 지나간다.
 * 그래서 「빠르면 보이고 느리면 안 보이는」 연출이었다. 층을 올려 타이밍에서 떼어 낸다. */
const CONFETTI_Z = 1300 + HANDOFF_Z_OVER_MODAL + 10;

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
   CSP(script-src 'self')에 안전하다.
   
   **필요해질 때 받는다.** 예전 주석은 "이미 게임방이 쓰고 있어 초기 번들에 들어 있다"고
   적었지만 게임방은 지연 청크다 — 실제로는 이 정적 import 가 확정 화면 진입마다 받는
   초기 번들에 라이브러리를 밀어 넣고 있었다. 폭죽은 로그인 직후 한 번 쏘는 연출이라
   그 순간에 받으면 된다(사용자가 못박은 연출이므로 없애지는 않는다).
   
   받아 오지 못하면 조용히 넘어간다 — 축포가 안 떠서 로그인이 실패한 것처럼 보이면 안 된다. */
async function fireWelcomeConfetti() {
  let confetti;
  try {
    ({ default: confetti } = await import("canvas-confetti"));
  } catch (e) {
    return;
  }
  const base = {
    spread: 70, startVelocity: 42, ticks: 160,
    zIndex: CONFETTI_Z,
  };
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

  useEffect(() => {
    if (!open) return undefined;
    // 한 번 쓰면 지운다. 새로고침마다 축하하면 그건 축하가 아니라 소음이다.
    clearHandoff();
    fireWelcomeConfetti();

    const minTimer = window.setTimeout(() => setMinElapsed(true), MIN_VISIBLE_MS);
    const maxTimer = window.setTimeout(() => setOpen(false), MAX_VISIBLE_MS);
    return () => {
      window.clearTimeout(minTimer);
      window.clearTimeout(maxTimer);
    };
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
        zIndex: (t) => t.zIndex.modal + HANDOFF_Z_OVER_MODAL,
        display: "grid",
        placeItems: "center",
        // 정보만 전하고 조작은 아래 화면이 받는다. 연출이 클릭을 먹으면 첫인상이 더 나빠진다.
        pointerEvents: "none",
        bgcolor: "background.default",
        animation: `${rise} 260ms cubic-bezier(.2,.8,.2,1) both`,
      }}
    >
      <Box sx={{ display: "grid", justifyItems: "center", gap: 1.5, px: 3, textAlign: "center" }}>
        <MascotPose mode="welcome" place="loginHandoff" />
        {/* 크기만 h6 이고 문서 heading 은 아니다 — 1초짜리 인계 연출이 문서 구조에 제목을
            하나 끼워 넣으면 그 아래 첫 화면의 h1 이 h6 다음에 오는 꼴이 된다. 낭독은 이
            상자의 `role="status"` 가 이미 맡는다. */}
        <Typography variant="h6" component="p" fontWeight={800}>
          로그인되었습니다.
        </Typography>
        <Typography variant="body2" color="text.secondary">
          업무 공간을 준비하고 있습니다.
        </Typography>
        <LinearProgress aria-label="첫 화면을 준비하는 중" sx={{ width: 180, height: 4, borderRadius: 2, mt: 0.5 }} />
      </Box>
    </Box>
  );
}

export default LoginHandoff;
