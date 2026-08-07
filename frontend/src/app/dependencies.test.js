import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 선언한 의존성은 실제로 쓰이는 것만 (PF10).
 *
 * ## 왜 검사가 필요한가
 *
 * 안 쓰는 패키지는 번들에는 안 들어가지만 공짜가 아니다. `npm ci` 가 매번 받아 오고,
 * 취약점 경보가 뜨면 사람이 확인해야 하고, 무엇보다 **다음 사람이 "이건 왜 있지" 를
 * 판단할 수 없다.** 실제로 이 저장소에는 `recharts` 가 설치돼 있었는데, 정작 소스에는
 * "recharts 를 설치하고도 쓰지 않기로 한 이유" 라는 주석만 있었다(ui/charts/base.jsx).
 * 결정은 옳았고 정리만 안 된 것이다 — 그 상태가 오래 남으면 결정이 아니라 실수로 읽힌다.
 *
 * ## 무엇을 눈감아 주는가
 *
 * import 문에 이름이 안 나오지만 반드시 있어야 하는 것들이 있다. 그 예외를 **이유와 함께**
 * 아래에 적는다 — 예외 목록이 이유 없이 길어지면 이 검사는 곧 통과용 장식이 된다.
 */

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FRONTEND = path.resolve(SRC, "..");

/** import 로는 안 보이지만 있어야 하는 것 — 이유를 적지 않은 항목은 여기 넣지 않는다. */
const ALLOWED_WITHOUT_IMPORT = {
  "@emotion/react": "MUI 7 이 런타임에 요구하는 peer 의존성. 우리 코드가 직접 부르지 않는다.",
  "@emotion/styled": "위와 같음 — MUI 의 styled 엔진.",
};

/* **테스트 파일은 세지 않는다.** 이 파일 자체가 "framer-motion" 이라는 글자를 들고 있어서,
   테스트까지 훑으면 지운 패키지를 되돌려 놔도 '쓰이고 있다'고 판정한다 — 실제로 사보타주를
   넣어 보니 그대로 통과했다. 번들에 들어가는 것만 본다. */
function sourceFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(js|jsx|html)$/.test(entry.name) && !/\.test\./.test(entry.name)) out.push(full);
  }
  return out;
}

describe("의존성 (PF10)", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(FRONTEND, "package.json"), "utf8"));
  const files = [...sourceFiles(SRC), path.join(FRONTEND, "index.html"), path.join(FRONTEND, "vite.config.js")];
  const text = files.map((f) => fs.readFileSync(f, "utf8")).join("\n");

  it("검사할 소스를 실제로 읽었다", () => {
    // 못 읽었으면 아래 검사가 "아무 이름도 못 찾았다"가 아니라 그냥 통과해 버린다.
    expect(files.length).toBeGreaterThan(50);
    expect(text).toContain('from "@mui/material/Box"');
  });

  it("dependencies 는 전부 소스에 나타난다", () => {
    const unused = Object.keys(pkg.dependencies).filter((name) => {
      if (ALLOWED_WITHOUT_IMPORT[name]) return false;
      // `from "pkg"` 와 `from "pkg/sub/path"` 둘 다 잡는다.
      return !new RegExp(`["']${name.replace("/", "\\/")}(["'/])`).test(text);
    });
    expect(
      unused,
      "쓰지 않는 패키지는 지우거나, 왜 남겨야 하는지를 ALLOWED_WITHOUT_IMPORT 에 적어라",
    ).toEqual([]);
  });

  it("번들에 안 들어가는 것은 dependencies 에 두지 않는다", () => {
    // pretendard 는 폰트 파일의 출처다 — 파일은 app/static/fonts 에 커밋돼 있고 소스는
    // npm 패키지를 import 하지 않는다. 런타임 의존성이 아니라는 사실을 자리로 말한다.
    expect(pkg.dependencies).not.toHaveProperty("pretendard");
    expect(pkg.devDependencies).toHaveProperty("pretendard");
  });

  it("한때 있었던 미사용 패키지가 되돌아오지 않는다", () => {
    // 되돌아오면 그건 '누가 쓰려고 넣었다'는 뜻이니, 쓰는 코드와 함께 와야 한다.
    for (const gone of ["framer-motion", "recharts"]) {
      const declared = !!(pkg.dependencies[gone] || pkg.devDependencies[gone]);
      const used = new RegExp(`["']${gone}(["'/])`).test(text);
      expect(declared && !used, `${gone} 이 다시 선언됐는데 쓰는 곳이 없다`).toBe(false);
    }
  });
});
