/**
 * 폴링이 **보이지 않는 탭에서는 멈춰야** 한다 (PF2 재확인).
 *
 * ## 계획서 항목을 확인해 보니 사실이 달랐다
 *
 * 백로그에 "폴링 20개 중 가시성 존중 1개" 라고 적혀 있었다. 실제로 `refetchInterval` 은
 * 21곳에서 쓰이고 `document.hidden` 을 직접 보는 곳은 ChatPane 하나뿐이라, 세어 보면
 * 그 말이 맞는 것처럼 보인다.
 *
 * 그런데 **라이브러리가 이미 하고 있다.** @tanstack/query-core 의 queryObserver 는
 *
 *     if (this.options.refetchIntervalInBackground || focusManager.isFocused()) { ... }
 *
 * 이고 `refetchIntervalInBackground` 의 기본값은 false 다. 즉 탭이 숨으면 주기 갱신이
 * 저절로 멈춘다. 화면마다 `document.hidden` 을 다시 쓰지 않은 것은 누락이 아니라 옳은 것이다.
 *
 * 그래서 고칠 것이 없다. 대신 **깨지기 쉬운 성질**을 여기서 고정한다:
 *   ① 어디서도 `refetchIntervalInBackground: true` 를 켜지 않는다
 *      (한 곳만 켜도 그 화면은 밤새 서버를 두드린다)
 *   ② 전역 기본값에서 그 옵션을 켜지 않는다
 *
 * 세어 보고 "없는 결함" 을 만들지 않은 기록이기도 하다.
 */
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function sourceFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...sourceFiles(full));
    } else if (/\.(js|jsx)$/.test(entry.name) && !/\.test\./.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

describe("폴링과 탭 가시성", () => {
  const files = sourceFiles(SRC);

  it("검사할 소스를 실제로 찾는다", () => {
    // 파일을 하나도 못 찾으면 아래 검사가 무조건 통과한다 - 그건 검사가 아니다.
    expect(files.length).toBeGreaterThan(50);
  });

  it("주기 갱신을 쓰는 곳이 실제로 있다", () => {
    const polling = files.filter((f) =>
      fs.readFileSync(f, "utf8").includes("refetchInterval"),
    );
    expect(polling.length).toBeGreaterThan(0);
  });

  it("숨은 탭에서도 계속 두드리도록 켠 곳이 없다", () => {
    const offenders = files.filter((f) => {
      const text = fs.readFileSync(f, "utf8");
      return /refetchIntervalInBackground\s*:\s*true/.test(text);
    });
    expect(
      offenders.map((f) => path.relative(SRC, f)),
      "이 옵션을 켜면 그 화면은 탭을 닫지 않는 한 밤새 서버를 두드린다",
    ).toEqual([]);
  });

  it("전역 기본값도 그 옵션을 켜지 않는다", () => {
    const main = fs.readFileSync(path.join(SRC, "main.jsx"), "utf8");
    expect(main).toContain("new QueryClient");
    expect(main).not.toMatch(/refetchIntervalInBackground\s*:\s*true/);
  });
});
