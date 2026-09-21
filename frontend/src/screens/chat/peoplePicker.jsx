import React from "react";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { affiliation } from "../../lib/people.js";
import { foldText, includesFolded } from "../../lib/search.js";
import { PickerOption } from "../../ui/filters.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE } from "../../ui/theme.js";

/* 여러 명을 고르는 자리의 «좁히기» (W5 · F-W5D-129 ①).
 *
 * ## 왜 Combobox 가 아닌가
 *
 * `EntityCombobox` 는 **하나**를 고르는 자리의 답이다. 여기는 그룹 초대·멤버 추가처럼
 * **여러 명**을 고르고, 고른 사람이 목록에 체크로 남아야 한다. 그래서 형태는 목록으로 두고
 * 거르는 수단을 따로 준다 — 문제(후보가 데이터만큼 자란다)는 같고 답의 모양만 다르다.
 *
 * 예전에는 `/api/team-chat/directory` 전량을 스크롤 상자에 그대로 쏟았다. 서른 명일 때는
 * 훑을 수 있지만 삼백 명이면 이름을 알면서도 눈으로 찾아야 한다.
 *
 * ## 왜 디바운스가 없는가
 *
 * 이미 받은 후보를 거르는 것이라 **네트워크가 안 간다.** 디바운스는 서버를 아끼는 장치이고,
 * 여기서는 타자와 결과 사이에 지연만 만든다.
 *
 * ## 왜 한 곳에 있는가
 *
 * 같은 디렉터리를 고르는 자리가 셋이다(그룹 초대 · 1:1 상대 · 멤버 추가). 세 벌로 두면
 * 한쪽만 고쳐지는 날이 오고, 그때 증상은 "이 모달만 검색이 안 된다"라서 원인이 안 보인다.
 */
export function PeopleFilter({ value, onChange, count, total }) {
  const id = React.useId();
  return (
    <Box sx={{ mb: 1 }}>
      <TextField
        id={id}
        type="search"
        size="small"
        fullWidth
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="이름, 이메일로 좁히기"
        inputProps={{ "aria-label": "사람 좁히기" }}
      />
      {/* 조건과 결과의 관계를 말한다(C2 «결과 줄»). 조건이 없으면 아무 말도 하지 않는다 —
          「전체 12명 / 12명」은 정보가 아니라 소음이다. */}
      {value ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }} aria-live="polite">
          {count}명 / 전체 {total}명
        </Typography>
      ) : null}
    </Box>
  );
}

/* 사람 한 줄 — 검색 팝오버의 항목 정본(`PickerOption`: 한 줄 32 · 아바타 22 + 이름 + 소속 muted)을 모달 안에
 * 늘 펼쳐 둔 목록에 그대로 쓴다(핸드오프 계획 B-7). 예전에는 세 모달이 「이름 (소속)」 한 덩어리 글자를 각자
 * 손으로 그렸다.
 *
 * - `onToggle` 이 있으면 체크박스 줄이다(그룹 초대 · 멤버 추가). 줄 전체가 `<label>` 이라 이름을 눌러도 켜진다.
 * - `onPick` 이 있으면 누르면 바로 고르는 단추 줄이다(1:1 상대).
 *
 * 포커스 링은 줄이 든다 — 체크박스의 물결만으로는 키보드로 어디 있는지 보이지 않는다. */
const ROW_SX = {
  "&&": { px: 1, borderRadius: 1.5, cursor: "pointer", fontSize: FONT_SIZE.body },
};

export function PersonPickRow({ person, checked, onToggle, onPick, disabled }) {
  const name = person.display_name || person.name || "";
  const avatar = <UserAvatar person={person} name={name} size="xs" />;
  if (onToggle) {
    return (
      <PickerOption
        liProps={{ component: "label" }}
        leading={(
          <>
            <Checkbox size="small" checked={!!checked} onChange={(e) => onToggle(e.target.checked)} sx={{ m: 0 }} />
            {avatar}
          </>
        )}
        label={name}
        secondary={affiliation(person)}
        sx={[ROW_SX, {
          "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
          "&:focus-within": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
        }]}
      />
    );
  }
  return (
    <PickerOption
      liProps={{ component: "button", type: "button", disabled, onClick: onPick }}
      leading={avatar}
      label={name}
      secondary={affiliation(person)}
      sx={[ROW_SX, {
        "&&": { width: "100%", border: 0, background: "none", color: "text.primary", font: "inherit", textAlign: "left" },
        "&:hover:not(:disabled)": { bgcolor: (t) => alpha(t.palette.primary.main, 0.06) },
        "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
        "&:disabled": { opacity: 0.6, cursor: "default" },
      }]}
    />
  );
}

/** 이름 · 이메일 · 부서 · 직급 어느 쪽으로 쳐도 걸린다.
 *
 * 이름과 이메일은 사람을 찾는 두 가지 방법이고, 부서와 직급은 목록 줄이 이름 옆에 함께 보여 주는 글자다(`affiliation`).
 * 보이는 글자로 찾을 수 있어야 하므로 「개발팀」으로도, 「팀장」으로도 좁힌다. 대조는 검색 접기이고(`lib/search.js`)
 * 칸마다 따로 본다 — 공백 · 대소문자 · 전각 표기가 달라도 같은 사람이 남는다. */
export function filterPeople(users, q) {
  if (!foldText(q)) return users || [];
  return (users || []).filter((u) => includesFolded([u.display_name, u.name, u.email, u.user_id, u.dept, u.title], q));
}
