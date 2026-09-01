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
  /* 고르개는 **한 묶음이 곧 전부**다 — 200건이면 이 조직의 프로젝트 전체다(실운영 22건).
     그래서 「더 보기」도 센티넬도 없다. 목록 훅을 함께 쓰는 이유는 캐시와 질의 키를 목록
     화면과 나누기 위해서다(`project-queries.js` 의 존재 이유 그대로). */
  const q = useProjectList("page_size=200");
  const projects = q.rows;
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
