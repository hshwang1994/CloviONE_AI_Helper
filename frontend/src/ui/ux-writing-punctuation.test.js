/* 한 문자열 안에서 독립된 두 문장을 쉼표로 이어 붙이지 않는가 (PA-RC-0002).
 *
 * `docs/UX_WRITING.md` §1 — "두 문장, 마침표로 구분한다." Product Audit이 지목한 예:
 * "공용 키트 `ui/kit.jsx`조차 마침표 관용이 6:5로 자기 안에서 갈라져 있다." 실제로 훑어보니
 * kit.jsx 두 곳(paste 초과 경고, 선택지 없음 오류)뿐 아니라 화면 20여 개에 걸쳐 "-습니다,
 * [다음 문장]" 형태의 쉼표 이어붙이기가 반복돼 있었다 — kit.jsx는 이 패턴의 일부였을 뿐,
 * 진짜 Root Cause는 저장소 전체였다.
 *
 * "-습니다/-입니다/-합니다/-됩니다/-세요/-까요" 로 끝나는 절 바로 뒤에 쉼표가 오고 그 뒤에
 * 다시 한글이 이어지면, 거의 항상 마침표가 와야 할 자리에 쉼표를 쓴 것이다(목록 나열이면 그
 * 자리에 서술어 종결 어미가 오지 않는다 — 예: "중단, 응답 없음 상태입니다"의 첫 쉼표는 이
 * 정규식에 안 걸린다). vitest는 이 문자열을 화면에 실제로 렌더링하는 테스트가 있을 때만
 * 우연히 잡는다 — 그래서 소스 전체를 직접 훑는다(jsx-comments.test.js와 같은 관용).
 *
 * 테스트 픽스처/목 데이터는 실제 사용자에게 보이는 문구가 아니므로 대상에서 뺀다. */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function sourceFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if ((name.endsWith(".js") || name.endsWith(".jsx")) && !name.includes(".test.")) out.push(full);
  }
  return out;
}

describe("UX Writing — 문장 종결 쉼표 (PA-RC-0002)", () => {
  it("‘-습니다/-세요’ 등으로 끝난 절 바로 뒤에 쉼표로 다음 문장을 잇지 않는다", () => {
    const broken = [];
    const splice = /(습니다|입니다|합니다|됩니다|세요|까요),\s*[가-힣]/g;
    for (const file of sourceFiles(SRC)) {
      const text = readFileSync(file, "utf8");
      let m;
      while ((m = splice.exec(text)) !== null) {
        const line = text.slice(0, m.index).split("\n").length;
        broken.push(`${file.replace(SRC, "src")}:${line}`);
      }
    }
    expect(broken).toEqual([]);
  });
});
