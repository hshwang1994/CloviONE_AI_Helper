import React from "react";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";

/* 목록 화면들이 함께 쓰는 필터 입력 부품.
 *
 * 예전에는 이 셋이 화면마다 손으로 복사돼 있었다(DataScreen 의 검색창, 문서 목록의
 * FilterSelect, 티켓 목록의 select). 같은 뜻의 부품이 세 벌이면 한쪽만 고쳐지는 날이 오고,
 * 그때 증상은 "이 화면 필터만 다르게 동작한다" 라서 원인이 안 보인다. */

/** 검색·자유 입력 확정까지의 지연. 화면마다 다르면 같은 앱에서 반응이 들쭉날쭉해진다. */
export const FILTER_DEBOUNCE_MS = 300;

/* 빈 값(전체·없음)을 고를 수 있는 select 에 반드시 함께 넘긴다.
 * MUI Select 는 값이 '' 이면 '아직 아무것도 안 골랐다'로 보고 라벨을 축소하지 않은 채
 * 입력 자리에 그대로 둔다 — 그러면 고른 값(전체·없음)이 화면에서 사라지고 상자가 빈 것처럼
 * 보인다. displayEmpty 로 빈 값의 항목 라벨을 그리게 하고, 라벨은 항상 노치로 올린다. */
export const EMPTYABLE_SELECT = { SelectProps: { displayEmpty: true }, InputLabelProps: { shrink: true } };

/* 타이핑 중인 값은 **자기가 든다** (PF4).
 *
 * 예전에는 타이핑 중인 값이 1,000줄짜리 화면 컴포넌트에 살았다. 그래서 글자 하나를 칠
 * 때마다 화면 전체가 다시 실행됐다 — 표 100행, 필터 일곱 개, 상세 드로어까지.
 *
 * 입력과 디바운스를 부품 안으로 내리면 타이핑은 이 작은 부품만 다시 그린다. 부모는
 * **확정된** 값이 바뀔 때만 다시 그린다.
 *
 * `value` 는 바깥에서 값이 바뀌는 경우(저장된 뷰 부르기, 필터 지우기, 뒤로가기)를 위한
 * 것이다. 그때는 `onCommit` 을 부르지 않는다 — 부르면 복원한 페이지 번호를 1로 되돌려,
 * 사용자가 링크를 열었는데 다른 화면을 보게 된다.
 */
export function useDebouncedCommit(value, onCommit, delay = FILTER_DEBOUNCE_MS) {
  const [draft, setDraft] = React.useState(value);
  const committed = React.useRef(value);

  React.useEffect(() => {
    if (value === committed.current) return;
    committed.current = value;
    setDraft(value);
  }, [value]);

  React.useEffect(() => {
    if (draft === committed.current) return undefined;
    const t = setTimeout(() => { committed.current = draft; onCommit(draft); }, delay);
    return () => clearTimeout(t);
  }, [draft, onCommit, delay]);

  return [draft, setDraft];
}

/* 검색창. `type="search"` 라 스크린리더·검사 모두 searchbox 로 잡는다. */
export const SearchBox = React.memo(function SearchBox({
  value, placeholder, ariaLabel, onSearch, sx = { gridColumn: { sm: "span 2" } },
}) {
  const [draft, setDraft] = useDebouncedCommit(value, onSearch);
  return (
    <TextField
      type="search"
      size="small"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder={placeholder}
      inputProps={{ "aria-label": ariaLabel }}
      InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
      sx={sx}
    />
  );
});

/* 자유 입력 필터(대분류처럼 후보 목록이 없는 값). 검색창과 같은 이유로 자기 상태를 든다. */
export const DebouncedTextField = React.memo(function DebouncedTextField({
  value, onCommit, label, placeholder, sx,
}) {
  const [draft, setDraft] = useDebouncedCommit(value, onCommit);
  return (
    <TextField
      size="small"
      label={label}
      InputLabelProps={{ shrink: true }}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder={placeholder}
      inputProps={{ maxLength: 200 }}
      sx={sx}
    />
  );
});

/* 선택 필터.
 *
 * **렌더 함수 밖(모듈 최상위)에 있어야 한다.** 화면 컴포넌트 본문 안에서 정의하면 부모가
 * 다시 그려질 때마다 React 가 다른 타입으로 보고 select 를 통째로 새로 마운트한다
 * (포커스와 열려 있던 드롭다운이 매번 날아간다).
 *
 * `options` 는 문자열 배열이거나 `{value,label}` 배열이다. 값과 보여줄 이름이 다른 필터
 * (담당자는 앱 user_id 로 나가고 화면에는 이름이 보인다)가 있어서 둘 다 받는다. */
export function FilterSelect({ label, value, onChange, options, allLabel, disabled, sx }) {
  const list = (options || []).map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  // 지금 걸린 값이 후보에 없으면(옵션이 아직 안 왔거나 이름이 바뀌었다) 맨 앞에 끼워 넣는다.
  // 안 그러면 주소에서 복원한 필터가 화면에서만 사라져, 목록은 걸러졌는데 상자는 전체로 보인다.
  if (value && !list.some((o) => o.value === value)) list.unshift({ value, label: value });
  return (
    <TextField
      select size="small" label={label} value={value} disabled={disabled} sx={sx}
      onChange={(e) => onChange(e.target.value)}
      {...EMPTYABLE_SELECT}
    >
      <MenuItem value="">{allLabel || `${label} 전체`}</MenuItem>
      {list.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
    </TextField>
  );
}

/* 부서 필터 (0060 §32) — **목록을 어느 팀 것으로 좁힐 것인가**.
 *
 * 후보는 서버가 준다(`departments.options`). 프런트가 스스로 조직도를 훑어 만들면 서버
 * 검증(`app/org/context.py`)과 갈라지고, 갈라진 쪽이 넓으면 사용자는 고를 수는 있는데
 * 404 만 보는 상자를 얻는다.
 *
 * 보여 주는 것은 이름이 아니라 **경로**다. '개발팀' 하나만 있으면 어느 줄기인지 알 수 없고,
 * 조직 개편으로 같은 이름이 다른 자리에 생기면 구분이 아예 불가능해진다.
 *
 * 고를 것이 하나뿐이면 아무것도 안 그린다 — 선택지가 하나인 선택기는 정보가 아니라 소음이고,
 * 화면만 좁힌다(부서가 하나인 조직, 팀 하나에만 속한 사람이 그렇다).
 */
export function DepartmentFilter({ departments, value, onChange, label = "부서", sx }) {
  const options = (departments && departments.options) || [];
  if (options.length < 2) return null;
  return (
    <FilterSelect
      label={label}
      value={value || ""}
      onChange={onChange}
      allLabel="내 범위 전체"
      sx={sx}
      options={options.map((o) => ({
        value: o.id,
        label: (o.path || []).map((n) => n.name).join(" › ") || o.name,
      }))}
    />
  );
}
