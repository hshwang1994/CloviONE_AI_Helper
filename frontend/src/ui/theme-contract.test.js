/* 디자인 시스템 계약 — 실제 런타임 테마를 검증한다.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * 예전에는 `theme-baseline.test.js` 가 폐기한 목업(지시 64)(목업)을
 * 파싱해 theme.js 와 **값이 같은지** 대조했다. 그 목업은 사용자 지시 64로 폐기했다 —
 * 리뉴얼의 디자인 정본이 아니고, 새 디자인을 옛 구조에 맞추는 족쇄였기 때문이다.
 *
 * 그래서 검사 대상을 바꿨다. "목업과 같은가"가 아니라 **"우리가 선언한 디자인 시스템 계약을
 * 실제 테마가 지키는가"** 를 본다. 시험을 지우거나 약화한 것이 아니다 — 지키려던 목적
 * (표면 위계가 실재하는가, 재양자화 단계 수가 유지되는가, 대비가 확보되는가, 포커스가
 * 보이는가)은 그대로 두고 근거를 목업에서 런타임으로 옮겼다.
 *
 * 계약의 출처는 `docs/DECISIONS.md` D-141 방향 계약이다.
 */
import { describe, expect, it } from "vitest";
import {
  createClovirTheme,
  ACCENT_PRESETS,
  CHART_DASH,
  CHART_SERIES,
  CONTROL,
  DEFAULT_ACCENT,
  FONT_SIZE,
  FONT_WEIGHT,
  LINE_HEIGHT,
  MOTION,
  NUMERIC,
  RADIUS,
} from "./theme.js";

const MODES = ["light", "dark"];

/* WCAG 상대 휘도와 대비비. 외부 의존성 없이 여기서 계산한다 — 대비는 눈대중으로 통과시킬
 * 수 있는 종류가 아니라서, 숫자가 시험 안에 있어야 한다. */
function luminance(hex) {
  const ch = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
function rgb(hex) {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
}
/* 반투명 워시가 실제로 그려내는 색. 투명 틴트의 대비는 "어떤 면 위에 얹히느냐"에 따라
   달라지므로, 합성하지 않고 잰 숫자는 아무것도 증명하지 않는다. */
function composite(fgHex, alpha, bgHex) {
  const f = rgb(fgHex);
  const b = rgb(bgHex);
  return (
    "#" +
    [0, 1, 2]
      .map((i) => Math.round(f[i] * alpha + b[i] * (1 - alpha)).toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()
  );
}
/* `rgba(255,255,255,.06)` -> 0.06. 워시 토큰의 알파를 시험이 직접 읽어야 값이 바뀌면 숫자도
   따라온다 — 알파를 시험에 손으로 적으면 그 순간 두 번째 정본이 생긴다. */
function alphaOf(css) {
  const m = /rgba?\(\s*255\s*,\s*255\s*,\s*255\s*,\s*(\.?\d*\.?\d+)\s*\)/.exec(css);
  if (!m) throw new Error(`흰빛 알파 워시가 아니다: ${css}`);
  return parseFloat(m[1]);
}
/* 그라디언트의 **모든 stop**. flat base 만 재던 것이 예전 Gradient Chrome 이 미측정으로
   배포된 경로다 — 가장 밝은 stop 위에서 글자가 무엇이 되는지 아무도 안 봤다. */
function stopsOf(gradient) {
  return (String(gradient).match(/#[0-9A-Fa-f]{6}/g) || []).map((h) => h.toUpperCase());
}

describe("표면 위계 (D-141: 판 위에 판독값)", () => {
  it.each(MODES)("%s — canvas / plate / inset / sunken 이 서로 다른 색이다", (mode) => {
    const bg = createClovirTheme(mode).palette.background;
    const levels = [bg.canvas, bg.plate, bg.inset, bg.sunken];
    expect(new Set(levels).size).toBe(4);
  });

  it.each(MODES)("%s — 옛 이름(surface2/surface3)이 새 위계를 가리킨다", (mode) => {
    const bg = createClovirTheme(mode).palette.background;
    // 소비처 55곳이 아직 옛 이름을 쓴다. 이름은 남기되 의미는 새 위계여야 한다.
    expect(bg.surface2).toBe(bg.inset);
    expect(bg.surface3).toBe(bg.sunken);
  });
});

describe("enclosure 는 기본값이 아니다 (D-141 RAISE, cracktro)", () => {
  it.each(MODES)("%s — 판(Card)에는 그림자가 없다", (mode) => {
    const t = createClovirTheme(mode);
    const card = t.components.MuiCard.styleOverrides.root({ theme: t });
    expect(card.boxShadow).toBe("none");
  });

  it.each(MODES)("%s — 판은 실선 하나로만 구획된다", (mode) => {
    const t = createClovirTheme(mode);
    const card = t.components.MuiCard.styleOverrides.root({ theme: t });
    expect(card.border).toBe(`1px solid ${t.palette.divider}`);
  });

  it.each(MODES)("%s — 그림자는 떠 있는 것만 갖는다(none/overlay/modal 셋뿐)", (mode) => {
    const s = createClovirTheme(mode).shadowTokens;
    expect(Object.keys(s).sort()).toEqual(["modal", "none", "overlay"]);
    expect(s.none).toBe("none");
    expect(s.overlay).not.toBe("none");
    expect(s.modal).not.toBe("none");
  });
});

/* D-179 가 D-141 의 "chrome 은 발광하지 않는다"를 대체한다.
 *
 * 옛 단언 `contrast(sidebar.bg, canvas) < 2` 는 **접근성 단언이 아니라 방향 단언**이었다.
 * 그 방향이 폐기됐는데 단언만 남아 있으면, 시험은 이제 제품이 Brand 를 갖는 것을 **금지**한다.
 * 그래서 지우는 것이 아니라 뒤집어 다시 쓴다 — 같은 자리에서, 더 강한 형태로.
 *
 * 새 단언 둘 다 반증 가능하다:
 *   (1) `blue − red >= 24` — 옛 `#E7EAEE` 는 7 로 실패하고 새 `#1E2758` 은 58 로 통과한다.
 *       이 단언이 없었기 때문에 "제품에 Brand 가 없다"를 아무 시험도 잡지 못했다.
 *   (2) Light `contrast(shell, canvas) >= 4.5` — chrome 이 캔버스의 한 톤이 아니라 **자기
 *       재료**임을 요구한다. Dark 는 두 면이 원래 다 어두워 이 비율이 성립할 수 없으므로
 *       (1)만 두 모드에 건다.
 */
describe("chrome 이 Brand 를 나른다 (D-179 — D-141 의 '발광하지 않는다'를 대체한다)", () => {
  it.each(MODES)("%s — 사이드바 flat base 는 여전히 단색이다(그라디언트가 아니다)", (mode) => {
    const bg = createClovirTheme(mode).palette.sidebar.bg;
    expect(bg).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(bg).not.toMatch(/gradient/i);
  });

  it.each(MODES)("%s — chrome.shell 이 Brand 색상을 나른다 (blue − red >= 24)", (mode) => {
    const shell = createClovirTheme(mode).palette.chrome.shell;
    const [r, , b] = rgb(shell);
    expect(b - r, `${shell} 의 blue−red = ${b - r}`).toBeGreaterThanOrEqual(24);
  });

  it("light — chrome 이 캔버스와 뚜렷이 다른 자기 재료다 (contrast >= 4.5)", () => {
    const p = createClovirTheme("light").palette;
    expect(contrast(p.chrome.shell, p.background.canvas)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(MODES)("%s — sidebar 는 chrome 의 별칭이고 값을 따로 들고 있지 않다", (mode) => {
    const p = createClovirTheme(mode).palette;
    expect(p.sidebar.bg).toBe(p.chrome.shell);
    expect(p.sidebar.text).toBe(p.chrome.onShell);
    expect(p.sidebar.muted).toBe(p.chrome.onShellMuted);
    expect(p.sidebar.line).toBe(p.chrome.line);
    expect(p.sidebar.activeRail).toBe(p.chrome.rail);
  });

  it.each(MODES)("%s — Top bar 채움이 Sidebar Gradient 의 첫 stop 이다", (mode) => {
    const p = createClovirTheme(mode).palette;
    // 두 층이 만나는 모서리가 같은 색인 이유가 이것이다. 다르면 L자가 두 조각으로 보인다.
    expect(stopsOf(p.chrome.shellImage)[0]).toBe(p.chrome.shellTop.toUpperCase());
  });
});

describe("Brand Identity 는 사용자 Accent 로 지울 수 없다 (지시 0-1)", () => {
  /* 이번 리뉴얼 이전에는 `sidebar.activeRail` 과 `BrandLogo` 워드마크가 `primary.main`
     이었다 — 청록을 고른 사용자의 화면에서는 제품의 '현재 위치'와 로고가 청록이 됐다.
     Identity 가 Interaction 계층에 얹혀 있었던 것이고, 그것을 막는 단언이 없었다. */
  const FIXED = [
    ["chrome.shell", (p) => p.chrome.shell],
    ["chrome.rail", (p) => p.chrome.rail],
    ["sidebar.activeRail", (p) => p.sidebar.activeRail],
    ["brand.purple", (p) => p.brand.purple],
    ["brand.wordmark", (p) => p.brand.wordmark],
    ["brand.core", (p) => p.brand.core],
    ["background.brandTint", (p) => p.background.brandTint],
    ["chart[0]", (p) => p.chart[0]],
    ["gradient.shell", (p) => p.gradient.shell],
    ["gradient.hero", (p) => p.gradient.hero],
  ];

  it.each(MODES)("%s — 어떤 강조색을 골라도 Brand 값이 하나도 바뀌지 않는다", (mode) => {
    const base = createClovirTheme(mode, ACCENT_PRESETS[0]).palette;
    for (const accent of ACCENT_PRESETS.slice(1)) {
      const other = createClovirTheme(mode, accent).palette;
      for (const [name, pick] of FIXED) {
        expect(pick(other), `${name} @ ${accent}`).toBe(pick(base));
      }
    }
  });

  it("Accent 는 여전히 Interaction 계층을 소유한다(기능이 사라지지 않았다)", () => {
    const a = createClovirTheme("light", ACCENT_PRESETS[0]).palette;
    const b = createClovirTheme("light", ACCENT_PRESETS[4]).palette;
    expect(a.primary.main).not.toBe(b.primary.main);
    expect(a.primary.dark).not.toBe(b.primary.dark);
  });
});

describe("Chrome 위의 글자 — Gradient 모든 stop 에서 잰다", () => {
  it.each(MODES)("%s — onShell / onShellMuted / onShellFaint 가 모든 stop 에서 AA", (mode) => {
    const c = createClovirTheme(mode).palette.chrome;
    const stops = [...new Set([c.shell, ...stopsOf(c.shellImage)])];
    expect(stops.length).toBeGreaterThanOrEqual(3);
    for (const ink of [c.onShell, c.onShellMuted, c.onShellFaint]) {
      for (const stop of stops) {
        expect(contrast(ink, stop), `${ink} on ${stop}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(MODES)("%s — 흰 글자도 모든 stop 에서 AA (버튼·칩이 Shell 위에 앉는다)", (mode) => {
    const c = createClovirTheme(mode).palette.chrome;
    for (const stop of [c.shell, ...stopsOf(c.shellImage)]) {
      expect(contrast("#FFFFFF", stop), `#FFFFFF on ${stop}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(MODES)("%s — 활성 레일과 Shell 포커스 링이 비텍스트 3:1 을 넘는다", (mode) => {
    const c = createClovirTheme(mode).palette.chrome;
    for (const stop of [c.shell, ...stopsOf(c.shellImage)]) {
      expect(contrast(c.rail, stop), `rail on ${stop}`).toBeGreaterThanOrEqual(3);
      expect(contrast(c.focusRing, stop), `focusRing on ${stop}`).toBeGreaterThanOrEqual(3);
    }
  });

  it.each(MODES)("%s — Hover Wash 합성 후에도 onShell·onShellMuted 가 AA", (mode) => {
    const c = createClovirTheme(mode).palette.chrome;
    const a = alphaOf(c.hover);
    for (const stop of [c.shell, ...stopsOf(c.shellImage)]) {
      const face = composite("#FFFFFF", a, stop);
      expect(contrast(c.onShell, face), `onShell on hover@${stop}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.onShellMuted, face), `onShellMuted on hover@${stop}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  /* 임의의 워시(`rgba(r,g,b,a)` 한 겹)를 그라디언트 stop 위에 합성한 면들. */
  const washFaces = (chrome, washCss) => {
    const m = /rgba\((\d+),\s*(\d+),\s*(\d+),\s*(\.?\d*\.?\d+)\)/.exec(washCss);
    if (!m) throw new Error(`rgba 워시를 못 찾았다: ${washCss}`);
    const tint =
      "#" + [1, 2, 3].map((i) => Number(m[i]).toString(16).padStart(2, "0")).join("").toUpperCase();
    const alpha = parseFloat(m[4]);
    return [chrome.shell, ...stopsOf(chrome.shellImage)].map((stop) => composite(tint, alpha, stop));
  };

  it.each(MODES)("%s — Selected Wash·AI Wash 위에서 onShell 은 모든 stop 에서 AA", (mode) => {
    const c = createClovirTheme(mode).palette.chrome;
    for (const [label, wash] of [["selected", c.selected], ["aiWash", c.aiWash]]) {
      for (const face of washFaces(c, wash)) {
        expect(contrast(c.onShell, face), `onShell on ${label}@${face}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  /* **하드 룰의 숫자 근거.** "Selected 행과 AI Wash 영역의 텍스트는 전부 `onShell`" 이라는
     규칙은 취향이 아니라 측정에서 나온다: 두 워시 위에서 `onShellMuted` 는 light 4.62/4.53 로
     간신히 통과하지만 **dark 에서 4.26/4.36 으로 미달**한다. 두 모드 전부에서 안전한 잉크는
     `onShell` 하나뿐이고, 그래서 모드별 예외를 두지 않고 규칙 하나로 간다.
     이 시험은 그 사실을 고정한다 — 팔레트가 바뀌어 muted 가 두 모드 다 통과하게 되면 여기가
     먼저 빨개지고, 그때 규칙을 다시 판단하면 된다(조용히 낡지 않는다). */
  it("두 모드를 함께 보면 워시 위에서 안전한 잉크는 onShell 하나뿐이다", () => {
    let worstMuted = Infinity;
    let worstFaint = Infinity;
    for (const mode of MODES) {
      const c = createClovirTheme(mode).palette.chrome;
      for (const wash of [c.selected, c.aiWash, c.hover]) {
        for (const face of washFaces(c, wash)) {
          worstMuted = Math.min(worstMuted, contrast(c.onShellMuted, face));
          worstFaint = Math.min(worstFaint, contrast(c.onShellFaint, face));
        }
      }
    }
    expect(worstMuted, `onShellMuted 최악 ${worstMuted.toFixed(2)}`).toBeLessThan(4.5);
    expect(worstFaint, `onShellFaint 최악 ${worstFaint.toFixed(2)}`).toBeLessThan(4.5);
  });

  it.each(MODES)("%s — Shell 위 반전 컨트롤(track/trackSelected)의 잉크가 AA", (mode) => {
    const c = createClovirTheme(mode).palette.chrome;
    for (const stop of [c.shell, ...stopsOf(c.shellImage)]) {
      const track = composite("#FFFFFF", alphaOf(c.track), stop);
      const sel = composite("#FFFFFF", alphaOf(c.trackSelected), stop);
      expect(contrast(c.onShellMuted, track), `비선택 @${stop}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.onShell, sel), `선택 @${stop}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("Brand 잉크와 Chart 시리즈", () => {
  const INKS = ["core", "indigoInk", "violetInk", "mintInk", "pinkInk", "wordmark"];

  it.each(MODES)("%s — Brand 잉크 6종이 네 면에서 AA 를 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    const faces = [p.background.plate, p.background.inset, p.background.canvas, p.background.brandTint];
    for (const key of INKS) {
      for (const face of faces) {
        expect(contrast(p.brand[key], face), `brand.${key} on ${face}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(MODES)("%s — Chart 시리즈가 세 면에서 비텍스트 3:1 을 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    const faces = [p.background.plate, p.background.inset, p.background.canvas];
    for (const c of p.chart) {
      for (const face of faces) {
        expect(contrast(c, face), `${c} on ${face}`).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it.each(MODES)("%s — 1번 시리즈는 항상 Brand 인디고다(사용자 Accent 가 아니다)", (mode) => {
    const p = createClovirTheme(mode).palette;
    expect(p.chart[0]).toBe(CHART_SERIES[mode][0]);
    expect(p.chart[0]).toBe(p.brand.core);
  });

  /* 인접 슬롯 휘도 분리의 최대 달성치가 1.26:1 이다 — 색만으로는 2개 시리즈 이상을 절대
     못 나른다. 그래서 선 스타일이 **선택이 아니라 필수**다. 누군가 "색만으로 충분하다"고
     판단해 dash 를 지우면 여기서 걸린다. */
  it("색만으로는 시리즈를 구분할 수 없으므로 선 스타일이 1:1 로 존재한다", () => {
    expect(CHART_DASH).toHaveLength(CHART_SERIES.light.length);
    expect(CHART_DASH[0]).toBe("");
    expect(new Set(CHART_DASH).size).toBe(CHART_DASH.length);
  });
});

describe("Gradient 는 정확히 넷이다 (지시 0-1)", () => {
  it.each(MODES)("%s — shell·ai·hero·mark 넷뿐이고 전부 gradient 문법이다", (mode) => {
    const g = createClovirTheme(mode).palette.gradient;
    expect(Object.keys(g).sort()).toEqual(["ai", "hero", "mark", "shell"]);
    for (const [k, v] of Object.entries(g)) expect(String(v), k).toMatch(/gradient\(/);
  });

  it("hero 는 두 모드가 바이트 동일하다 — 로그인(Jinja)과 SPA 가 다시 갈라지지 않는다", () => {
    expect(createClovirTheme("dark").palette.gradient.hero).toBe(
      createClovirTheme("light").palette.gradient.hero,
    );
  });
});

describe("컨트롤 높이는 한 곳에서 나온다", () => {
  it("버튼·입력·탭·아이콘 버튼이 CONTROL 토큰을 쓴다", () => {
    const t = createClovirTheme("light");
    expect(t.components.MuiButton.styleOverrides.root.minHeight).toBe(CONTROL.button);
    expect(t.components.MuiButton.styleOverrides.sizeSmall.minHeight).toBe(CONTROL.buttonSm);
    expect(t.components.MuiButton.styleOverrides.sizeLarge.minHeight).toBe(CONTROL.buttonLg);
    expect(t.components.MuiOutlinedInput.styleOverrides.root.minHeight).toBe(CONTROL.input);
    expect(t.components.MuiTab.styleOverrides.root.minHeight).toBe(CONTROL.tab);
    expect(t.components.MuiIconButton.styleOverrides.root.minHeight).toBe(CONTROL.iconButton);
  });

  it("아이콘 버튼의 포인터 목표가 시각 크기보다 크다 (WCAG 2.2 Target Size)", () => {
    const root = createClovirTheme("light").components.MuiIconButton.styleOverrides.root;
    expect(CONTROL.iconButtonHit).toBeGreaterThanOrEqual(40);
    expect(CONTROL.iconButtonHit).toBeGreaterThan(CONTROL.iconButton);
    // 목표를 넓히는 방법은 `::after` 의 음수 inset 이다 — 시각 크기를 키우면 표 행이 자란다.
    const grow = -parseFloat(root["&::after"].inset);
    expect(grow * 2 + CONTROL.iconButton).toBe(CONTROL.iconButtonHit);
  });
});

describe("재양자화 단계 수 (PA-RC-0001 — 이 계약은 목업이 아니라 우리가 정한 것이다)", () => {
  it("FONT_SIZE 는 역할 이름 7단계다 (별칭 2개는 옛 소비처용)", () => {
    const roles = ["micro", "caption", "bodySm", "body", "title", "pageTitle", "readout"];
    for (const r of roles) expect(FONT_SIZE[r], r).toMatch(/rem$/);
    // 별칭은 실제 슬롯을 가리키기만 하고 새 단계를 만들지 않는다.
    expect(FONT_SIZE.sectionTitle).toBe(FONT_SIZE.title);
    expect(FONT_SIZE.statValue).toBe(FONT_SIZE.readout);
    expect(new Set(Object.values(FONT_SIZE)).size).toBe(roles.length);
  });

  /* 옛 스케일의 실제 결함은 슬롯 **수**가 아니라 **간격**이었다 — 7단계 중 4단계가 3px
     밴드(11/12/13/14) 안에 몰려 있어 위계 일을 하지 않았다. 수만 세던 위 시험은 그 상태를
     통과시켰다. 그래서 간격을 단언한다: 인접 단계는 최소 1.06배, 머리쪽(title 이후)은 최소
     1.2배. 그리고 최소 크기는 12px(0.75rem) — 11px 은 한글에서 실제로 너무 작다. */
  it("스케일이 실제로 위계를 만든다 (밴드 몰림 재발 방지)", () => {
    const order = ["micro", "caption", "bodySm", "body", "title", "pageTitle", "readout"];
    const rem = order.map((k) => parseFloat(FONT_SIZE[k]));
    expect(rem[0]).toBeGreaterThanOrEqual(0.75);
    for (let i = 1; i < rem.length; i += 1) {
      expect(rem[i] / rem[i - 1], `${order[i - 1]}->${order[i]}`).toBeGreaterThanOrEqual(1.06);
    }
    for (let i = 4; i < rem.length; i += 1) {
      expect(rem[i] / rem[i - 1], `머리쪽 ${order[i - 1]}->${order[i]}`).toBeGreaterThanOrEqual(1.2);
    }
  });

  it("역할마다 줄간격이 있고 크기가 커질수록 좁아진다", () => {
    const order = ["micro", "caption", "bodySm", "body", "title", "pageTitle", "readout"];
    for (const k of order) expect(LINE_HEIGHT[k], k).toBeGreaterThan(1);
    expect(LINE_HEIGHT.readout).toBeLessThan(LINE_HEIGHT.body);
    expect(LINE_HEIGHT.pageTitle).toBeLessThan(LINE_HEIGHT.body);
  });

  it("FONT_WEIGHT 는 5단계다 (extrabold 는 워드마크 전용 예외)", () => {
    expect(Object.keys(FONT_WEIGHT)).toHaveLength(5);
  });

  it("RADIUS 는 4개 의미 슬롯이고 계측 전면 배율이다", () => {
    expect(Object.keys(RADIUS).sort()).toEqual(["full", "lg", "md", "sm"]);
    // 18px 카드 모서리는 이 방향이 아니다. 판은 8px 다.
    expect(RADIUS.md).toBeLessThanOrEqual(8);
    expect(RADIUS.sm).toBeLessThan(RADIUS.md);
    expect(RADIUS.lg).toBeGreaterThan(RADIUS.md);
  });

  it("MUI 기본 모서리는 판의 모서리(md)다", () => {
    expect(createClovirTheme("light").shape.borderRadius).toBe(RADIUS.md);
  });
});

describe("숫자는 등폭이다 (D-141)", () => {
  it("NUMERIC 이 tabular-nums 를 선언한다", () => {
    expect(NUMERIC.fontVariantNumeric).toBe("tabular-nums");
  });

  it("판독값(statValue) variant 가 등폭을 물려받는다", () => {
    const ty = createClovirTheme("light").typography.statValue;
    expect(ty.fontVariantNumeric).toBe("tabular-nums");
  });
});

describe("제목은 고정 스케일이다 (Operate 모드 — 유동 제목을 쓰지 않는다)", () => {
  it.each(MODES)("%s — h1~h4 어디에도 clamp() 가 없다", (mode) => {
    const ty = createClovirTheme(mode).typography;
    for (const k of ["h1", "h2", "h3", "h4"]) {
      expect(String(ty[k].fontSize), k).not.toMatch(/clamp\(/);
    }
  });

  it("화면 제목(h4)은 pageTitle 슬롯을 쓴다", () => {
    expect(createClovirTheme("light").typography.h4.fontSize).toBe(FONT_SIZE.pageTitle);
  });
});

describe("대비 — 강조색 프리셋 전체 × 두 모드에서 성립해야 한다", () => {
  const accents = [DEFAULT_ACCENT, ...ACCENT_PRESETS];

  /* `sunken` 과 `brandTint` 가 추가됐다. brandTint 는 AI 영역의 실제 텍스트 면이 되면서
     처음으로 잉크를 받는 면이 됐고, sunken 은 트랙·차트 밴드 위 라벨을 받는다. */
  const inkFaces = (p) => [
    p.background.plate,
    p.background.inset,
    p.background.canvas,
    p.background.sunken,
    p.background.brandTint,
  ];

  it.each(MODES)("%s — 본문 잉크 두 단계가 다섯 면 모두에서 AA(4.5)를 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    /* W4 재작성 — 예전에는 `faint` 도 이 목록에 있었다. 그 요구가 바로 3단 잉크를
       불가능하게 만든 제약이었다(다섯 면 전부 AA 면 여유가 1.16배뿐이다). `faint` 는
       이제 본문 잉크가 아니라 AA-large 전용이고, 아래 시험이 따로 3.0 을 요구한다. */
    for (const ink of [p.text.primary, p.text.secondary]) {
      for (const face of inkFaces(p)) {
        expect(contrast(ink, face), `${ink} on ${face}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  /* W4 결정(F-W1R-03 / F-W1-02) — `faint` 를 **AA-large 자리로 한정**하고 값을 실제로 벌렸다.
     W1 은 이 자리에 "3단이 되면 상한을 올리며 그 결정을 기록하라" 고 적어 두었다. 그 기록이
     이 시험이다: 상한을 지우고 **하한을 1.45 로 올린다.** 되돌아가면 실패한다. */
  it.each(MODES)("%s — faint 는 AA-large(3:1) 를 다섯 면 모두에서 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    for (const face of inkFaces(p)) {
      const r = contrast(p.text.faint, face);
      expect(r, `faint ${p.text.faint} on ${face} = ${r.toFixed(2)}`).toBeGreaterThanOrEqual(3.0);
    }
  });

  /* `text.disabled` 는 `text.faint` 와 **다른 역할이고 다른 값이다** (W4 실측).
     둘은 오랫동안 같은 값을 공유했는데, `faint` 를 AA-large 자리로 좁히며 밝히자 MUI 가 그
     값을 쓰는 **비활성 입력 라벨**이 배포본에서 4.18:1(light)/4.47:1(dark) 로 AA 아래로
     내려갔다(`/profile` 의 «시작»·«종료»). WCAG 는 비활성 요소를 대비 요구에서 빼 주지만
     읽히지 않는 비활성 값은 여전히 나쁘다 — 사용자는 그 칸에 무엇이 설정돼 있는지 알아야
     한다. 두 값이 다시 붙으면 이 시험이 실패한다. */
  it.each(MODES)("%s — 비활성 잉크는 판 위에서 AA 를 넘고 faint 와 같은 값이 아니다", (mode) => {
    const p = createClovirTheme(mode).palette;
    expect(p.text.disabled, "disabled 가 faint 와 같은 값으로 되돌아갔다").not.toBe(p.text.faint);
    for (const face of inkFaces(p)) {
      const r = contrast(p.text.disabled, face);
      expect(r, `disabled ${p.text.disabled} on ${face} = ${r.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(MODES)("%s — 잉크가 실제로 3단이다 (secondary 와 faint 가 눈으로 갈린다)", (mode) => {
    const p = createClovirTheme(mode).palette;
    const sep = contrast(p.text.secondary, p.text.faint);
    expect(sep, `secondary vs faint = ${sep.toFixed(2)} — 1.10 이던 시절로 돌아가면 안 된다`)
      .toBeGreaterThanOrEqual(1.45);
    // primary 와 secondary 도 확실히 다른 단계여야 한다.
    expect(contrast(p.text.primary, p.text.secondary)).toBeGreaterThanOrEqual(2);
    // 세 단계의 **순서**가 유지된다 — faint 가 secondary 보다 배경에 가깝다.
    const plate = p.background.plate;
    expect(contrast(p.text.faint, plate)).toBeLessThan(contrast(p.text.secondary, plate));
    expect(contrast(p.text.secondary, plate)).toBeLessThan(contrast(p.text.primary, plate));
  });

  it.each(MODES)("%s — 상태색 strong 이 판과 자기 배경 위에서 AA 를 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    for (const key of ["success", "warning", "error", "info"]) {
      const s = p[key];
      expect(contrast(s.strong, p.background.plate), `${key} on plate`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(s.strong, s.bg), `${key} on own bg`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(MODES)("%s — 포커스 링이 다섯 면 모두에서 3:1 을 넘는다 (KBD-01/02/03)", (mode) => {
    const p = createClovirTheme(mode).palette;
    for (const face of [
      p.background.plate,
      p.background.inset,
      p.background.canvas,
      p.background.sunken,
      p.background.brandTint,
    ]) {
      expect(contrast(p.focusRing, face), `focus on ${face}`).toBeGreaterThanOrEqual(3);
    }
  });

  it.each(MODES)("%s — 사이드바 글자가 사이드바 바탕 위에서 AA 를 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    expect(contrast(p.sidebar.text, p.sidebar.bg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(p.sidebar.muted, p.sidebar.bg)).toBeGreaterThanOrEqual(4.5);
  });

  it("어떤 강조색 프리셋을 골라도 흰 글자가 그 위에서 AA 를 넘는다", () => {
    for (const a of accents) {
      const p = createClovirTheme("light", a).palette;
      expect(contrast("#FFFFFF", p.primary.main), a).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(MODES)("%s — 어떤 강조색 프리셋을 골라도 링크색이 네 면 위에서 AA 를 넘는다", (mode) => {
    for (const a of accents) {
      const p = createClovirTheme(mode, a).palette;
      /* 판 하나만 재던 것이 Dark 에서 `brandTint` 위 링크가 4.48 로 떨어진 것을 놓친 경로다
         (그래서 dark 의 strongMix 를 0.72 -> 0.62 로 내렸다). 이제 네 면 전부 잰다. */
      for (const face of [
        p.background.plate,
        p.background.inset,
        p.background.canvas,
        p.background.brandTint,
      ]) {
        expect(contrast(p.primary.dark, face), `${mode} ${a} on ${face}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});

describe("포커스가 보인다", () => {
  it.each(MODES)("%s — focus-visible 이 실제 outline 을 그린다", (mode) => {
    const t = createClovirTheme(mode);
    const root = t.components.MuiButtonBase.styleOverrides.root;
    expect(root["&.Mui-focusVisible"].outline).toContain(t.palette.focusRing);
    expect(root["&.Mui-focusVisible"].outlineOffset).toBeGreaterThan(0);
  });
});

describe("상태색은 강조색과 섞이지 않는다 (사용자가 강조색을 바꿔도 흔들리지 않는다)", () => {
  it("강조색을 바꿔도 상태색과 판 색은 그대로다", () => {
    const a = createClovirTheme("light", ACCENT_PRESETS[0]).palette;
    const b = createClovirTheme("light", ACCENT_PRESETS[3]).palette;
    expect(a.error.main).toBe(b.error.main);
    expect(a.success.main).toBe(b.success.main);
    expect(a.background.plate).toBe(b.background.plate);
    expect(a.divider).toBe(b.divider);
    // 강조색에서 파생하는 것은 primary 계열뿐이다.
    expect(a.primary.main).not.toBe(b.primary.main);
  });
});

describe("모션은 상태 전달용이다", () => {
  it("전환 시간이 Operate 상한(250ms) 안에 있다", () => {
    for (const k of ["instant", "fast", "base"]) {
      expect(parseInt(MOTION[k], 10), k).toBeLessThanOrEqual(250);
    }
  });

  it("reduced-motion 을 전역에서 존중한다", () => {
    const css = createClovirTheme("light").components.MuiCssBaseline.styleOverrides;
    expect(css["@media (prefers-reduced-motion: reduce)"]).toBeTruthy();
  });
});

describe("컴포넌트 계약 — 옛 목업 대조 시험이 지키던 목적을 런타임에서 지킨다", () => {
  it.each(MODES)("%s — 표 머리는 오목면이고 아래에 실선이 있다", (mode) => {
    const t = createClovirTheme(mode);
    const head = t.components.MuiTableCell.styleOverrides.head({ theme: t });
    expect(head.background).toBe(t.palette.background.inset);
    expect(head.borderBottom).toBe(`1px solid ${t.palette.dividerStrong}`);
  });

  it.each(MODES)("%s — 버튼은 판보다 좁은 모서리를 쓰고 높이가 밀도에 맞다", (mode) => {
    const root = createClovirTheme(mode).components.MuiButton.styleOverrides.root;
    expect(root.borderRadius).toBe(RADIUS.sm);
    // 상시 도구라 40px 은 크다. 다만 접근성 하한(터치 목표는 IconButton 이 따로 책임)은 지킨다.
    expect(root.minHeight).toBeLessThanOrEqual(36);
    expect(root.minHeight).toBeGreaterThanOrEqual(28);
  });

  it.each(MODES)("%s — 입력은 버튼과 같은 모서리를 쓴다(형태 Lock)", (mode) => {
    const root = createClovirTheme(mode).components.MuiOutlinedInput.styleOverrides.root;
    expect(root.borderRadius).toBe(RADIUS.sm);
  });

  it.each(MODES)("%s — 기본 버튼은 그라디언트가 아니라 단색이고 그림자가 없다", (mode) => {
    const t = createClovirTheme(mode);
    const cp = t.components.MuiButton.styleOverrides.containedPrimary;
    expect(cp.background).toBe(t.palette.primary.main);
    expect(cp.background).not.toMatch(/gradient/i);
    expect(cp.boxShadow).toBe("none");
  });

  it("본문은 14px 이고 한글에 맞게 자간이 좁다", () => {
    const ty = createClovirTheme("light").typography;
    expect(ty.body1.fontSize).toBe(FONT_SIZE.body);
    // MUI 기본은 +0.00938em 이라 한글이 헐거워 보인다. 음수여야 한다.
    expect(parseFloat(ty.body1.letterSpacing)).toBeLessThan(0);
    expect(ty.body1.lineHeight).toBeGreaterThanOrEqual(1.5);
  });

  it("글꼴은 Pretendard 로 시작하고 시스템 스택으로 끝난다(폰트가 안 와도 같아 보인다)", () => {
    const f = createClovirTheme("light").typography.fontFamily;
    expect(f).toMatch(/^"Pretendard Variable", Pretendard,/);
    expect(f).toMatch(/sans-serif$/);
    // 한글 폴백이 반드시 있어야 한다.
    expect(f).toMatch(/Malgun Gothic|Apple SD Gothic Neo/);
  });

  it.each(MODES)("%s — 칩이 알약이 아니다(상태·분류를 형태로 구분하려면 알약 독점을 깬다)", (mode) => {
    const root = createClovirTheme(mode).components.MuiChip.styleOverrides.root;
    expect(root.borderRadius).toBe(RADIUS.sm);
    expect(root.borderRadius).not.toBe(RADIUS.full);
  });
});
