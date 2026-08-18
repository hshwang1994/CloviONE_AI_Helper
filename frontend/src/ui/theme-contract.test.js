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
  DEFAULT_ACCENT,
  FONT_SIZE,
  FONT_WEIGHT,
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

describe("chrome 은 발광하지 않는다 (D-141)", () => {
  it.each(MODES)("%s — 사이드바 배경이 그라디언트가 아니라 단색이다", (mode) => {
    const bg = createClovirTheme(mode).palette.sidebar.bg;
    expect(bg).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(bg).not.toMatch(/gradient/i);
  });

  it.each(MODES)("%s — 사이드바가 캔버스 계열이다(짙은 남색 덩어리가 아니다)", (mode) => {
    const p = createClovirTheme(mode).palette;
    // chrome 과 본문이 같은 램프에 있는지: 캔버스와의 대비가 2 미만이면 같은 계열이다.
    expect(contrast(p.sidebar.bg, p.background.canvas)).toBeLessThan(2);
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

  it("FONT_WEIGHT 는 5단계다 (extrabold 는 워드마크 전용 예외)", () => {
    expect(Object.keys(FONT_WEIGHT)).toHaveLength(5);
  });

  it("RADIUS 는 4개 의미 슬롯이고 계측 전면 배율이다", () => {
    expect(Object.keys(RADIUS).sort()).toEqual(["full", "lg", "md", "sm"]);
    // 18px 카드 모서리는 이 방향이 아니다. 판은 6px 다.
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

  it.each(MODES)("%s — 본문·보조·희미 글자가 세 면 모두에서 AA(4.5)를 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    const faces = [p.background.plate, p.background.inset, p.background.canvas];
    const inks = [p.text.primary, p.text.secondary, p.text.faint];
    for (const ink of inks) {
      for (const face of faces) {
        expect(contrast(ink, face), `${ink} on ${face}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it.each(MODES)("%s — 상태색 strong 이 판과 자기 배경 위에서 AA 를 넘는다", (mode) => {
    const p = createClovirTheme(mode).palette;
    for (const key of ["success", "warning", "error", "info"]) {
      const s = p[key];
      expect(contrast(s.strong, p.background.plate), `${key} on plate`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(s.strong, s.bg), `${key} on own bg`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it.each(MODES)("%s — 포커스 링이 세 면 모두에서 3:1 을 넘는다 (KBD-01/02/03)", (mode) => {
    const p = createClovirTheme(mode).palette;
    for (const face of [p.background.plate, p.background.inset, p.background.canvas]) {
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

  it.each(MODES)("%s — 어떤 강조색 프리셋을 골라도 링크색이 판 위에서 AA 를 넘는다", (mode) => {
    for (const a of accents) {
      const p = createClovirTheme(mode, a).palette;
      expect(contrast(p.primary.dark, p.background.plate), `${mode} ${a}`).toBeGreaterThanOrEqual(4.5);
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
