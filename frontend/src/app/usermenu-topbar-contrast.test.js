import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ACCENT_PRESETS, createClovirTheme } from "../ui/theme.js";

/* 상단바 사용자 영역의 대비 — **실제 chrome 색**으로 잰다.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * `usermenu-topbar-gradient-contrast.test.js` 는 상단바가 보라 그라데이션이라는 전제로
 * "78% 지점 최악의 광원" 위 흰 글자 대비를 계산했다(WF7-K01). D-141 로 chrome 이 캔버스
 * 계열 **단색**이 되면서 그 전제가 사라졌고, 그 시험은 존재하지 않는 배경에 대해 계속
 * 초록불을 내고 있었다 — 그 사이 `UserMenu.jsx` 는 어두운 배경용 리터럴
 * (`rgba(0,0,0,.15)` 알약, `rgba(255,255,255,.22)` 아바타)을 그대로 들고 있어서, 밝은
 * 상단바에 검은 알약이 얹히고 아바타 이니셜은 흰 원 안 흰 글자가 됐다. **초록불이 결함을
 * 가린 자리**다.
 *
 * 그래서 여기서는 두 가지를 본다.
 *   1. 값이 **테마에서 온다** — 리터럴을 다시 박으면 실패한다(그게 원래 결함이었다).
 *   2. 그 조합의 대비가 강조색 프리셋 전부 × 두 모드에서 AA 를 넘는다.
 */

const AA_NORMAL_TEXT = 4.5;

/** `rgba(r,g,b,a)` 를 배경 hex 위에 합성한 hex. */
function over(tint, base) {
  const m = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)/.exec(String(tint));
  if (!m) throw new Error(`rgba 가 아니다: ${tint}`);
  const a = m[4] === undefined ? 1 : Number(m[4]);
  const [br, bg, bb] = rgb(base);
  const mix = (t, b) => Math.round(Number(t) * a + b * (1 - a));
  const hex = (v) => v.toString(16).padStart(2, "0");
  return `#${hex(mix(m[1], br))}${hex(mix(m[2], bg))}${hex(mix(m[3], bb))}`.toUpperCase();
}

/** 아바타 원이 실제로 앉는 면 전부 — shell 의 모든 stop × (AI Wash 있음/없음) × track. */
function avatarFaces(p) {
  const stops = [p.chrome.shell, ...(String(p.chrome.shellImage).match(/#[0-9A-Fa-f]{6}/g) || [])];
  const faces = [];
  for (const stop of stops) {
    faces.push(over(p.chrome.track, stop));
    faces.push(over(p.chrome.track, over(p.chrome.aiWash.match(/rgba\([^)]*\)/)[0], stop)));
  }
  return faces;
}

function channel(c8) {
  const c = c8 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
function rgb(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) throw new Error(`hex 가 아니다: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function luminance(hex) {
  const [r, g, b] = rgb(hex).map(channel);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

const SRC = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "UserMenu.jsx"),
  "utf-8",
);
const BUTTON_BLOCK = (() => {
  const start = SRC.indexOf("<Button");
  return SRC.slice(start, start + 2200);
})();

describe("사용자 영역은 chrome 색을 리터럴로 다시 박지 않는다", () => {
  it("어두운 배경 전제의 옛 리터럴을 스타일로 쓰지 않는다", () => {
    /* 이 값들이 **선언으로** 남아 있는 것이 원래 결함이었다 — 상단바가 밝아졌는데 값만
       안 따라왔다. 주석 안의 언급(왜 바꿨는지 설명)은 잡지 않는다: 그 설명이 사라지면
       다음 사람이 같은 리터럴을 "원래 그랬으니" 하고 되돌린다. */
    expect(BUTTON_BLOCK).not.toMatch(/(bgcolor|color|background)\s*:\s*"rgba\(/);
  });

  /* W2 재작성. 옛 단언은 아바타 원이 `background.plate` 를 쓰는지 확인했다 — 그때는
     chrome 이 캔버스 계열이라 그 값이 맞았다. D-179 로 셸이 인디고가 되면서 같은 값이
     **하우징에 뚫린 순백 원판**이 됐다(F-W1R-32 가 배포본 상단 우측 크롭에서 잡았다).
     즉 이 시험은 값이 배경을 따라오는지 보겠다고 만들어졌는데, 정작 자기가 고정한 값
     때문에 따라오지 못했다. 이제 **캔버스 면 토큰 자체를 금지**하고 chrome 반전 컨트롤
     토큰을 요구한다 — 셸 밝기가 또 바뀌어도 알파 흰빛은 같은 방향으로 따라온다. */
  it("호버·아바타가 chrome 반전 컨트롤 토큰을 쓴다 — 상단바 색이 바뀌면 같이 따라온다", () => {
    expect(BUTTON_BLOCK).toMatch(/bgcolor:\s*"sidebar\.hover"/);
    expect(BUTTON_BLOCK).toMatch(/bgcolor:\s*"sidebar\.track"/);
    expect(BUTTON_BLOCK).toMatch(/borderColor:\s*"sidebar\.edge"/);
  });

  it("아바타가 캔버스 면 토큰으로 되돌아가지 않는다 (그 되돌림이 곧 순백 원판이다)", () => {
    expect(BUTTON_BLOCK).not.toMatch(/bgcolor:\s*"background\.(plate|inset|canvas|paper)"/);
    expect(BUTTON_BLOCK).not.toMatch(/color:\s*"text\.secondary"/);
  });

  /* D-179 로 Shell 이 인디고가 되면서 계정 이름의 잉크도 chrome 잉크여야 한다.
     예전에는 `text.primary`(본문 잉크)였고, 그때는 상단바가 캔버스 계열이라 우연히 맞았다 —
     **값이 배경을 따라오지 않는다**는 같은 종류의 결함이 한 번 더 일어난 것이다. 그래서
     이제 **소스가 쓰는 토큰 이름을 시험이 읽어** 그 토큰으로 대비를 잰다. 배선과 측정이
     한 줄로 묶여, 다음에 배경이 또 바뀌면 대비 시험이 같이 빨개진다. */
  it("계정 이름이 chrome 잉크 토큰을 쓴다 (본문 잉크가 아니다)", () => {
    expect(BUTTON_BLOCK).toMatch(/color:\s*"sidebar\.text"/);
    expect(BUTTON_BLOCK).not.toMatch(/color:\s*"text\.primary"/);
  });
});

describe("사용자 영역 대비 — 강조색 프리셋 전부 × 두 모드", () => {
  const cases = [];
  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) cases.push([mode, accent]);
  }

  it.each(cases)("%s / accent=%s — 계정 이름이 상단바 위에서 AA", (mode, accent) => {
    const p = createClovirTheme(mode, accent).palette;
    const ratio = contrast(p.sidebar.text, p.sidebar.bg);
    expect(ratio, `이름 ${p.sidebar.text} on chrome ${p.sidebar.bg} = ${ratio.toFixed(2)}`)
      .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  /* 아바타 면은 이제 **알파**다(`chrome.track`). 알파 면의 대비는 그 아래 깔린 것에
     달려 있으므로 한 값을 재는 것으로는 부족하다 — 아바타는 상단바의 AI 앵커 안에 살고,
     그 앵커는 Gradient stop 전부 위에 AI Wash 를 한 겹 더 얹는다. 그래서 실제로 밟히는
     합성 순서 그대로(shell stop → aiWash → track) 쌓아 놓고 **최악값**을 잰다.
     D-179 «Wash 위 잉크 하드 룰» 이 이 영역의 잉크를 `onShell` 하나로 못박은 근거가
     바로 이 계산이다. */
  it.each(cases)("%s / accent=%s — 아바타 이니셜이 AI 앵커 안 모든 합성면에서 AA", (mode, accent) => {
    const p = createClovirTheme(mode, accent).palette;
    const faces = avatarFaces(p);
    expect(faces.length, "합성면을 하나도 못 만들었다 — 토큰 이름이 바뀌었는지 확인하라")
      .toBeGreaterThanOrEqual(8);
    for (const face of faces) {
      const ratio = contrast(p.sidebar.text, face);
      expect(ratio, `이니셜 ${p.sidebar.text} on ${face} = ${ratio.toFixed(2)}`)
        .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    }
  });

  /* 아바타 **원 자체**의 대비는 재지 않는다. `aria-hidden` 인 장식 원이고 상태를 알리는
     컨트롤이 아니다(WCAG 1.4.11 의 대상이 아니다) — 읽어야 하는 것은 그 안의 이니셜이고
     위 시험이 그것을 잰다. 원을 chrome 에서 떼어 놓는 하이라인은 시각적 마감이라 값만
     토큰(`sidebar.line`)에서 오게 하고(위 배선 시험), 비율을 못박지 않는다. */
});
