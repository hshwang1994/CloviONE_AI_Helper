import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 편집기가 **초기 번들에 안 들어가는지**를 코드로 확인한다 (S7 Exit · D-198).
 *
 * ## 왜 시험이 필요한가
 *
 * TipTap 과 ProseMirror 는 무겁다. 정적 `import` 한 줄이면 문서를 평생 안 여는 사람의
 * 첫 로딩에 그 무게가 얹히고, **아무 오류도 안 난다.** 증상은 "왜 이렇게 느리지" 하나뿐이라
 * 원인을 찾는 데 한참 걸린다 — MUI 를 들이면서 초기 번들이 한 번에 40% 늘었던 그때와
 * 같은 모양이다(`scripts/check_bundle_size.sh` 서문).
 *
 * 번들 예산 검사(`check_bundle_size.sh`)가 결국 잡기는 한다. 그런데 그것은 **빌드 뒤**에
 * 잡고 이유를 말해 주지 않는다. 여기서 잡으면 어느 파일의 어느 줄인지가 바로 나온다.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");

function read(rel) {
  return fs.readFileSync(path.join(SRC, rel), "utf8");
}

/* 소스 전체에서 `BlockEditor.jsx` 를 **정적으로** 들여오는 자리를 찾는다.
 * `import(...)`(동적)는 세지 않는다 — 그것이 우리가 원하는 모양이다. */
function staticImporters() {
  const found = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.(jsx?|tsx?)$/.test(entry.name)) continue;
      if (/\.test\.(jsx?|tsx?)$/.test(entry.name)) continue;
      const src = fs.readFileSync(full, "utf8");
      // `import ... from ".../BlockEditor.jsx"` — 줄 맨 앞의 `import` 만 정적이다.
      if (/^\s*import\s[^;]*from\s+["'][^"']*BlockEditor\.jsx["']/m.test(src)) {
        found.push(path.relative(SRC, full).replace(/\\/g, "/"));
      }
    }
  };
  walk(SRC);
  return found;
}

describe("블록 편집기는 늦게 실린다", () => {
  it("어느 파일도 BlockEditor 를 정적으로 들여오지 않는다", () => {
    const offenders = staticImporters();
    expect(
      offenders,
      `TipTap 이 초기 번들에 들어간다. React.lazy 로 바꿔라: ${offenders.join(", ")}`,
    ).toEqual([]);
  });

  it("문서 화면이 실제로 React.lazy 로 들여온다", () => {
    const src = read("screens/KnowledgeDoc.jsx");
    expect(src).toMatch(/React\.lazy\(\s*\(\)\s*=>\s*\n?\s*import\("\.\.\/ui\/BlockEditor\.jsx"\)/);
  });

  it("이 검사가 헛돌지 않는다 — 실제로 파일들을 훑는다", () => {
    // 위 두 시험이 **아무 파일도 안 본 채** 통과하는 상태를 막는다.
    const src = read("screens/KnowledgeDoc.jsx");
    expect(src.length).toBeGreaterThan(1000);
  });
});

describe("지식 화면도 라우트 단위로 늦게 실린다", () => {
  it("UserRoutes 가 두 화면을 React.lazy 로 들여온다", () => {
    const src = read("app/UserRoutes.jsx");
    expect(src).toMatch(/const Knowledge = React\.lazy\(/);
    expect(src).toMatch(/const KnowledgeDoc = React\.lazy\(/);
    // 정적 import 가 함께 남아 있으면 lazy 는 아무 일도 안 한다.
    expect(src).not.toMatch(/^\s*import\s[^;]*from\s+["']\.\.\/screens\/Knowledge(Doc)?\.jsx["']/m);
  });
});
