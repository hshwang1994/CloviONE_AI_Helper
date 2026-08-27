import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { ACCENT_PRESETS, createClovirTheme } from "../ui/theme.js";

/* qa-contract-change: 상단바 계정 아바타가 「이니셜이 담긴 트랙색 원」에서 「사진이나 이 사람의 기본 아바타 그림」으로 바뀌었다(Avatar 시스템). 그래서 이니셜의 대비를 재던 단언들은 잴 대상이 사라졌다 — 사용자가 올린 사진의 명도를 제품이 정할 수 없고, 정하려 들면 사진을 덧칠하게 된다. 면 토큰을 요구하던 단언도 같은 이유로 원의 **둘레** 토큰 단언으로 옮겼다. 계정 이름의 대비 단언은 한 줄도 줄이지 않았다.
 *
 * 상단바 사용자 영역의 대비 — **실제 chrome 색**으로 잰다.
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

  /* W2 재작성 · 이번 회차 재정정. 옛 단언은 아바타 **면**이 chrome 반전 트랙인지 봤다 —
     그때 그 원 안에는 이니셜 한 글자가 있었고, 면과 잉크의 대비가 읽기의 전부였다.
     지금 그 자리에는 사진이나 이 사람의 기본 아바타가 선다(`ui/UserAvatar.jsx`).
     면이 아니라 그림이라 트랙색을 요구할 수 없고, 요구하면 그림 위에 색을 덧칠하게 된다.
     남은 계약은 **원의 둘레**다: 밝은 그림이 밝은 셸에 얹히면 원의 경계가 사라진다. */
  it("호버가 chrome 반전 컨트롤 토큰을 쓴다 — 상단바 색이 바뀌면 같이 따라온다", () => {
    expect(BUTTON_BLOCK).toMatch(/bgcolor:\s*"sidebar\.hover"/);
  });

  it("아바타 둘레가 chrome 테두리 토큰에서 온다", () => {
    // `palette.sidebar` 가 없는 격리 렌더에서는 캔버스 구분선으로 떨어진다 — 그 폴백이
    // 있어야 이 부품을 테마 없이 그리는 시험들이 안 죽는다. 앞엣것이 정본이다.
    expect(BUTTON_BLOCK).toMatch(/palette\.sidebar \|\| t\.palette\)\.edge/);
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

  /* 🔴 **이니셜 대비 시험은 여기서 은퇴한다.** 잴 대상이 없어졌기 때문이다 — 아바타
     원 안에는 더 이상 글자가 없고, 사진이거나 이 사람의 기본 아바타 그림이다.
     그림의 대비를 AA 로 재는 것은 뜻이 없다: 사용자가 올린 사진의 명도를 제품이 정할 수
     없고, 정하려 들면 사진을 덧칠하게 된다.
     아바타 **원 자체**의 대비도 재지 않는다. 상태를 알리는 컨트롤이 아니라 사람을
     가리키는 그림이고(WCAG 1.4.11 의 대상이 아니다), 그 옆에는 언제나 계정 이름이 있다 —
     위 시험이 그 이름의 대비를 잰다. 원이 셸에 묻히지 않게 하는 것은 둘레 한 줄이고,
     그 값이 chrome 토큰에서 오는지는 배선 시험이 본다. */
});
