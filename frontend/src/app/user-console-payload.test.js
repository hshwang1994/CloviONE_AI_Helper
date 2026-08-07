import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 사용자 콘솔이 관리자 설정을 함께 받지 않는다 (PF7).
 *
 * ## 무슨 일이 있었나
 *
 * 알림 화면(`/notifications`)은 관리자 화면이면서 사용자 콘솔의 화면이기도 하다. 그 하나
 * 때문에 `UserRoutes.jsx` 가 `screens/registry.js` 를 통째로 정적 import 했고, 평범한
 * 사용자가 관리자 화면 스물여덟 개의 설정을 함께 내려받았다 — 평생 열지 않을 화면들이다.
 *
 * 측정(2026-08-07, 같은 트리에서 이 한 줄만 바꿔 두 번 빌드):
 *   고치기 전  UserRoutes 230.1KB + datascreen 86.6KB + registry 113.4KB = gzip 124.4KB
 *   고친 뒤    UserRoutes 230.1KB + datascreen 86.6KB                    = gzip  94.8KB
 *   → 사용자 콘솔 경로에서 gzip 29.7KB(24%) 감소
 *
 * ## 왜 소스를 읽어서 검사하는가
 *
 * 번들 크기로 검사하면 다른 이유(라이브러리 추가·화면 추가)로도 흔들려서, 언젠가 사람이
 * 숫자를 올려 버리고 끝난다. 지키려는 성질은 **"사용자 콘솔이 관리자 설정 덩어리를
 * 정적으로 들여오지 않는다"** 하나이므로 그것만 본다.
 */

const APP = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(APP, "..");

function read(rel) {
  return fs.readFileSync(path.join(SRC, rel), "utf8");
}

describe("사용자 콘솔이 내려받는 것 (PF7)", () => {
  const userRoutes = read("app/UserRoutes.jsx");

  it("검사할 파일을 실제로 읽었다", () => {
    // 경로가 틀리면 아래 검사들이 빈 문자열을 보고 전부 통과한다 — 그건 검사가 아니다.
    expect(userRoutes).toContain("function UserRoutes");
    expect(userRoutes.length).toBeGreaterThan(1000);
  });

  it("registry.js 전체를 들여오지 않는다", () => {
    expect(userRoutes).not.toMatch(/from\s+["']\.\.\/screens\/registry\.js["']/);
  });

  it("알림 화면 설정만 들여온다", () => {
    expect(userRoutes).toMatch(/from\s+["']\.\.\/screens\/registry\/notifications\.js["']/);
  });

  it("알림 설정 파일은 관리자 화면을 데리고 오지 않는다", () => {
    // 이 파일이 다른 도메인 파일을 import 하면 위 두 검사는 통과하면서 짐은 그대로 온다.
    const notif = read("screens/registry/notifications.js");
    const imports = [...notif.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    const domain = imports.filter(
      (p) => p.startsWith("./") && !["./shared.js", "./actions.js"].includes(p),
    );
    expect(domain, "알림 설정은 공용(shared/actions) 외에는 아무것도 끌고 오지 않는다").toEqual([]);
  });

  it("registry.js 는 조립만 한다 — 화면 설정을 직접 담지 않는다", () => {
    const registry = read("screens/registry.js");
    expect(registry.split("\n").length).toBeLessThan(60);
    expect(registry).toContain("export const REGISTRY");
  });

  it("쪼갠 파일들이 저장소의 크기 규칙(최대 800줄) 안에 있다", () => {
    const dir = path.join(SRC, "screens/registry");
    const files = fs.readdirSync(dir).filter((f) => f.endsWith(".js"));
    expect(files.length).toBeGreaterThan(5);
    const tooBig = files.filter(
      (f) => fs.readFileSync(path.join(dir, f), "utf8").split("\n").length > 800,
    );
    expect(tooBig).toEqual([]);
  });
});
