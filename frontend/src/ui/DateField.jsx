import React from "react";
import TextField from "@mui/material/TextField";

/* 날짜 고르개 — `@mui/x-date-pickers` 감싸개 (REAUDIT §15.5).
 *
 * 이 저장소 프런트에는 지금까지 날짜 라이브러리가 아예 없었다(`lib/format.js` 손짜기).
 * `native input[type=date]` 를 여기로 옮긴다 — 브라우저마다 달력 UI가 다르고(일부는 로캘을
 * 못 바꾼다), 폭·높이가 이 제품의 다른 입력과 안 맞았다.
 *
 * 실제 몸통(`DateFieldInner.jsx`)은 **지연 로드**한다 — `@mui/x-date-pickers`+`dayjs` 를
 * 이 화면이 열릴 때만 받는다(§15.8, 진입 번들 예산 320KB). `React.lazy` 가 그 경계다.
 *
 * 저장 값은 ISO 날짜 문자열('YYYY-MM-DD')이다 — 서버 계약이 안 바뀐다.
 */
const Inner = React.lazy(() => import("./DateFieldInner.jsx"));

/** 청크가 아직 안 왔을 때 — 자리만 지킨다(레이아웃이 안 튄다). 실제 입력이 오면 그 자리에
 * 그대로 들어선다. 비활성으로 보이는 것이 맞다 — 아직 누를 수 있는 것이 없다.
 * `value`·`onChange`·`disabled` 등 실제 필드용 값은 여기서 받아도 **일부러 버린다** — 이
 * 자리는 항상 비어 있고 항상 비활성이어야 한다(값을 그대로 넣으면 아직 못 누르는 칸에
 * 실제 값이 보이는 모순이 생긴다). `...rest` 로 남는 것은 `data-filter-kind` 같은 순수 DOM
 * 속성뿐이다 — 로딩 중에도 QA 프로브가 같은 종류로 인식하게 그대로 흘려보낸다. */
function DateFieldFallback({
  id, label, size = "small", sx,
  value, onChange, minDate, maxDate, disabled, error, helperText, required,
  ...rest
}) {
  return (
    <TextField
      id={id}
      fullWidth
      size={size}
      label={label}
      disabled
      value=""
      sx={sx}
      InputLabelProps={label ? { shrink: true } : undefined}
      {...rest}
    />
  );
}

export function DateField(props) {
  return (
    <React.Suspense fallback={<DateFieldFallback {...props} />}>
      <Inner {...props} />
    </React.Suspense>
  );
}

export default DateField;
