import React from "react";
import Autocomplete, { createFilterOptions } from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.js";
import { FILTER_LISTBOX_SX, kindSx } from "./filters.jsx";

/* 태그 고르개 — 검색 · 다중 선택 · 새 태그 생성 · 사용 문서 수 (§15.3).
 *
 * 🔴 기본 라벨이 「기술 태그」였다. 라벨을 안 주는 자리 둘(새 문서 대화상자 · 문서 상세)이
 * 그 말을 조용히 물려받아, 같은 축이 화면마다 「태그」와 「기술 태그」 둘로 보였다.
 * 사용자에게 보이는 이름은 **태그** 하나다(문서 개편 2번).
 *
 * `EntityCombobox` 위에 세우지 않는다 — 그 부품은 **닫힌 후보 집합**을 전제한다(자유
 * 입력으로 없는 값을 만드는 것은 값 보존이지 생성이 아니다). 여기는 반대로 "목록에
 * 없으면 그 자리에서 만든다"가 핵심이라 MUI `freeSolo` + `filterOptions` 를 직접 쓴다.
 * 검색·키보드·Listbox 스타일은 `filters.jsx` 의 상수를 그대로 가져와 다른 고르개와
 * 같은 결을 유지한다.
 */
const filter = createFilterOptions();

export function useKnowledgeTags() {
  return useQuery({ queryKey: ["knowledge", "tags"], queryFn: () => api("/api/knowledge/tags") });
}

export function TagPicker({
  label = "태그", value, onChange, sx, disabled, helperText, size = "small", layout,
  required = false,
}) {
  const tagsQ = useKnowledgeTags();
  const options = tagsQ.data?.items || [];
  const selected = value || [];
  // 값은 이름 배열이다(문서 저장 계약과 같다, `tag_names`) — 서버가 없으면 만들고
  // 있으면 그것을 쓴다(`tags.ensure`)므로 화면이 id 를 미리 알 필요가 없다.
  const current = selected.map((name) => {
    const found = options.find((t) => t.name === name);
    return found || { name, document_count: null, _new: true };
  });

  return (
    <Autocomplete
      multiple
      freeSolo
      size={size}
      openOnFocus
      autoHighlight
      handleHomeEndKeys
      disabled={disabled}
      loading={tagsQ.isLoading}
      options={options}
      value={current}
      onChange={(e, next) => {
        const names = next.map((o) => (typeof o === "string" ? o : o.name)).filter(Boolean);
        onChange(Array.from(new Set(names)));
      }}
      filterOptions={(opts, params) => {
        const filtered = filter(opts, params);
        const input = params.inputValue.trim();
        const exists = input && opts.some((o) => o.name.toLowerCase() === input.toLowerCase());
        if (input && !exists) {
          filtered.push({ name: input, document_count: null, _create: true });
        }
        return filtered;
      }}
      getOptionLabel={(o) => (typeof o === "string" ? o : o.name)}
      isOptionEqualToValue={(a, b) => a.name === b.name}
      noOptionsText="일치하는 태그가 없습니다"
      loadingText="불러오는 중…"
      data-filter-kind="entity"
      sx={kindSx("entity", sx, layout)}
      ListboxProps={{ sx: FILTER_LISTBOX_SX }}
      renderOption={(props, o) => {
        const { key, ...rest } = props;
        return (
          <Box component="li" key={key ?? o.name} {...rest} sx={{ display: "flex !important", justifyContent: "space-between", gap: 1 }}>
            <Typography variant="body2">
              {o._create ? `"${o.name}" 추가` : o.name}
            </Typography>
            {!o._create && Number.isFinite(o.document_count) ? (
              <Typography variant="caption" color="text.secondary">
                문서 {o.document_count}건
              </Typography>
            ) : null}
          </Box>
        );
      }}
      renderTags={(tagValue, getTagProps) => tagValue.map((o, i) => {
        const { key, ...rest } = getTagProps({ index: i });
        return <Chip key={key ?? o.name} {...rest} size="small" label={o.name} />;
      })}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          /* 별표는 `TextField` 가 그린다 — 라벨에 손으로 적으면 다른 필수 칸과 모양이
             달라지고, 스크린 리더가 읽는 `aria-required` 도 안 붙는다. */
          required={required}
          helperText={helperText}
          InputLabelProps={{ ...params.InputLabelProps, shrink: true }}
          placeholder={selected.length ? undefined : "태그 검색 또는 입력"}
        />
      )}
    />
  );
}
