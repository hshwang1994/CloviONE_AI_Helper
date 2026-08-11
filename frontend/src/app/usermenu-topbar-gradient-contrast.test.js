import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, it, expect } from "vitest";

/* WF7(whole-product 재감사, K축 — 그라디언트 배경 위 텍스트 대비, 2026-08-11).
 *
 * QA_COVERAGE.md §11이 "그라디언트 배경 위 텍스트(상단바 전체)는 아직 아무도 재지
 * 못했다"고 정직하게 남겨 둔 공백을 직접 계산해 확인했다. 상단바(AppShell.jsx의 AppBar)
 * 배경은 `radial-gradient(circle at 78% -120%, brand.purple@0.74, transparent 44%) +
 * linear-gradient(112deg, brand.deep 0% → brand.mid 48% → brand.accent 100%)`다.
 *
 * 78% 부근(오른쪽 끝 — 실제로 UserMenu가 있는 자리)에서 보라 광원이 강조색 정지점과
 * 겹치는 최악의 지점을 계산하면, 흰 글자 대비가 4종 강조색(ACCENT_PRESETS) 전부에서
 * 3.88~4.20으로 WCAG AA(4.5) 미달이다. 그라디언트 자체("최종안"으로 확정된 디자인)는
 * 손대지 않고, 그 위에 실제로 놓이는 텍스트(계정 이름)에 옅은 검정 알약 배경을 얹어
 * 같은 최악 지점에서도 확실한 여유로 통과하게 한다.
 */

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

function alphaComposite(fgHex, alpha, bgHex) {
  const ch = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const fg = ch(fgHex);
  const bg = ch(bgHex);
  const out = fg.map((f, i) => Math.round(alpha * f + (1 - alpha) * bg[i]));
  return "#" + out.map((v) => v.toString(16).padStart(2, "0")).join("");
}

const WHITE = "#FFFFFF";
const BLACK = "#000000";
const BRAND_PURPLE = "#8E75E1";
const ACCENT_PRESETS = ["#536CD6", "#4058BD", "#6B5BC7", "#327C98"];
const AA_NORMAL_TEXT = 4.5;

describe("WF7-K01 — 상단바 그라디언트 78% 부근(UserMenu 위치) 최악 지점 대비", () => {
  it("배경 그림 없이 흰 글자를 직접 얹으면 4종 강조색 전부 AA(4.5) 미달이다(회귀 방지 — 이 계산이 계속 맞는지 고정)", () => {
    const worst = Math.min(
      ...ACCENT_PRESETS.map((a) => contrastRatio(alphaComposite(BRAND_PURPLE, 0.74, a), WHITE)),
    );
    expect(worst, `최악 지점 대비=${worst.toFixed(2)}`).toBeLessThan(AA_NORMAL_TEXT);
  });

  it("UserMenu가 실제로 옅은 검정 알약 배경(bgcolor)을 쓴다(원래 결함은 배경이 아예 없었다)", () => {
    const src = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "UserMenu.jsx"),
      "utf-8",
    );
    const start = src.indexOf("<Button");
    const block = src.slice(start, start + 1600);
    expect(block).toMatch(/bgcolor:\s*"rgba\(0,0,0,\s*\.15\)"/);
  });

  it("그 알약 배경을 최악의 그라디언트 지점에 얹어도 4종 강조색 전부 AA를 만족한다", () => {
    const PILL_ALPHA = 0.15; // UserMenu.jsx에 실제로 쓰인 값과 같아야 한다(위 시험이 배선을 고정)
    for (const accent of ACCENT_PRESETS) {
      const worstBg = alphaComposite(BRAND_PURPLE, 0.74, accent);
      const withPill = alphaComposite(BLACK, PILL_ALPHA, worstBg);
      const ratio = contrastRatio(withPill, WHITE);
      expect(ratio, `accent=${accent} worstBg=${worstBg} withPill=${withPill} ratio=${ratio.toFixed(2)}`)
        .toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    }
  });
});
