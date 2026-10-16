import React from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api.js";
import { foldedFilterOptions, splitWords } from "../lib/search.js";
import { FILTER_LISTBOX_SX, LABEL_ABOVE_SX, PrefixLabel, RowSummary, kindSx, useRowCell } from "./filters.jsx";

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
/* 목록 거르기는 **검색**이다 — 다른 고르개와 같은 접기로 본다(`lib/search.js`). 「현황제외」를 치면 「현황 제외」
   태그도 목록에 서서, 비슷한 태그가 이미 있다는 것이 새로 만들기 전에 보인다. */
const filter = foldedFilterOptions();

/* 「추가」 후보를 세울지는 **정체성**으로 가른다 — 서버 `app/knowledge/tags.py::slugify` 와 같은 규칙이다(NFKC →
 * 앞뒤 공백 제거 → casefold → 이어진 공백 한 칸). 서버가 같은 태그로 볼 이름이면 「추가」를 세우지 않는다.
 *
 * 검색 접기(`foldText`)로 가르지 않는다. 접기는 공백을 **지워서** 「현황 제외」와 「현황제외」가 서로를 찾게 하지만,
 * 서버는 둘을 다른 태그로 둔다(slug 에 유일 제약이 있다). 접기로 가르면 새 태그 「현황제외」를 만들 길이 사라진다.
 *
 * JS 에는 casefold 가 없어서 소문자로 내린 뒤 casefold 와 갈리는 글자 둘(ß → ss, ς → σ)을 손으로 맞춘다. 체로키 문자 ·
 * 이오타 아래 첨자가 붙은 그리스 문자처럼 casefold 만 다르게 접는 드문 글자는 맞추지 않는다 — 그 이름에서 화면이
 * 「추가」를 세워도 서버가 있는 태그를 찾아 쓰므로(`tags.ensure`) 태그가 둘로 갈리지 않는다. */
export function tagSlug(name) {
  const lowered = String(name ?? "").normalize("NFKC").toLowerCase().replace(/\u00DF/g, "ss").replace(/\u03C2/g, "\u03C3");
  return splitWords(lowered).join(" ");
}

export function useKnowledgeTags() {
  return useQuery({ queryKey: ["knowledge", "tags"], queryFn: () => api("/api/knowledge/tags") });
}

export function TagPicker({
  label = "태그", value, onChange, sx, disabled, helperText, size = "small", layout,
  required = false,
}) {
  const tagsQ = useKnowledgeTags();
  /* 필터 바 안이면 다른 줄 칸과 같은 모양이다 — 이름이 칸 안 접두로 서고 칸은 34 다(핸드오프 README §3).
     새 문서 · 문서 상세처럼 폼 자리는 그대로 라벨이 위에 선 36 칸이다. */
  const row = useRowCell(layout);
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
        const slug = tagSlug(input);
        const exists = !slug || opts.some((o) => tagSlug(o.name) === slug);
        return input && !exists
          ? [...filtered, { name: input, document_count: null, _create: true }]
          : filtered;
      }}
      getOptionLabel={(o) => (typeof o === "string" ? o : o.name)}
      isOptionEqualToValue={(a, b) => a.name === b.name}
      noOptionsText="일치하는 태그가 없습니다."
      loadingText="불러오는 중…"
      data-filter-kind="entity"
      sx={kindSx("entity", sx, layout, row)}
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
      renderTags={row
        /* 필터 바 줄 칸은 칩 대신 고른 태그를 한 줄로 요약한다 — 하나씩 떼는 칩은 조건 줄의 것이다(`filters.jsx::RowSummary`). */
        ? (tagValue) => <RowSummary names={tagValue.map((o) => o.name)} />
        : (tagValue, getTagProps) => tagValue.map((o, i) => {
          const { key, ...rest } = getTagProps({ index: i });
          return <Chip key={key ?? o.name} {...rest} size="small" label={o.name} />;
        })}
      renderInput={(params) => (
        <TextField
          {...params}
          label={row ? undefined : label}
          /* 별표는 `TextField` 가 그린다 — 라벨에 손으로 적으면 다른 필수 칸과 모양이
             달라지고, 스크린 리더가 읽는 `aria-required` 도 안 붙는다. */
          required={required}
          helperText={helperText}
          InputLabelProps={row ? params.InputLabelProps : { ...params.InputLabelProps, shrink: true }}
          InputProps={row
            ? { ...params.InputProps, startAdornment: <><PrefixLabel>{label}</PrefixLabel>{params.InputProps.startAdornment}</> }
            : params.InputProps}
          /* 「검색 또는 입력」은 값이 아니라 **안내**다 — 줄 칸에서 muted 로 선다(`data-row-hint`). */
          inputProps={row ? { ...params.inputProps, "aria-label": label, "data-row-hint": "" } : params.inputProps}
          /* 줄 칸에는 이름이 이미 접두로 서 있으므로 자리표시자에서 그 낱말을 뗀다(「태그 태그 검색」이
             되지 않게 — `rowAllText` 와 같은 규칙). */
          placeholder={selected.length ? undefined : (row ? "검색 또는 입력" : "태그 검색 또는 입력")}
          /* 폼 자리의 이름은 칸 위다(`filters.jsx::LABEL_ABOVE_SX`). */
          sx={row ? undefined : LABEL_ABOVE_SX}
        />
      )}
    />
  );
}
