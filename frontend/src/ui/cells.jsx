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
 *
 * ## 왜 «비율 셀»·«상태 셀» 을 여기 더 만들지 않았나 (W6)
 *
 * C3 의 초안은 자릿수 고정(`NUMERIC`)을 **셀 컴포넌트**가 나르게 하려고 했다. 그러면 그
 * 처리를 받으려면 화면이 그 컴포넌트를 써야 하고, 안 쓴 열은 조용히 빠진다 — 실제로 그렇게
 * 여덟 열이 빠져 있었다. 지금은 **열이 자기 타입을 말하면 표가 `td` 에 직접 건다**
 * (`columnTypes.js` · D-288). 그래서 새 셀 컴포넌트가 필요 없어졌고, 쓰이지 않을 부품을
 * 만들지 않는다 — 정의만 있고 소비처가 0 인 코드는 다음 사람에게 «있다» 고 거짓말한다.
 * 아래 둘은 **모양**을 나르므로 남는다(압축 표기 · 단위 붙이기).
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
