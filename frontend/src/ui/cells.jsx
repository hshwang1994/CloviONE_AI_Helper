import React from "react";
import Box from "@mui/material/Box";
import { fmtDateTimeCompact } from "../lib/format.js";
import { NUMERIC } from "./theme.js";

/* 데이터 유형별 표 셀 (지시 10).
 *
 * 표의 존재 이유는 **비교**다. 같은 유형의 값이 화면마다 다른 모양이면 비교가 안 되고,
 * 셀이 제멋대로 접히면 세로로 훑을 수도 없다. 유형별 렌더러를 한 곳에 둔다.
 *
 * 상태·분류는 이미 `kit.jsx` 의 `Badge`/`Tag` 가 맡는다 — 여기 있는 것은 그 둘이 다루지
 * 않는 유형(날짜·수치)이다.
 */

/** 날짜·시각 셀 — 줄바꿈 없이 한 줄, 자릿수 고정, 표 폭에 맞는 압축 표기. */
export function DateCell({ value }) {
  return (
    <Box component="span" sx={{ whiteSpace: "nowrap", ...NUMERIC }}>
      {fmtDateTimeCompact(value)}
    </Box>
  );
}

/** 수치 셀 — 자릿수를 고정해 위아래 숫자가 정확히 겹치게 한다. 단위는 값 뒤에 붙인다. */
export function NumberCell({ value, unit }) {
  if (value == null || value === "") return "-";
  return (
    <Box component="span" sx={{ whiteSpace: "nowrap", ...NUMERIC }}>
      {value}{unit ? unit : null}
    </Box>
  );
}
