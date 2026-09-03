import React from "react";

import { useAllProjects } from "../screens/project-queries.js";
import { EntityCombobox } from "./filters.jsx";

/* 프로젝트 고르개 — 검색(이름·코드) · 단일 선택 · 코드 보조 표시 (§15.3).
 *
 * 후보는 이 부품이 직접 받아 온다(`useProjectList`) — 화면마다 프로젝트 목록을 따로
 * 조회하면 같은 자료가 여러 번 왕복하고, 그중 하나만 최신인 자리가 생긴다
 * (`project-queries.js` 의 존재 이유 그대로).
 */
export function ProjectPicker({
  label = "프로젝트", value, onChange, multiple = false, disabled, sx, allLabel,
  helperText, required, extraOptions, noAllOption, placeholder, layout,
}) {
  /* 후보는 **이 조직의 프로젝트 전부**다(`useAllProjects`). 예전에는 여기서 직접
     `page_size=200` 을 적었는데 서버 상한은 100 이라 그 질의가 **매번 422** 였다 —
     후보가 0개가 되고, 고른 값의 이름을 못 찾은 고르개가 UUID 를 그대로 그렸다.
     쪽 수는 훅이 서버 상한 안에서 정한다(`project-queries.js`). */
  const q = useAllProjects();
  const projects = q.rows;
  /* `extraOptions` 는 앞에 선다 — 「공통 문서」처럼 프로젝트가 아니지만 같은 축에서
     고르는 구체 선택지다. 값이 실옵션이라 주소·서버 센티널과 무변환으로 왕복한다. */
  const options = [
    ...(extraOptions || []),
    ...projects.map((p) => ({
      value: p.id,
      label: p.name,
      secondary: p.code || "",
    })),
  ];

  return (
    <EntityCombobox
      label={label}
      kind="entity"
      value={value}
      onChange={onChange}
      options={options}
      multiple={multiple}
      loading={q.isLoading}
      disabled={disabled}
      layout={layout}
      sx={sx}
      allLabel={allLabel}
      noAllOption={noAllOption}
      placeholder={placeholder}
      helperText={helperText}
      required={required}
      noOptionsText="일치하는 프로젝트가 없습니다"
    />
  );
}
