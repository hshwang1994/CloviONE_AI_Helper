import React from "react";
import Typography from "@mui/material/Typography";

import { affiliation, needsOrg, personLabel } from "../lib/people.js";
import { EntityCombobox, PickerOption } from "./filters.jsx";
import { UserAvatar } from "./UserAvatar.jsx";

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
  myId, kind = "entity", sx, helperText, required, layout, open, disablePortal, placeholder, allLabel, describe,
}) {
  const list = candidates || [];
  const withOrg = needsOrg(list);
  /* `describe(person)` — 후보가 identity 모양이 아닐 때(오프보딩 후임: 이메일 · 부서) 소속 자리에 설 낱말.
     고른 값의 글자와 검색은 「이름, 그 낱말」 전체다. */
  const options = list.map((c) => ({
    value: c.user_id,
    label: describe ? [c.display_name, describe(c)].filter(Boolean).join(", ") : personLabel(c, { withOrg }),
    secondary: describe ? describe(c) : affiliation(c, { withOrg }),
    /* 칩은 이름만 말한다 — 소속은 목록 줄과 검색이 든다(칩의 `title` 에 전체 이름이 남는다). */
    tagLabel: c.display_name,
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
      layout={layout}
      open={open}
      disablePortal={disablePortal}
      sx={sx}
      helperText={helperText}
      required={required}
      placeholder={placeholder}
      allLabel={allLabel}
      noOptionsText="일치하는 사람이 없습니다"
      myId={myId}
      renderOption={(props, o, state) => (
        /* 한 줄 32 — 아바타 22 + 이름 + 소속 muted, 고른 사람에 체크(검색 팝오버 계약).
           소속은 동명이인이 있을 때 유일한 구분 수단이라 같은 줄에 남긴다(좁으면 말줄임 + title).
           "작성자 전체" 같은 자리표시자 옵션에는 person 이 없어 그림 없이 선다. */
        <PickerOption
          liProps={{ ...props, key: props.key ?? o.value }}
          leading={o.person ? <UserAvatar person={o.person} name={o.person.display_name} size="xs" /> : null}
          label={o.person ? o.person.display_name : o.label}
          suffix={myId && o.value === myId ? (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>(나)</Typography>
          ) : null}
          secondary={o.person ? o.secondary : null}
          selected={!!(state && state.selected)}
        />
      )}
    />
  );
}
