import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, it, expect } from "vitest";

import { createClovirTheme, ACCENT_PRESETS } from "./theme.js";

/* CTR-01/CTR-02/CTR-04: MuiLink(테마 기본 색)와 ConsoleSwitch(AppShell.jsx)의 활성 탭
 * 글자색이 배경과 WCAG AA(4.5:1) 대비를 만족하는지 확인한다.
 *
 * 팔레트 값(theme.palette.primary.dark 등)을 테스트 안에서 독립적으로 다시 계산하면 안
 * 된다 — 그 값 자체는 배선(MuiLink가 실제로 그 값을 쓰는지)과 무관하게 항상 존재하므로,
 * 배선이 빠진 회귀(원래 버그: MuiLink가 color를 안 줘서 MUI 기본값 primary.main으로
 * 렌더된 것)를 절대 못 잡는다(1차 시도에서 실제로 이 실수를 했다 — stash로 되돌려도
 * 통과해서 직접 확인함). 그래서 theme.components.MuiLink.styleOverrides.root.color처럼
 * **실제로 적용되는 설정값**을 읽는다. ConsoleSwitch(AppShell.jsx)는 sx prop 리터럴이라
 * 테마 객체에 없다 — jsdom이 emotion 동적 클래스의 computed style을 안정적으로 못 주므로
 * (body-editor-toolbar-contrast.test.jsx의 같은 이유) 소스 텍스트를 직접 읽는다
 * (test_deploy_wiring.py와 같은 기법의 프런트 버전). */
function srgbToLinear(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a hex color: ${hex}`);
  const int = parseInt(m[1], 16);
  const r = srgbToLinear((int >> 16) & 255);
  const g = srgbToLinear((int >> 8) & 255);
  const b = srgbToLinear(int & 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(hexA, hexB) {
  const la = relativeLuminance(hexA);
  const lb = relativeLuminance(hexB);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

const AA_NORMAL_TEXT = 4.5;

// QAH-05: 일부 자리는 배경 자체가 alpha(color, opacity) 워시라 theme.palette에 없다(렌더
// 시점에 브라우저가 합성한다) — 실제 sx의 alpha 값과 같은 값으로 여기서도 합성해야
// "그 자리가 실제로 보이는 배경"과 대비를 잰다(순수 표면색과만 비교하면 워시가 만드는
// 진짜 문제를 놓친다).
function compositeOver(fgHex, bgHex, alpha) {
  const fm = /^#?([0-9a-f]{6})$/i.exec(fgHex);
  const bm = /^#?([0-9a-f]{6})$/i.exec(bgHex);
  if (!fm || !bm) throw new Error(`not a hex color: ${fgHex} / ${bgHex}`);
  const fi = parseInt(fm[1], 16), bi = parseInt(bm[1], 16);
  const mix = (shift) => {
    const f = (fi >> shift) & 255, b = (bi >> shift) & 255;
    return Math.round(f * alpha + b * (1 - alpha));
  };
  const out = [mix(16), mix(8), mix(0)];
  return "#" + out.map((c) => c.toString(16).padStart(2, "0")).join("");
}

describe("CTR-01/CTR-04 — MuiLink이 실제로 primary.dark(대비 보강 변수)를 쓰고, 그 값이 AA를 만족한다", () => {
  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent}`, () => {
        const theme = createClovirTheme(mode, accent);
        // 배선 확인: MuiLink styleOverrides가 실제로 primary.dark를 참조하는가(원래 버그는
        // color 자체가 없어 MUI가 자기 기본값 primary.main으로 렌더한 것이었다).
        const wiredColor = theme.components?.MuiLink?.styleOverrides?.root?.color;
        expect(wiredColor, "MuiLink styleOverrides.root.color가 설정돼 있지 않다").toBe(
          theme.palette.primary.dark,
        );

        const surfaces = [
          theme.palette.background.paper,
          theme.palette.background.surface2,
          theme.palette.background.default,
        ];
        for (const surface of surfaces) {
          const ratio = contrastRatio(wiredColor, surface);
          expect(
            ratio,
            `mode=${mode} accent=${accent} linkColor=${wiredColor} surface=${surface} ratio=${ratio.toFixed(2)}`,
          ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });
    }
  }
});

describe("CTR-02 — ConsoleSwitch 활성 탭이 실제로 primary.main을 쓰고, 그 값이 흰 배경과 AA를 만족한다", () => {
  const appShellSrc = readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "AppShell.jsx"),
    "utf-8",
  );

  /* D-141 로 선택 표현이 바뀌었다. 예전에는 활성 탭 글자가 강조색이었고 배경이 리터럴
   * 흰색이었다(CTR-02 가 그 조합의 대비를 지켰다). 지금은 **판이 떠오르고 글자는 본문색**
   * 이다 — 강조색은 주요 행동·현재 선택 레일·포커스 세 자리에만 쓴다.
   *
   * 그래서 검사 대상도 바뀐다: "글자가 primary.main 인가"가 아니라 **"선택된 쪽이 실제로
   * 구분되고, 그 글자가 자기 배경 위에서 AA 를 넘는가"** 를 본다. 배선 검사(소스를 읽어
   * 실제 적용값을 확인)라는 성격은 그대로 유지한다. */
  const consoleSwitchBlock = appShellSrc.slice(
    appShellSrc.indexOf("function ConsoleSwitch"),
    appShellSrc.indexOf("function ConsoleSwitch") + 2500,
  );

  /* D-179 로 Shell 이 인디고가 되면서 이 스위치는 **반전 컨트롤**이 됐다. 흰 판이 떠오르는
     예전 방식은 인디고 하우징 안에서 화면을 통틀어 가장 밝은 면이 되어 데이터보다 먼저
     눈에 띈다. 지금은 트랙보다 밝은 흰빛 알파 + 한 줄 하이라이트다.
     시험의 성격(소스를 읽어 실제 적용값을 확인 → 그 조합의 대비를 잰다)은 그대로다. */
  it("ConsoleSwitch 활성 탭은 흰빛 알파로 떠오르고 비활성은 트랙에 남는다", () => {
    const bg = /bgcolor:\s*seg\.on\s*\?\s*"([^"]+)"\s*:\s*"([^"]+)"/.exec(consoleSwitchBlock);
    expect(bg, "ConsoleSwitch 에서 seg.on 삼항 bgcolor 선언을 못 찾았다").not.toBeNull();
    expect(bg[1]).toBe("sidebar.trackSelected");
    expect(bg[2]).toBe("transparent");
    // 알파만으로는 트랙과 붙어 보일 수 있어 한 줄 하이라이트를 더 얹는다.
    expect(consoleSwitchBlock).toMatch(/boxShadow:\s*seg\.on\s*\?/);
    expect(consoleSwitchBlock).toMatch(/sidebar\.edge/);
    /* 트랙 자체도 chrome 면이어야 한다. `background.inset` 은 캔버스 계열이라 인디고 위에서
       밝은 회색 띠가 되고, 그 위 `sidebar.muted` 글자는 실측 1.75:1 이 된다 — 이 시험이
       실제로 잡아낸 회귀다. */
    expect(consoleSwitchBlock).toMatch(/bgcolor:\s*"sidebar\.track"/);
  });

  it("ConsoleSwitch 활성 탭 글자는 chrome 잉크이고 비활성은 chrome 보조 잉크다", () => {
    const colorLine = /color:\s*seg\.on\s*\?\s*"([^"]+)"\s*:\s*"([^"]+)"/.exec(consoleSwitchBlock);
    expect(colorLine, "ConsoleSwitch 에서 seg.on 삼항 color 선언을 못 찾았다").not.toBeNull();
    expect(colorLine[1]).toBe("sidebar.text");
    expect(colorLine[2]).toBe("sidebar.muted");
  });

  /* 워시는 반투명이라 실제 색이 **뒷면과의 합성**으로 정해진다. 합성하지 않고 잰 숫자는
     아무것도 증명하지 않으므로, 사이드바 그라디언트의 stop 전부에 대해 합성해 잰다 —
     예전에는 flat base 하나만 봤고, 그래서 가장 밝은 stop 위 글자를 아무도 안 봤다. */
  function overWhite(alphaCss, bgHex) {
    const a = parseFloat(/rgba\(255,\s*255,\s*255,\s*(\.?\d*\.?\d+)\)/.exec(alphaCss)[1]);
    const ch = (i) => Math.round(255 * a + parseInt(bgHex.slice(i, i + 2), 16) * (1 - a));
    return "#" + [1, 3, 5].map((i) => ch(i).toString(16).padStart(2, "0")).join("");
  }

  for (const mode of ["light", "dark"]) {
    it(`${mode} — ConsoleSwitch 활성/비활성 글자가 모든 stop 에서 AA 를 넘는다`, () => {
      const p = createClovirTheme(mode).palette;
      const stops = [p.chrome.shell, ...(p.chrome.shellImage.match(/#[0-9A-Fa-f]{6}/g) || [])];
      expect(stops.length).toBeGreaterThanOrEqual(3);
      for (const stop of stops) {
        expect(
          contrastRatio(p.sidebar.text, overWhite(p.sidebar.trackSelected, stop)),
          `활성 @${stop}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        expect(
          contrastRatio(p.sidebar.muted, overWhite(p.sidebar.track, stop)),
          `비활성 @${stop}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      }
    });
  }

  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — primary.main vs 흰 배경(common.white)`, () => {
        const theme = createClovirTheme(mode, accent);
        const ratio = contrastRatio(theme.palette.primary.main, "#FFFFFF");
        expect(
          ratio,
          `mode=${mode} accent=${accent} color=${theme.palette.primary.main} ratio=${ratio.toFixed(2)}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });
    }
  }
});

describe("QAH-03(2026-08-11 하네스 실측) — MuiButton 기본(text/outlined + primary) 글자색이 AA를 만족한다", () => {
  it("MuiButton styleOverrides가 textPrimary/outlinedPrimary에 실제로 primary.dark를 쓴다", () => {
    // 하네스 표본 519건 중 262건(68/68 라우트)이 이 패턴이었다 — href가 있는 Button은
    // <a>로 렌더되고(예: 「초기 설정 계속하기」), variant/color를 안 주면 MUI 기본값(text
    // variant, primary color)이 palette.primary.main(원본 accent)을 그대로 쓴다.
    const theme = createClovirTheme("light", "indigo");
    expect(theme.components?.MuiButton?.styleOverrides?.textPrimary?.color).toBe(
      theme.palette.primary.dark,
    );
    expect(theme.components?.MuiButton?.styleOverrides?.outlinedPrimary?.color).toBe(
      theme.palette.primary.dark,
    );
  });

  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — primary.dark(=버튼 텍스트색) vs 표면`, () => {
        const theme = createClovirTheme(mode, accent);
        const color = theme.components.MuiButton.styleOverrides.textPrimary.color;
        for (const surface of [theme.palette.background.paper, theme.palette.background.default]) {
          const ratio = contrastRatio(color, surface);
          expect(
            ratio,
            `mode=${mode} accent=${accent} color=${color} surface=${surface} ratio=${ratio.toFixed(2)}`,
          ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });
    }
  }
});

describe("QAH-03 — 판독 칸 「주의」/「위험」 배지가 palette.{warning,error}.strong(대비 보강)을 쓴다", () => {
  const kitSrc = readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "kit.jsx"),
    "utf-8",
  );

  it("판독 칸의 sev Box가 실제로 `${tone}.strong`을 참조한다(원래 버그는 `.main`이었다)", () => {
    // StatCard(카드 한 장 = 지표 하나)를 MetricStrip 이 대체했다 — 계약은 그대로다.
    const start = kitSrc.indexOf("export function MetricStrip");
    expect(start, "MetricStrip 정의를 못 찾았다").toBeGreaterThan(-1);
    const block = kitSrc.slice(start, start + 4500);
    expect(block).toMatch(/color:\s*`\$\{tone\}\.strong`/);
    expect(block).not.toMatch(/color:\s*`\$\{tone\}\.main`/);
  });

  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — warning.strong/error.strong vs 표면`, () => {
        const theme = createClovirTheme(mode, accent);
        for (const tone of ["warning", "error"]) {
          const color = theme.palette[tone].strong;
          expect(color, `palette.${tone}.strong이 없다`).toBeTruthy();
          for (const surface of [theme.palette.background.paper, theme.palette.background.default]) {
            const ratio = contrastRatio(color, surface);
            expect(
              ratio,
              `mode=${mode} accent=${accent} tone=${tone} color=${color} surface=${surface} ratio=${ratio.toFixed(2)}`,
            ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
          }
        }
      });
    }
  }
});

describe("QAH-02(2026-08-11 하네스 실측) — 심각도 배지가 좁은 칸에서 세로로 안 무너진다", () => {
  it("sev Box에 whiteSpace:nowrap과 flexShrink:0이 있다(한글은 word-break 기본값이 음절 사이 어디서나 끊는다)", () => {
    const kitSrcHere = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "kit.jsx"),
      "utf-8",
    );
    const start = kitSrcHere.indexOf("export function MetricStrip");
    expect(start, "MetricStrip 정의를 못 찾았다").toBeGreaterThan(-1);
    const block = kitSrcHere.slice(start, start + 4500);
    const sevLine = /\{sev \? \([\s\S]{0,900}?<\/Box>/.exec(block);
    expect(sevLine, "sev Box 블록을 못 찾았다").not.toBeNull();
    expect(sevLine[0]).toMatch(/whiteSpace:\s*"nowrap"/);
    expect(sevLine[0]).toMatch(/flexShrink:\s*0/);
  });
});

describe("QAH-03 — MyTickets TitleCell 링크가 inline sx로 대비 보강 색을 덮어쓰지 않는다", () => {
  it("TitleCell이 실제로 primary.dark를 쓴다(원래 버그는 primary.main을 inline sx로 직접 박아 MuiLink의 공유 대비 보강을 덮어썼다)", () => {
    const src = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screens", "MyTickets.jsx"),
      "utf-8",
    );
    const start = src.indexOf("function TitleCell");
    expect(start, "TitleCell 정의를 못 찾았다").toBeGreaterThan(-1);
    const block = src.slice(start, start + 1400);
    expect(block).toMatch(/color:\s*"primary\.dark"/);
    expect(block).not.toMatch(/color:\s*"primary\.main"/);
  });
});

describe("QAH-03 — SchedulerCalendar가 짝이 안 맞는 .light 배경 + .contrastText 조합을 안 쓴다", () => {
  const src = readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screens", "SchedulerCalendar.jsx"),
    "utf-8",
  );

  it("EventDot의 bgcolor가 .light가 아니라 .main이다(contrastText는 .main 기준으로 계산된다)", () => {
    const start = src.indexOf("function EventDot");
    expect(start, "EventDot 정의를 못 찾았다").toBeGreaterThan(-1);
    const block = src.slice(start, start + 1200);
    expect(block).toMatch(/bgcolor:\s*planned \? "transparent" : failed \? "error\.main" : "primary\.main"/);
  });

  it("오늘 날짜 숫자가 primary.dark를 쓴다(다크 표면에서 primary.main은 AA 미달이었다)", () => {
    const anchor = src.indexOf('isToday ? ", 오늘"');
    expect(anchor, "오늘 표시를 못 찾았다").toBeGreaterThan(-1);
    const block = src.slice(Math.max(0, anchor - 400), anchor);
    expect(block).toMatch(/color:\s*isToday \? "primary\.dark" : "text\.secondary"/);
  });
});

describe("QAH-03 — Diagnostics 진단 문제 목록이 palette.{error,warning}.strong을 쓴다", () => {
  it("li 항목의 color가 .main이 아니라 .strong이다", () => {
    const src = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screens", "ops", "Diagnostics.jsx"),
      "utf-8",
    );
    const idx = src.indexOf('component="li"');
    expect(idx, "component=\"li\" 항목을 못 찾았다").toBeGreaterThan(-1);
    const block = src.slice(idx, idx + 550);
    expect(block).toMatch(/color:\s*p\.tone === "danger" \? "error\.strong" : "warning\.strong"/);
  });
});

/* QAH-05: QAH-03 조사가 하네스 표본(라우트당 5건 상한)에 안 걸려 놓친 같은 패턴 —
 * Board.jsx + 게임방 화면 5개 파일에 작은 글자 raw primary.main이 7곳 더 있었다(신설
 * BACKLOG 행이 "손대기 전에 먼저... 수동으로 대비를 재야 함"이라고 명시적으로 요구했다).
 * 조사 중 같은 파일들에서 2곳을 추가로 더 찾았다(GameStage.jsx의 success.main 정답 표시,
 * StageShared.jsx Countdown의 urgent 삼항이 error.main도 같이 씀) — 9곳 전부 여기서 잰다.
 *
 * 이 9곳 중 다수는 배경 자체가 alpha(...) 워시다(Paper/Card 없이 바로 background.default
 * 위에 뜨는 배지·라벨류) — compositeOver로 실제 렌더 배경을 재구성해서 잰다. */
describe("QAH-05 — Board.jsx + game-room 6파일의 raw .main 소문자 텍스트가 대비 보강 색을 쓴다", () => {
  const screensDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screens");
  const gameRoomDir = path.join(screensDir, "game-room");

  function readSite(...segments) {
    return readFileSync(path.join(...segments), "utf-8");
  }

  it("Board.jsx 댓글 수 배지가 primary.dark를 쓴다", () => {
    const src = readSite(screensDir, "Board.jsx");
    // PA-RC-0001이 fontWeight:700/fontSize:"0.8125rem" 리터럴을 FONT_WEIGHT.bold/FONT_SIZE.bodySm
    // 토큰 참조로 옮겼다(같은 계산값, revert-to-verify로 무변경 확인됨) — 이 시험이 확인하려는
    // 것은 리터럴 철자가 아니라 primary.dark 대비색이 여전히 그 자리에 있는지다.
    expect(src).toMatch(/color:\s*"primary\.dark",\s*fontWeight:\s*FONT_WEIGHT\.bold,\s*fontSize:\s*FONT_SIZE\.bodySm/);
    expect(src).not.toMatch(/color:\s*"primary\.main",\s*fontWeight:\s*FONT_WEIGHT\.bold,\s*fontSize:\s*FONT_SIZE\.bodySm/);
  });

  it("GameStage.jsx 사다리 결과 폴백 목록이 primary.dark를 쓴다", () => {
    const src = readSite(gameRoomDir, "GameStage.jsx");
    expect(src).toMatch(/color:\s*"primary\.dark"\s*}}>{a\.outcome}/);
  });

  it("GameStage.jsx 실시간 투표 수가 primary.dark를 쓴다", () => {
    const src = readSite(gameRoomDir, "GameStage.jsx");
    expect(src).toMatch(/color:\s*"primary\.dark",\s*fontVariantNumeric:\s*"tabular-nums"\s*}}>\s*{liveCounts\[i\]}/);
  });

  it("GameStage.jsx 퀴즈 '정답' 표시가 success.strong을 쓴다", () => {
    const src = readSite(gameRoomDir, "GameStage.jsx");
    expect(src).toMatch(/color:\s*"success\.strong"\s*}}>정답/);
  });

  it("LadderBoard.jsx 확정된 결과가 primary.dark를 쓴다", () => {
    const src = readSite(gameRoomDir, "LadderBoard.jsx");
    expect(src).toMatch(/component="b" sx={{ color: "primary\.dark" }}/);
  });

  it("MembersList.jsx 직책 라벨이 primary.dark를 쓴다", () => {
    const src = readSite(gameRoomDir, "MembersList.jsx");
    // PA-RC-0001이 fontWeight:600 리터럴을 FONT_WEIGHT.semibold 토큰 참조로 옮겼다(같은 계산값).
    expect(src).toMatch(/color:\s*"primary\.dark",\s*fontWeight:\s*FONT_WEIGHT\.semibold/);
  });

  it("Scoreboard.jsx 점수 값이 primary.dark를 쓴다", () => {
    const src = readSite(gameRoomDir, "Scoreboard.jsx");
    expect(src).toMatch(/color:\s*"primary\.dark",\s*fontVariantNumeric:\s*"tabular-nums"\s*}}>{s\.value}/);
  });

  it("StageShared.jsx 결과 라벨이 primary.dark를 쓴다", () => {
    const src = readSite(gameRoomDir, "StageShared.jsx");
    expect(src).toMatch(/letterSpacing:\s*"0\.06em",\s*color:\s*"primary\.dark"\s*}}>{label}/);
  });

  it("StageShared.jsx Countdown이 error.strong/primary.dark를 쓴다(urgent 삼항 양쪽 다)", () => {
    const src = readSite(gameRoomDir, "StageShared.jsx");
    expect(src).toMatch(/color:\s*urgent\s*\?\s*"error\.strong"\s*:\s*"primary\.dark"/);
  });

  // ── 계산된 대비: 각 자리의 실제 배경(순수 표면 또는 alpha 워시)과 비교 ──────────────
  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — 순수 표면 위 6곳(Board·GameStage:70·LadderBoard·MembersList 비-isMe·Scoreboard)`, () => {
        const theme = createClovirTheme(mode, accent);
        for (const surface of [theme.palette.background.paper, theme.palette.background.default]) {
          const ratio = contrastRatio(theme.palette.primary.dark, surface);
          expect(
            ratio,
            `mode=${mode} accent=${accent} color=${theme.palette.primary.dark} surface=${surface} ratio=${ratio.toFixed(2)}`,
          ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });

      it(`${mode} 모드, accent=${accent} — GameStage.jsx:132 내 투표(선택됨, alpha(primary.main,0.12) on background.default)`, () => {
        const theme = createClovirTheme(mode, accent);
        const washed = compositeOver(theme.palette.primary.main, theme.palette.background.default, 0.12);
        const ratio = contrastRatio(theme.palette.primary.dark, washed);
        expect(ratio, `mode=${mode} accent=${accent} washed=${washed} ratio=${ratio.toFixed(2)}`)
          .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });

      it(`${mode} 모드, accent=${accent} — MembersList.jsx 내 자신 행(alpha(primary.main,0.1) on background.paper)`, () => {
        const theme = createClovirTheme(mode, accent);
        const washed = compositeOver(theme.palette.primary.main, theme.palette.background.paper, 0.1);
        const ratio = contrastRatio(theme.palette.primary.dark, washed);
        expect(ratio, `mode=${mode} accent=${accent} washed=${washed} ratio=${ratio.toFixed(2)}`)
          .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });

      it(`${mode} 모드, accent=${accent} — StageShared.jsx 결과 라벨(celebrating, alpha(primary.main,0.08) on background.default)`, () => {
        const theme = createClovirTheme(mode, accent);
        const washed = compositeOver(theme.palette.primary.main, theme.palette.background.default, 0.08);
        const ratio = contrastRatio(theme.palette.primary.dark, washed);
        expect(ratio, `mode=${mode} accent=${accent} washed=${washed} ratio=${ratio.toFixed(2)}`)
          .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });

      it(`${mode} 모드, accent=${accent} — StageShared.jsx Countdown 평시(alpha(primary.main,0.14), primary.dark)`, () => {
        const theme = createClovirTheme(mode, accent);
        // 확실한 조상 배경을 못 밝혀 둘 중 더 낮게 나오는 쪽(paper)을 기준으로 삼는다 — 보수적 판정.
        for (const base of [theme.palette.background.paper, theme.palette.background.default]) {
          const washed = compositeOver(theme.palette.primary.main, base, 0.14);
          const ratio = contrastRatio(theme.palette.primary.dark, washed);
          expect(ratio, `mode=${mode} accent=${accent} base=${base} washed=${washed} ratio=${ratio.toFixed(2)}`)
            .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });

      it(`${mode} 모드, accent=${accent} — StageShared.jsx Countdown 긴급(alpha(error.main,0.14), error.strong)`, () => {
        const theme = createClovirTheme(mode, accent);
        for (const base of [theme.palette.background.paper, theme.palette.background.default]) {
          const washed = compositeOver(theme.palette.error.main, base, 0.14);
          const ratio = contrastRatio(theme.palette.error.strong, washed);
          expect(ratio, `mode=${mode} accent=${accent} base=${base} washed=${washed} ratio=${ratio.toFixed(2)}`)
            .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });

      it(`${mode} 모드, accent=${accent} — GameStage.jsx:303 퀴즈 정답(alpha(success.main,0.12) on background.default)`, () => {
        const theme = createClovirTheme(mode, accent);
        const washed = compositeOver(theme.palette.success.main, theme.palette.background.default, 0.12);
        const ratio = contrastRatio(theme.palette.success.strong, washed);
        expect(ratio, `mode=${mode} accent=${accent} washed=${washed} ratio=${ratio.toFixed(2)}`)
          .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });
    }
  }
});

/* QAH-07 — QAH-05 수정 뒤 배경 조사 에이전트가 저장소 전체에서 같은 `color: "X.main"` 패턴을
 * 재확인했다(kit.jsx 필수 표시 asterisk 포함 15개 파일 후보). 대부분은 bgcolor/borderColor/
 * SVG 아이콘 fill(텍스트 대비 문제 아님)이거나 이미 통과하는 조합이었지만, 5곳은 실측으로
 * 대비 미달을 확인했다 — 전부 dark 모드에서 실패(최저 2.81), 그중 WelcomeStatus.jsx는
 * light 모드도 accent 절반이 실패한다(배경이 Card의 background.paper가 아니라
 * Chat.jsx가 다시 칠하는 background.default라 워시 없이도 대비가 더 나쁘다). */
describe("PA-RC-0021 — MuiTab/MuiTabs 선택 상태가 primary.dark(대비 보강)를 쓴다", () => {
  // 소비처 셋(AssistantPanel의 /me 브리핑 탭, Project, SettingsShell) 전부 색을 안 주므로
  // MUI 기본값(indicatorColor/textColor="primary" → palette.primary.main)이 그대로
  // 적용돼 있었다 — 다크 표면에서 3.76:1로 AA 미달(실측). 개별 화면 대신 테마 컴포넌트
  // 층에서 고쳐 세 소비처 모두 한 번에 낫는다(MuiLink/MuiButton과 같은 방식).
  it("MuiTab.styleOverrides의 선택 상태 color, MuiTabs.styleOverrides.indicator가 실제로 primary.dark를 쓴다", () => {
    const theme = createClovirTheme("dark", "indigo");
    expect(theme.components?.MuiTab?.styleOverrides?.root?.["&.Mui-selected"]?.color).toBe(
      theme.palette.primary.dark,
    );
    expect(theme.components?.MuiTabs?.styleOverrides?.indicator?.backgroundColor).toBe(
      theme.palette.primary.dark,
    );
  });

  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — 탭 글자/밑줄색(primary.dark) vs 표면`, () => {
        const theme = createClovirTheme(mode, accent);
        const color = theme.components.MuiTab.styleOverrides.root["&.Mui-selected"].color;
        for (const surface of [theme.palette.background.paper, theme.palette.background.default]) {
          const ratio = contrastRatio(color, surface);
          expect(
            ratio,
            `mode=${mode} accent=${accent} color=${color} surface=${surface} ratio=${ratio.toFixed(2)}`,
          ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
        }
      });
    }
  }
});

/* PA-RC-0021 — NavBadge(사이드바 안 읽음/실패 건수 배지)가 색을 하드코딩했었다
 * (color: "common.white"). 배경(error.main)은 모드별로 다른데(다크: #FF8B9B 밝은 분홍)
 * 글자만 항상 흰색이라 다크에서 2.23:1(기준 4.5)로 실패했다. error.contrastText는
 * theme.js가 명시적으로 지정하지 않으므로 MUI가 error.main 명도로 자동 계산한다 —
 * 라이트(짙은 빨강)에서는 흰 글자, 다크(밝은 분홍)에서는 검은 글자로 자동으로 갈라진다.
 *
 * contrastText는 "#fff"뿐 아니라 "rgba(0, 0, 0, 0.87)"(부분 불투명 검정)로도 나올 수
 * 있어 hex 전용 relativeLuminance로 못 읽는다 — jsdom의 실제 CSS 파서(getComputedStyle)에
 * 맡겨 rgb/rgba 어느 쪽이든 정규화하고, 알파가 있으면 실제 배경(error.main) 위에 합성한
 * 뒤에 대비를 잰다(근사가 아니라 실제 렌더 결과와 같은 계산). */
function parseCssColorViaDom(cssColor) {
  const el = document.createElement("div");
  el.style.color = cssColor;
  document.body.appendChild(el);
  const computed = getComputedStyle(el).color;
  document.body.removeChild(el);
  const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(computed);
  if (!m) throw new Error(`jsdom이 색을 못 읽었다: "${cssColor}" -> "${computed}"`);
  return { r: Number(m[1]), g: Number(m[2]), b: Number(m[3]), a: m[4] != null ? Number(m[4]) : 1 };
}

function toHexFromRgb({ r, g, b }) {
  return "#" + [r, g, b].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("");
}

function resolveOverBackground(fgCss, bgHex) {
  const fg = parseCssColorViaDom(fgCss);
  if (fg.a >= 1) return toHexFromRgb(fg);
  const bg = parseCssColorViaDom(bgHex);
  return toHexFromRgb({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
  });
}

describe("PA-RC-0021 — NavBadge가 색을 하드코딩하지 않고 error.contrastText를 쓴다", () => {
  const appShellSrc = readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "AppShell.jsx"),
    "utf-8",
  );

  it("NavBadge의 color가 error.contrastText이고 common.white 하드코딩이 아니다", () => {
    const start = appShellSrc.indexOf("function NavBadge");
    expect(start, "NavBadge 정의를 못 찾았다").toBeGreaterThan(-1);
    const block = appShellSrc.slice(start, start + 1100);
    expect(block).toMatch(/color:\s*"error\.contrastText"/);
    expect(block).not.toMatch(/color:\s*"common\.white"/);
  });

  for (const mode of ["light", "dark"]) {
    it(`${mode} 모드 — error.contrastText가 실제 배경(error.main) 위에서 AA를 만족한다`, () => {
      const theme = createClovirTheme(mode, "indigo");
      const bg = theme.palette.error.main;
      const resolvedFg = resolveOverBackground(theme.palette.error.contrastText, bg);
      const ratio = contrastRatio(resolvedFg, bg);
      expect(
        ratio,
        `mode=${mode} contrastText=${theme.palette.error.contrastText} resolved=${resolvedFg} bg=${bg} ratio=${ratio.toFixed(2)}`,
      ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    });
  }
});

describe("QAH-07 — TeamDocs·ChatPane·AccentPicker·WelcomeStatus의 raw .main 텍스트가 대비 보강 색을 쓴다", () => {
  const screensDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screens");

  function readSite(...segments) {
    return readFileSync(path.join(...segments), "utf-8");
  }

  it("TeamDocs.jsx 테이블뷰 제목 링크 hover가 primary.dark를 쓴다", () => {
    const src = readSite(screensDir, "TeamDocs.jsx");
    const hits = src.match(/"&:hover":\s*{\s*color:\s*"primary\.dark"\s*}/g) || [];
    expect(hits.length, "테이블뷰·DocCard 두 곳 모두 primary.dark를 써야 한다").toBe(2);
    expect(src).not.toMatch(/"&:hover":\s*{\s*color:\s*"primary\.main"\s*}/);
  });

  it("ChatPane.jsx 읽음 표시가 primary.dark를 쓴다", () => {
    const src = readSite(screensDir, "ChatPane.jsx");
    expect(src).toMatch(/color:\s*receipt === "읽음" \? "primary\.dark" : "text\.disabled"/);
  });

  it("settings/AccentPicker.jsx 선택 체크가 primary.dark를 쓴다", () => {
    const src = readSite(screensDir, "settings", "AccentPicker.jsx");
    // PA-RC-0001이 fontWeight:800 리터럴을 FONT_WEIGHT.extrabold 토큰 참조로 옮겼다(같은 계산값).
    expect(src).toMatch(/fontWeight:\s*FONT_WEIGHT\.extrabold,\s*color:\s*"primary\.dark"\s*}}>✓/);
  });

  it("chat/WelcomeStatus.jsx QuickPrompts hover색이 primary.dark를 쓴다(테두리는 그대로 primary.main)", () => {
    const src = readSite(screensDir, "chat", "WelcomeStatus.jsx");
    expect(src).toMatch(/"&:hover":\s*{\s*borderColor:\s*"primary\.main",\s*color:\s*"primary\.dark"\s*}/);
  });

  // ── 계산된 대비: 각 자리의 실제 배경과 비교 ──────────────────────────────────────
  for (const mode of ["light", "dark"]) {
    for (const accent of ACCENT_PRESETS) {
      it(`${mode} 모드, accent=${accent} — background.paper 위 4곳(TeamDocs×2·ChatPane·AccentPicker)`, () => {
        const theme = createClovirTheme(mode, accent);
        const ratio = contrastRatio(theme.palette.primary.dark, theme.palette.background.paper);
        expect(
          ratio,
          `mode=${mode} accent=${accent} color=${theme.palette.primary.dark} paper=${theme.palette.background.paper} ratio=${ratio.toFixed(2)}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });

      it(`${mode} 모드, accent=${accent} — WelcomeStatus.jsx QuickPrompts(Card 아님, background.default 위)`, () => {
        const theme = createClovirTheme(mode, accent);
        const ratio = contrastRatio(theme.palette.primary.dark, theme.palette.background.default);
        expect(
          ratio,
          `mode=${mode} accent=${accent} color=${theme.palette.primary.dark} default=${theme.palette.background.default} ratio=${ratio.toFixed(2)}`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });
    }
  }
});
