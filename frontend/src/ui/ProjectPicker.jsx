import React from "react";

import { useProjectList } from "../screens/project-queries.js";
import { EntityCombobox } from "./filters.jsx";

/* 프로젝트 고르개 — 검색(이름·코드) · 단일 선택 · 코드 보조 표시 (§15.3).
 *
 * 후보는 이 부품이 직접 받아 온다(`useProjectList`) — 화면마다 프로젝트 목록을 따로
 * 조회하면 같은 자료가 여러 번 왕복하고, 그중 하나만 최신인 자리가 생긴다
 * (`project-queries.js` 의 존재 이유 그대로).
 */
export function ProjectPicker({
  label = "프로젝트", value, onChange, multiple = false, disabled, sx, allLabel,
  helperText, required,
}) {
  const q = useProjectList("page_size=200");
  const projects = q.data?.items || [];
  const options = projects.map((p) => ({
    value: p.id,
    label: p.name,
    secondary: p.code || "",
  }));

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
      sx={sx}
      allLabel={allLabel}
      helperText={helperText}
      required={required}
      noOptionsText="일치하는 프로젝트가 없습니다"
    />
  );
}
