import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { affiliation, needsOrg, personLabel } from "../lib/people.js";
import { EntityCombobox } from "./filters.jsx";
import { PersonLine } from "./UserAvatar.jsx";

/* 사람 고르개 — 검색 · 단일/다중 · **아바타 + 이름 + 부서** (§15.3).
 *
 * `EntityCombobox` 위에 세운다(§15.3 이 정한 셋 다 그렇다) — 검색·키보드·값 보존은
 * 이미 거기 있다. 이 부품이 더하는 것은 옵션 줄의 그림(아바타)과, 후보를 사람 dict
 * 배열로 그대로 받는 편의뿐이다.
 *
 * `candidates` 는 **서버가 이미 좁힌 후보**를 그대로 받는다(`app/core/people.py`
 * identity 모양: `user_id`·`display_name`·`dept`·`title`·`org`·`avatar_url`) — 이
 * 부품이 스스로 사용자 전체를 훑지 않는다. 화면마다 "이 프로젝트에 닿을 수 있는 사람"
 * 같은 다른 좁히기 규칙을 갖기 때문이다.
 */
export function UserPicker({
  label = "담당자", candidates, value, onChange, multiple = false, loading, disabled,
  myId, kind = "entity", sx, helperText, required,
}) {
  const list = candidates || [];
  const withOrg = needsOrg(list);
  const options = list.map((c) => ({
    value: c.user_id,
    label: personLabel(c, { withOrg }),
    secondary: affiliation(c, { withOrg }),
    person: c,
  }));

  return (
    <EntityCombobox
      label={label}
      kind={kind}
      value={value}
      onChange={onChange}
      options={options}
      multiple={multiple}
      loading={loading}
      disabled={disabled}
      sx={sx}
      helperText={helperText}
      required={required}
      noOptionsText="일치하는 사람이 없습니다"
      renderOption={(props, o) => {
        const { key, ...rest } = props;
        // 단일 선택은 "작성자 전체" 같은 자리표시자 옵션을 앞에 끼운다(EntityCombobox 의
        // 규약) — 그 옵션에는 person 이 없다. 사람 그림 없이 글자만 그린다.
        if (!o.person) {
          return (
            <Box component="li" key={key ?? o.value} {...rest}>
              <Typography variant="body2">{o.label}</Typography>
            </Box>
          );
        }
        return (
          <Box component="li" key={key ?? o.value} {...rest} sx={{ display: "block !important" }}>
            <PersonLine
              person={o.person}
              name={o.person.display_name}
              suffix={myId && o.value === myId ? (
                <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>(나)</Typography>
              ) : null}
              size="sm"
            />
            {/* 소속은 보조줄로 — 동명이인이 있을 때 이것이 유일한 구분 수단이다. */}
            {o.secondary ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.3, pl: "1.875rem" }}>
                {o.secondary}
              </Typography>
            ) : null}
          </Box>
        );
      }}
    />
  );
}
