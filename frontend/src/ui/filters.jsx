import React from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { DEBOUNCE_MS } from "./theme.js";

/* 목록 화면들이 함께 쓰는 필터 입력 부품.
 *
 * 예전에는 이 셋이 화면마다 손으로 복사돼 있었다(DataScreen 의 검색창, 문서 목록의
 * FilterSelect, 티켓 목록의 select). 같은 뜻의 부품이 세 벌이면 한쪽만 고쳐지는 날이 오고,
 * 그때 증상은 "이 화면 필터만 다르게 동작한다" 라서 원인이 안 보인다. */

/** 검색·자유 입력 확정까지의 지연. 값의 정본은 토큰이다(theme.js::DEBOUNCE_MS). */
export const FILTER_DEBOUNCE_MS = DEBOUNCE_MS.filter;

/* ── 폭은 **의미**가 정한다 (W5 · C2 «폭 배분» · R-76 · R-80) ────────────────
 *
 * 예전 규칙은 격자 트랙 하나였다: `repeat(auto-fit, minmax(11rem, 16rem))`. 그 한 줄이
 * 세 가지를 동시에 만들었다.
 *   ① **값 길이와 무관한 균등 폭.** 「상태: 전체」(4글자)와 「P. SK 하이닉스 [용인 클러스터
 *      대비]」(24글자)가 같은 255px 를 받는다. 긴 프로젝트명은 잘리고, 앞부분이 같은
 *      프로젝트끼리는 잘린 뒤 구분이 불가능해진다.
 *   ② **고아 줄.** 트랙 수가 정해져 있으니 마지막 항목 하나가 자기 줄을 통째로 쓴다.
 *   ③ **검사 불능.** `width: fit-content` 가 격자 상자를 가장 넓은 줄 폭으로 줄이므로
 *      `isolated_control_row` 가 재는 «윗줄 여유» 가 구조적으로 항상 0 이 된다 —
 *      그래서 664 페이지에서 fail 이 0 이었다. «위반이 없다» 가 아니라 «잴 수 없다» 였다.
 *
 * 그래서 격자를 버리고 **줄바꿈되는 흐름**으로 간다. 각 컨트롤은 자기 종류가 요구하는
 * 폭을 들고 다니고, 컨테이너는 폭 전체를 차지한다(그래야 남는 폭이 실제로 남는 폭이고,
 * 프로브가 그것을 잴 수 있다).
 */
export const CONTROL_KIND = {
  /* 자유 검색 — 이 줄에서 유일하게 늘어나는 것. 한없이 늘리지는 않는다(긴 입력은 읽기 어렵다). */
  search: { flex: "1 1 20rem", maxWidth: "32rem", minWidth: "12rem" },
  /* Entity(프로젝트·담당자·부서·사용자) — 값이 길고 주요 탐색 조건이다. 넉넉히 준다.
     **자란다**(단 자기 상한까지만): 줄에 남는 폭이 있으면 값이 긴 축이 그것을 가져가는
     것이 옳고, 동시에 마지막 줄에 컨트롤 하나만 덩그러니 남는 고아 줄이 줄어든다
     (지시 76 이 이름으로 지목한 상태). 균등 폭이 아니다 — 각자 **자기** basis 에서
     자기 상한까지만 자란다. */
  entity: { flex: "1 1 18rem", minWidth: "12rem", maxWidth: "24rem" },
  /* 닫힌 열거형(상태·우선순위·난이도·역할) — 값이 짧고 개수가 고정이다. 내용만큼만. */
  enum: { flex: "0 0 auto", minWidth: "8rem", maxWidth: "13rem" },
  /* 날짜 — 브라우저 기본 위젯이 요구하는 폭이 있다. */
  date: { flex: "0 0 auto", minWidth: "9.5rem", maxWidth: "12rem" },
  /* 자유 입력(후보 목록이 없는 값). */
  text: { flex: "0 1 14rem", minWidth: "10rem", maxWidth: "18rem" },
  /* 숫자 — 값이 짧고 자릿수가 정해져 있다. 「동시 실행 수」의 값은 «1» 한 글자인데 균등
     격자가 775px 를 줬다(실측 `/settings?tab=ai`) — 폭이 값에 대해 거짓말을 하면 사용자는
     그 칸에 무엇을 넣어야 하는지 잘못 짐작한다. */
  number: { flex: "0 0 auto", minWidth: "7rem", maxWidth: "10rem" },
  /* 켜짐/꺼짐 칩·체크박스. */
  toggle: { flex: "0 0 auto" },
};

/** 종류별 기본 폭에 호출부 `sx` 를 얹는다. 호출부가 이기되, 안 주면 의미가 정한다. */
export function kindSx(kind, sx) {
  const base = CONTROL_KIND[kind] || null;
  if (!base) return sx;
  if (typeof sx === "function") return (theme) => ({ ...base, ...sx(theme) });
  return { ...base, ...sx };
}

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

/* 검색창. `type="search"` 라 스크린리더·검사 모두 searchbox 로 잡는다.
 *
 * **기본 `sx` 가 없다** (W5). 예전 기본값은 `{ gridColumn: { sm: "span 2" } }` 였는데,
 * JS 기본 인자는 `undefined` 를 «안 넘긴 것» 으로 보므로 `sx={undefined}` 로 «기본을 끄겠다»
 * 는 호출부에서 오히려 **되살아났다**. 실제로 `/board`·`/ideas` 가 그 함정을 밟아 검색창이
 * 2칸을 차지했고, 그 결과 정렬 select 하나가 두 번째 줄로 혼자 밀려났다 —
 * R-76 이 이름으로 지목한 «Sort Select 하나만 아래 왼쪽에 홀로» 가 바로 이것이다.
 * `OrgTree.jsx` 는 이 함정을 알고 `sx={{}}` 로 우회하고 있었다(주석까지 달아 두었다):
 * 한 호출부가 우회로 알고 있는 기본값은 기본값이 아니라 결함이다. 폭은 이제 종류가 정한다.
 */
export const SearchBox = React.memo(function SearchBox({
  value, placeholder, ariaLabel, onSearch, sx,
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
      data-filter-kind="search"
      sx={kindSx("search", sx)}
    />
  );
});

/* 자유 입력 필터(대분류처럼 후보 목록이 없는 값). 검색창과 같은 이유로 자기 상태를 든다.
 *
 * **디바운스가 여기 있는 이유** (W5 · F-W5D-115): 예전에는 이 자리가 맨 `TextField` 였고
 * `onChange` 가 곧바로 필터 상태와 질의 키를 갱신했다 — 서버 필터인 키는 **타자 한 글자마다**
 * API 를 한 번씩 불렀다. 검색창은 이미 이 부품 계열로 디바운스를 하고 있었는데 자유 입력
 * 필터만 규칙이 갈려 있었다.
 *
 * `freeTextReason` 은 «이 자유 텍스트는 일부러 그렇다» 는 **선언**이다. 후보 목록이 존재하지
 * 않는 값(외부 시스템 식별자, 여러 object_type 을 가로지르는 대상 ID)이 그렇다. 그 **문장이
 * 그대로** DOM 에 `data-free-text` 로 남아 프로브가 그 자리를 결함으로 세지 않는다.
 *
 * **억제 마커가 아니다.** `plain_dropdown_for_entity` 는 끌 수 없는 검사이고(QA_SUPPRESSIONS
 * 규칙 4) 그것이 옳다 — 여기서 말하는 것은 «이 검사를 끄겠다» 가 아니라 «이 칸은 애초에
 * 선택기가 될 수 없다(고를 후보가 세상에 없다)» 는 **종류 선언**이다. 값이 boolean 이 아니라
 * 문장인 이유도 같다: 읽는 사람이 DOM 에서 바로 그 이유를 본다. */
export const DebouncedTextField = React.memo(function DebouncedTextField({
  value, onCommit, label, placeholder, sx, kind = "text", inputProps, freeTextReason,
}) {
  const [draft, setDraft] = useDebouncedCommit(value, onCommit);
  return (
    <TextField
      size="small"
      label={label}
      InputLabelProps={{ shrink: true }}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      /* 값이 없을 때 **아무 말도 안 하는 상자**를 만들지 않는다 (W5 재정정 — 독립 검수 실측:
         「대분류」가 모든 뷰포트에서 224px 빈 상자였다). 같은 줄의 select 들은 전부 「… 전체」
         라고 자기 상태를 말하는데 이 칸만 비어 있으면 사용자는 그것을 «덜 그려졌다» 로 읽는다.
         조건이 없는 자유 입력의 뜻은 정확히 «전체» 다 — 그 낱말을 그대로 쓴다. */
      placeholder={placeholder || "전체"}
      inputProps={{ maxLength: 200, ...inputProps }}
      data-filter-kind={kind}
      data-free-text={freeTextReason || undefined}
      sx={kindSx(kind, sx)}
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
export function FilterSelect({ label, value, onChange, options, allLabel, disabled, sx, kind = "enum" }) {
  const list = normalizeOptions(options);
  // 지금 걸린 값이 후보에 없으면(옵션이 아직 안 왔거나 이름이 바뀌었다) 맨 앞에 끼워 넣는다.
  // 안 그러면 주소에서 복원한 필터가 화면에서만 사라져, 목록은 걸러졌는데 상자는 전체로 보인다.
  if (value && !list.some((o) => o.value === value)) list.unshift({ value, label: value });
  return (
    <TextField
      select size="small" label={label} value={value} disabled={disabled}
      data-filter-kind={kind}
      sx={kindSx(kind, sx)}
      onChange={(e) => onChange(e.target.value)}
      {...EMPTYABLE_SELECT}
    >
      <MenuItem value="">{allLabel || `${label} 전체`}</MenuItem>
      {list.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
    </TextField>
  );
}

/** `["가","나"]` 와 `[{value,label,secondary}]` 를 한 모양으로 편다. */
export function normalizeOptions(options) {
  return (Array.isArray(options) ? options : []).map(
    (o) => (typeof o === "string" ? { value: o, label: o } : o),
  ).filter(Boolean);
}

/* ── Entity Selector — 검색형 Combobox (R-5 · C2 · 지시 0-2.17) ──────────────
 *
 * **`FilterSelect` 와 무엇이 다른가.** `FilterSelect` 는 값 집합이 **닫힌** 축 전용이다
 * (상태·우선순위·난이도·역할). `EntityCombobox` 는 값 집합이 **데이터가 쌓이는 만큼
 * 자란다**(프로젝트·담당자·사용자·부서·조직·일정·워크플로). 그 둘을 같은 부품으로 그리면
 * 프로젝트 200개가 스크롤 목록이 되고, 사용자는 이름을 알면서도 그것을 눈으로 찾아야 한다.
 *
 * 이 부품이 지키는 것 다섯 (전부 실측된 결함에서 나왔다):
 *   ① **검색 가능.** 입력하면 후보가 걸러진다. 지금 제품에는 이런 자리가 **0개**였다 —
 *      `plain_dropdown_for_entity` 가 664 페이지에서 pass 0 · fail 80 이었던 이유다.
 *   ② **고른 값을 끝까지 알 수 있다.** 잘리더라도 `title` 로 전체 값이 나온다(C2 «값 식별성»).
 *   ③ **후보끼리 구분된다.** 앞부분이 같은 긴 이름은 보조 식별자(부서·코드·기간)를 둘째 줄로
 *      함께 보인다 — 자르고 끝내면 「P. SK 하이닉스 [용인…」 두 개가 같은 값이 된다.
 *   ④ **주소에서 복원한 값이 사라지지 않는다.** 후보 목록에 없는 값이면 그 값 자체를 후보로
 *      끼워 넣는다(`FilterSelect` 와 같은 규율).
 *   ⑤ **키보드.** MUI Autocomplete 가 ARIA 1.2 combobox 시맨틱·화살표·Home/End·Escape 를
 *      내장한다. 새 의존성이 아니다 — 이미 `MyTickets.jsx` 의 담당자 선택이 쓰고 있다.
 */
export function EntityCombobox({
  label, value, onChange, options, loading, disabled, sx, kind = "entity", id,
  placeholder, allLabel, noOptionsText = "일치하는 항목이 없습니다", required, helperText,
  ariaLabelledBy, hideLabel,
}) {
  const list = normalizeOptions(options);
  /* «전체» 를 **항목으로** 둔다. Autocomplete 의 지우기(X)만으로도 되돌릴 수는 있지만,
     이 제품의 나머지 필터는 전부 목록 첫 줄의 「… 전체」로 되돌린다(`EMPTYABLE_SELECT`).
     한 화면에서 되돌리는 방법이 두 가지면 사용자는 둘 다 못 찾는다. 되돌릴 길이 없는
     필터는 함정이다(C2). */
  const all = { value: "", label: allLabel || `${label} 전체` };
  const withAll = [all, ...list];
  /* 값이 없으면 입력을 **비워 둔다** — 「… 전체」 는 자리표시자로 보이고 목록에도 남는다.
     값을 입력 **글자**로 넣으면(MUI Select 의 `displayEmpty` 관용) 사용자가 타이핑할 때
     그 글자 뒤에 덧붙어 후보가 0개가 된다. 실브라우저에서 확인했다: 「프로젝트 전체」 상태에서
     ArrowDown 으로 열고 「D.」를 치면 입력이 「프로젝트 전체D.」가 되어 23개가 0개가 됐다.
     보이는 결과는 자리표시자 쪽이 오히려 정확하다 — «아직 안 골랐다» 가 잉크 무게로도 드러난다. */
  const current = value
    ? (list.find((o) => String(o.value) === String(value)) || { value, label: String(value) })
    : null;
  return (
    <Autocomplete
      id={id}
      size="small"
      openOnFocus
      autoHighlight
      handleHomeEndKeys
      disableClearable
      /* 고른 값이 있는 상태에서 타이핑하면 **덧붙이지 말고 갈아 끼운다.** 없으면 입력이
         「프로젝트 전체하이닉스」가 되어 후보가 0개가 된다 — 검색형인데 검색이 안 되는 상태다.
         `clearOnBlur` 는 그 짝이다: 반쯤 친 글자를 두고 자리를 뜨면 화면의 글자와 실제 값이
         갈라진다(고른 값은 그대로인데 상자에는 다른 글자가 남는다). */
      selectOnFocus
      clearOnBlur
      disabled={disabled}
      loading={!!loading}
      options={withAll}
      value={current}
      onChange={(e, next) => onChange(next ? next.value : "")}
      getOptionLabel={(o) => (o && o.label != null ? String(o.label) : "")}
      isOptionEqualToValue={(a, b) => String(a.value) === String(b.value)}
      noOptionsText={noOptionsText}
      loadingText="불러오는 중…"
      data-filter-kind={kind}
      sx={kindSx(kind, sx)}
      renderOption={(props, o) => {
        const { key, ...rest } = props;
        return (
          <Box component="li" key={key ?? o.value} {...rest} sx={{ display: "block !important" }}>
            <Typography variant="body2" sx={{ lineHeight: 1.35 }}>{o.label}</Typography>
            {/* 보조 식별자는 **앞부분이 같은 후보를 가르는 유일한 수단**이다. 없는 항목은
                줄을 만들지 않는다 — 빈 줄이 생기면 목록 높이가 들쭉날쭉해진다. */}
            {o.secondary ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.35 }}>
                {o.secondary}
              </Typography>
            ) : null}
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          /* `hideLabel` 은 **이름이 이미 화면에 있는 자리**를 위한 것이다 — 상세 화면의
             `MetaRow` 처럼 왼쪽 열이 「부서」를 이미 적고 있으면 노치 라벨이 같은 낱말을
             한 번 더 그린다. 이름을 지우는 게 아니라 **보이는 자리에서만 뺀다**: 접근
             이름은 아래 `aria-label` 로 그대로 남는다(이름 없는 combobox 는 스크린리더도
             시험도 부를 수 없다). */
          label={hideLabel ? undefined : label}
          required={required}
          helperText={helperText}
          InputLabelProps={{ shrink: true }}
          placeholder={current ? placeholder : (placeholder || all.label)}
          /* **한 줄에 잉크 무게는 하나다** (W5 재정정 — 독립 검수 실측 2.68:1 vs 옆 select 17.24:1).
             값이 없을 때 이 상자가 말하는 「… 전체」는 자리표시자가 아니라 **고른 값**이다 —
             옆의 `FilterSelect` 는 같은 뜻을 빈 `MenuItem` 의 **본문 글자**로 그린다. 브라우저
             기본 자리표시자 투명도(0.42)를 그대로 두면 같은 뜻이 한 줄 안에서 두 무게로 서고,
             사용자는 그 차이를 «이 칸만 비어 있다» 로 읽는다. 값을 **입력 글자로** 넣지 않는
             이유는 그대로다(타이핑이 그 글자 뒤에 덧붙는다) — 무게만 맞춘다. */
          sx={{ "& .MuiInputBase-input::placeholder": { opacity: 1, color: "text.primary" } }}
          /* 잘려도 전체 값을 알 수 있어야 한다 (C2 «선택된 값 식별성»). */
          /* 라벨을 부품 밖(`FieldLabel`)이 그리는 자리에서는 이름을 **가리켜서** 잇는다 —
             `label` 을 안 넘기면 MUI 는 이름 없는 combobox 를 만들고, 그러면 스크린리더도
             시험도 그 컨트롤을 부를 수 없다. */
          inputProps={{
            ...params.inputProps,
            "aria-labelledby": ariaLabelledBy || params.inputProps["aria-labelledby"],
            "aria-label": hideLabel && !ariaLabelledBy ? label : params.inputProps["aria-label"],
            title: current ? current.label : undefined,
          }}
        />
      )}
    />
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
  /* 부서는 **Entity** 다 — 조직이 자라면 후보도 자란다. 그리고 이 축의 라벨은 경로라서
     제품에서 가장 긴 값 축에 속한다("브로드컴사업본부 › ClovirONE팀"). 닫힌 열거형용
     `FilterSelect` 로 그리면 그 경로가 255px 트랙 안에서 잘리고, 잘린 뒤에는 같은 본부의
     팀들이 서로 구분되지 않는다. 이름은 **보조 식별자**로 함께 낸다 — 조직 개편으로 같은
     이름이 다른 자리에 생기면 경로만이 둘을 가른다. */
  return (
    <EntityCombobox
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
