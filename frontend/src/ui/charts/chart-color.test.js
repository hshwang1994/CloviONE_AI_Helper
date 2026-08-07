import { describe, expect, it } from "vitest";

import { resolveChartColor } from "./base.jsx";
import { createClovirTheme } from "../theme.js";

/* resolveChartColor 는 "팔레트 이름이면 실제 색으로, 아니면(예: '#4058BD') 그대로 쓴다"고
 * 문서화돼 있다(charts/base.jsx). 그런데 theme.palette.cyan 처럼 **객체가 아니라 문자열인
 * 슬롯**은 `slot.main` 이 undefined 라 조건을 통과하지 못하고 원래 인자(color 문자열 "cyan")로
 * 그대로 새 버린다 - 우연히 "cyan" 이 CSS 네임드 컬러(#00FFFF)와 같아서 화면에는 뭔가 칠해지지만,
 * 라이트/다크에서 값이 다른 theme.palette.cyan(#58A9C4 / #72C0D7) 대신 **테마 모드를 무시하는
 * 고정색**이 나간다 - 이 저장소가 반복해서 잡아 온 "하드코딩 색이 테마 모드를 안 따른다" 부류다. */
describe("resolveChartColor", () => {
  it("팔레트의 문자열 색(cyan)을 테마 모드에 맞게 그대로 돌려준다", () => {
    const light = createClovirTheme("light");
    const dark = createClovirTheme("dark");
    expect(resolveChartColor(light, "cyan")).toBe(light.palette.cyan);
    expect(resolveChartColor(dark, "cyan")).toBe(dark.palette.cyan);
    // 라이트와 다크의 cyan 은 실제로 다른 색이다 - 리터럴로 새면 두 모드가 우연히 같아진다.
    expect(light.palette.cyan).not.toBe(dark.palette.cyan);
  });

  it("객체 팔레트 슬롯(success 등)은 .main 값을 쓴다", () => {
    const theme = createClovirTheme("light");
    expect(resolveChartColor(theme, "success")).toBe(theme.palette.success.main);
  });

  it("톤 별칭(ok/danger/warn)을 실제 팔레트 색으로 바꾼다", () => {
    const theme = createClovirTheme("light");
    expect(resolveChartColor(theme, "ok")).toBe(theme.palette.success.main);
    expect(resolveChartColor(theme, "danger")).toBe(theme.palette.error.main);
    expect(resolveChartColor(theme, "warn")).toBe(theme.palette.warning.main);
  });

  it("팔레트에 없는 값(hex 리터럴)은 그대로 통과시킨다", () => {
    const theme = createClovirTheme("light");
    expect(resolveChartColor(theme, "#4058BD")).toBe("#4058BD");
  });
});
