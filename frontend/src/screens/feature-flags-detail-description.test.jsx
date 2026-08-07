import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { mergeDetailFields } from "./data-screen/detailFields.js";
import { REGISTRY } from "./registry.js";

/* 기능 플래그 상세 드로어의 '설명'.
 *
 * 목록 열은 truncateCol("description", "설명", 70) — 70자를 넘으면 말줄임(…)하고 hover title로만
 * 전체를 보여준다. registry는 상세 드로어에 **전체** 설명을 보여주려고 detailFields에
 * field("description", "설명")를 따로 뒀지만, key가 목록 열과 똑같아 mergeDetailFields(key 기준,
 * columns가 먼저 오므로 columns 우선)가 그 detailFields 항목을 조용히 버린다 — 감사 로그의
 * object_id_full·백업의 path_full과 똑같은 함정을 이 화면만 피하지 못했다.
 * 그 결과 상세 드로어도 70자 말줄임 버전만 보여줘, 터치 기기(hover 없음)에서는 전체 설명을
 * 확인할 방법이 아예 없었다.
 */
describe("기능 플래그 상세: 설명 전체 노출", () => {
  it("목록 열의 70자 말줄임에 가려지지 않고 상세에서 전체 설명을 볼 수 있다", () => {
    const config = REGISTRY["feature-flags"];
    const longDesc = "가".repeat(120);
    const row = {
      name: "team_docs_enabled", description: longDesc, value: true,
      owner: "file", has_consumer: true, default: false, edit_hint: "",
    };

    const merged = mergeDetailFields(config, config.columns);
    const fullTextEntry = merged.find((f) => {
      if (!f.render) return false;
      const { container } = render(<div>{f.render(row)}</div>);
      return container.textContent === longDesc;
    });

    expect(fullTextEntry).toBeTruthy();
  });
});
