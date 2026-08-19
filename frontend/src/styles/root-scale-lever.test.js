import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { BREAKPOINTS } from "../ui/theme.js";

/* 4K 스케일 레버와 셸의 오프셋은 **같은 경계값**을 봐야 한다.
 *
 * `styles/root.css` 는 루트 폰트사이즈를 2200/3000 에서 16→18→20px 로 올린다. 그 위에서
 * `AppShell` 은 상단바 높이(52/60/68px)만큼 본문을 내린다. 두 축이 **서로 다른 숫자**를 들고
 * 있으면 한쪽만 바뀔 때 넓은 화면에서만 어긋난다 — 실제로 그런 적이 있다: 오프셋이 rem
 * 기반 spacing 이고 상단바 높이가 px 라 2560 에서 7.5px, 3840 에서 17px 의 죽은 띠가 생겼다
 * (D-182). 그때 고친 것은 **단위**였고, 남은 위험은 **경계값**이다.
 *
 * root.css 는 순수 CSS 라 JS 상수를 보간할 수 없다. 그래서 반대로 — 시험이 두 파일을 함께
 * 읽어 같은 값인지 확인한다. 이 파일이 없으면 `BREAKPOINTS.xxl` 을 바꾼 사람은 root.css 가
 * 자기를 따라오지 않는다는 것을 배포 후에야 안다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT_CSS = readFileSync(path.join(HERE, "root.css"), "utf-8");
const APP_SHELL = readFileSync(path.join(HERE, "..", "app", "AppShell.jsx"), "utf-8");

function mediaMins(css) {
  return [...css.matchAll(/@media\s*\(min-width:\s*(\d+)px\)/g)].map((m) => Number(m[1]));
}

describe("4K 스케일 레버 — root.css 와 테마 브레이크포인트가 같은 값을 본다", () => {
  it("root.css 가 올리는 지점이 정확히 xxl · uhd 다", () => {
    const mins = mediaMins(ROOT_CSS);
    expect(mins, "root.css 의 미디어쿼리 두 개를 못 찾았다").toEqual([
      BREAKPOINTS.xxl,
      BREAKPOINTS.uhd,
    ]);
  });

  it("루트 폰트사이즈가 단계마다 실제로 커진다 (레버가 살아 있는가)", () => {
    const sizes = [...ROOT_CSS.matchAll(/--clv-root-fs:\s*([\d.]+)px/g)].map((m) => Number(m[1]));
    expect(sizes.length, "--clv-root-fs 선언이 세 단계가 아니다").toBe(3);
    expect(sizes[1]).toBeGreaterThan(sizes[0]);
    expect(sizes[2]).toBeGreaterThan(sizes[1]);
  });

  it("셸의 본문 오프셋이 같은 경계값을 **상수에서** 가져온다 (리터럴 금지)", () => {
    /* 값이 우연히 같은 것과 같은 곳에서 오는 것은 다르다. R-6 은 "Breakpoint 를 페이지마다
       따로 만들지 않는다"고 못박는다. */
    expect(APP_SHELL).toMatch(/min-width:\$\{BREAKPOINTS\.xxl\}px/);
    expect(APP_SHELL).toMatch(/min-width:\$\{BREAKPOINTS\.uhd\}px/);
    expect(APP_SHELL, "셸에 해상도 리터럴이 되돌아왔다")
      .not.toMatch(/@media \(min-width:\d{4}px\)/);
  });
});
