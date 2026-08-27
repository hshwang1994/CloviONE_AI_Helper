import React from "react";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import dayjs from "dayjs";
import "dayjs/locale/ko";

/* `DateField` 의 실제 몸통 — **지연 로드되는 청크 하나**(§15.5·§15.8).
 *
 * `dayjs/locale/ko` 는 **정적 import** 다(동적 경로 금지 — 번들에서 빠진다, §16). 이 파일
 * 자체가 `ui/DateField.jsx` 의 `React.lazy(() => import("./DateFieldInner.jsx"))` 로만
 * 닿으므로, 이 파일이 statically import 하는 `@mui/x-date-pickers`·`dayjs` 전부가 이
 * 지연 청크 하나에 묶인다 — 진입 번들은 이 파일의 존재조차 모른다.
 *
 * `LocalizationProvider` 를 이 안에 둔 것은 "셸 한 곳에" 라는 §15.5 의 말과 얼핏 어긋나
 * 보이지만, 진짜 앱 셸(즉시 로드)에 두면 그 순간 이 패키지 전체가 진입 번들로 끌려온다.
 * 그래서 "한 곳"의 뜻을 **정의가 사는 파일 하나**로 지킨다 — 여러 `DateField` 가 화면에
 * 동시에 서도 이 컴포넌트 정의는 하나이고, provider 가 감싸는 범위도 이 부품 하나로 끝난다
 * (중첩된 provider 여러 개가 있어도 서로 값이 갈릴 일이 없다 — 전부 같은 dayjs 어댑터·
 * 같은 로케일이다).
 *
 * 저장 값은 ISO 날짜 문자열('YYYY-MM-DD')이다 — 서버 계약을 안 바꾼다. 날짜만 다루고
 * 시각은 안 다루므로(순수 달력일) UTC/KST 경계를 계산할 필요가 없다 — 그 경계는
 * `datetime-local` 필드(`FormModal` 의 `apiToKstLocal` 경로)의 몫이고 이 부품과는
 * 다른 문제다.
 */
dayjs.locale("ko");

const ISO_FMT = "YYYY-MM-DD";

export default function DateFieldInner({
  id, value, onChange, label, minDate, maxDate, disabled, error, helperText, required, size = "small", sx,
  ...rest
}) {
  const parsed = value ? dayjs(value, ISO_FMT, true) : null;
  const dateValue = parsed && parsed.isValid() ? parsed : null;

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="ko">
      <DatePicker
        label={label}
        value={dateValue}
        onChange={(next) => onChange(next && next.isValid() ? next.format(ISO_FMT) : "")}
        minDate={minDate ? dayjs(minDate, ISO_FMT, true) : undefined}
        maxDate={maxDate ? dayjs(maxDate, ISO_FMT, true) : undefined}
        disabled={disabled}
        format="YYYY-MM-DD"
        slotProps={{
          textField: {
            id, fullWidth: true, size, required, error, sx,
            helperText,
            // 폼 맥락(FormModal)은 라벨을 위에서 따로 그린다(지시 17) — 이 부품에 label 을
            // 안 주면 MUI 자신의 뜬 라벨도 안 뜬다. 필터·독립 사용처는 label 을 그대로 넘긴다.
            // `id` 를 함께 넘겨야 위 `FieldLabel` 의 `htmlFor` 가 실제 입력과 맺어진다 —
            // MUI 가 `${id}-helper-text` 도 이 id 에서 파생해 `aria-describedby` 로 건다.
            // `...rest` — `data-filter-kind` 처럼 QA 프로브가 읽는 순수 DOM 속성을 그대로
            // 흘려보낸다(§18.2). 다른 필터 부품(`ui/filters.jsx`)도 같은 방식으로 받는다.
            ...rest,
          },
          // MUI v9 부터 `slotProps.textField.InputLabelProps` 는 조용히 버려진다(콘솔 경고) —
          // 최상위 `inputLabel` 슬롯으로 옮겨야 실제로 적용된다. 구간형 필드는 비어 있어도
          // YYYY/MM/DD 자리표시가 항상 차 있어 보여 라벨이 안 줄어들면 값과 겹친다.
          inputLabel: label ? { shrink: true } : undefined,
        }}
      />
    </LocalizationProvider>
  );
}
