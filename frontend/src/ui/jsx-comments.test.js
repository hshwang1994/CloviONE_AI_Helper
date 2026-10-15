/* JSX 주석이 제대로 닫혀 있는가.
 *
 * `{/* … *​/}` 에서 닫는 `}` 를 빠뜨리면 그 뒤의 JSX 가 통째로 JS 표현식으로 읽혀
 * `Expected identifier but found "!"` 같은 **엉뚱한 위치의 파싱 오류**가 난다.
 * 실제로 이 저장소에서 한 세션에 세 번 났고(AppShell 2회, kit 1회), 매번 오류가
 * 가리키는 줄과 진짜 원인이 20~60줄 떨어져 있어 찾는 데 시간이 걸렸다.
 *
 * vitest 는 파일을 변환할 때만 이걸 잡는다 — 그 파일을 import 하는 테스트가 없으면
 * 조용히 지나간다. 그래서 소스 전체를 직접 훑는 검사를 둔다. */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { parse } from "@babel/parser";
import { describe, expect, it } from "vitest";

// jsdom 환경에서는 `import.meta.url` 이 file: 스킴이 아니라 fileURLToPath 가 던진다.
// vitest 는 `frontend/` 에서 도므로 cwd 기준이 안전하다.
const SRC = join(process.cwd(), "src");

function jsxFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...jsxFiles(full));
    else if (name.endsWith(".jsx")) out.push(full);
  }
  return out;
}

/* 문자열 리터럴 안의 `{/*` 는 주석이 아니다.
 *
 * 이 검사 자체가 소스를 정규식으로 훑기 때문에, **이 규칙을 설명하는 코드**가 걸린다:
 * `ko-wordbreak.test.jsx` 가 `t.startsWith("{/*")` 로 주석 줄을 걸러 내는데 그 안의 세 글자를
 * 열린 주석으로 읽었다. 화면 결함이 아니라 검사의 위양성이고, 실제로 두 회차에 걸쳐 빨간
 * 채로 남아 있었다(P-34 ①).
 *
 * 진짜 JSX 주석 앞에는 언제나 공백·`>`·`}`·`(` 가 온다 — 따옴표가 오는 경우는 없다.
 * 그래서 바로 앞 글자가 따옴표면 건너뛴다. 이 좁힘이 진짜 결함을 가리지 않는 이유가 그것이다.
 */
function insideStringLiteral(text, index) {
  return index > 0 && (text[index - 1] === '"' || text[index - 1] === "'" || text[index - 1] === "`");
}

describe("JSX 주석", () => {
  it("`{/*` 로 연 주석은 전부 `*/}` 로 닫힌다", () => {
    const broken = [];
    for (const file of jsxFiles(SRC)) {
      const text = readFileSync(file, "utf8");
      const opener = /\{\/\*/g;
      let m;
      while ((m = opener.exec(text)) !== null) {
        if (insideStringLiteral(text, m.index)) continue;
        const end = text.indexOf("*/", m.index + 3);
        if (end < 0 || text.slice(end, end + 3) !== "*/}") {
          const line = text.slice(0, m.index).split("\n").length;
          broken.push(`${file.replace(SRC, "src")}:${line}`);
        }
      }
    }
    expect(broken).toEqual([]);
  });

  // PA-RC-0001 작업 중 실제로 두 번 더 났다(kit.jsx StatCard, ChatPane.jsx 읽음 표시) —
  // `{sev ? ( {/* 주석 */} <Box>...` 처럼 삼항식이 여는 `(` 바로 뒤(JS 표현식 자리)에
  // `{/* */}`(JSX children 전용 문법)를 쓰면 "Expected ')' but found ..." 로 그 주석과
  // 20~60줄 떨어진 자리를 가리킨다(위 첫 테스트와 같은 원인 계열, 다른 증상). 이 자리는
  // `/* ... */`(중괄호 없이)만 유효하다.
  it("`(` 바로 뒤(JS 표현식 자리)에 `{/*` 로 시작하는 주석을 쓰지 않는다", () => {
    const broken = [];
    for (const file of jsxFiles(SRC)) {
      const text = readFileSync(file, "utf8");
      const opener = /\(\s*\{\/\*/g;
      let m;
      while ((m = opener.exec(text)) !== null) {
        if (insideStringLiteral(text, m.index + m[0].indexOf("{"))) continue;
        const line = text.slice(0, m.index).split("\n").length;
        broken.push(`${file.replace(SRC, "src")}:${line}`);
      }
    }
    expect(broken).toEqual([]);
  });
});

/* 중괄호 없이 원소 사이에 쓴 `/* … *​/` 는 주석이 아니라 **화면에 그려지는 글**이다.
 *
 * 2026-09-15 부터 AI 도우미 대화 목록의 행 동작 단추마다 「/* 행 안 동작은 30 이다(핸드오프 RULES §5) — …」가 그려졌고,
 * 줄지 않는 동작 칸에 밀려 선택한 대화의 제목이 한 글자로 줄었다(사용자가 본 「나/* 행 안 동작은 …」). 빌드도 시험도 조용했다 —
 * JSX 문법으로는 맞는 글이기 때문이다. 정규식은 주석과 글을 가르지 못하므로 파서로 JSXText 마디를 직접 본다. */
function commentTextNodes(source, file = "견본.jsx") {
  const ast = parse(source, { sourceType: "module", plugins: ["jsx"] });
  const out = [];
  const visit = (node) => {
    if (!node || typeof node.type !== "string") return;
    if (node.type === "JSXText" && /\/\*|\*\/|(^|\s)\/\/\s/.test(node.value)) {
      out.push(`${file}:${node.loc.start.line} ${node.value.trim().slice(0, 60)}`);
    }
    for (const key of Object.keys(node)) {
      if (key === "loc" || key === "start" || key === "end") continue;
      const value = node[key];
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value.type === "string") visit(value);
    }
  };
  visit(ast.program);
  return out;
}

describe("JSX 글 자식", () => {
  it("검사기는 원소 사이의 주석 글을 잡고 중괄호 안의 주석은 통과시킨다", () => {
    const bad = "const a = <Tooltip title=\"t\">\n  /* 행 안 동작 */\n  <b />\n</Tooltip>;\nconst c = <p>// 여기\n</p>;";
    const good = "const a = <Tooltip title=\"t\">\n  {/* 행 안 동작 */}\n  <b />\n</Tooltip>;\nconst u = <a href=\"http://x\">주소 http://x/y</a>;";
    expect(commentTextNodes(bad)).toHaveLength(2);
    expect(commentTextNodes(good)).toEqual([]);
  });

  it("화면 파일의 JSX 글 자식에 주석 표식이 없다", () => {
    const found = [];
    for (const file of jsxFiles(SRC)) {
      found.push(...commentTextNodes(readFileSync(file, "utf8"), file.replace(SRC, "src")));
    }
    expect(found).toEqual([]);
  });
});
