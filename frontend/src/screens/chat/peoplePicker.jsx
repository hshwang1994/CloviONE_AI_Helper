import React from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

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

/** 이름·이메일 어느 쪽으로 쳐도 걸린다 — 사람을 찾는 두 가지 방법이다. */
export function filterPeople(users, q) {
  const s = String(q || "").trim().toLowerCase();
  if (!s) return users || [];
  return (users || []).filter((u) => {
    const hay = [u.display_name, u.name, u.email, u.user_id].filter(Boolean).join(" ").toLowerCase();
    return hay.indexOf(s) >= 0;
  });
}
