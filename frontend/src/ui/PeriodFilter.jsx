import React from "react";
import Box from "@mui/material/Box";
import ListItemIcon from "@mui/material/ListItemIcon";
import MenuItem from "@mui/material/MenuItem";
import MenuList from "@mui/material/MenuList";
import Popover from "@mui/material/Popover";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { Button } from "./kit.jsx";
import { DateField } from "./DateField.jsx";
import { PrefixLabel, RowValue, kindSx, withLabelAbove } from "./filters.jsx";
import {
  DATE_PRESETS, PERIOD_PRESET_LABEL, TIME_PRESETS, matchPreset, periodLabel, periodProblem, presetRange, rememberPreset,
} from "./period.js";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

/* 「기간」 칸 (F4 · D-530) — 필터 줄의 34 칸 하나가 키 쌍 하나를 고른다.
 *
 * 예전에는 날짜 칸 둘(라벨 위 + 36)이 필터 줄에 섰다. 그 칸만 높이와 라벨 자리가 달랐고, 칩도 둘이라 하나만 지우면 반쪽 기간이
 * 남았다. 이 칸은 다른 줄 칸과 같은 해부다 — 칸 안 접두 이름(「기간」)과 값(600, 「최근 7일」), 같은 34 높이, 같은 글자 기준선.
 * 값의 이름은 `period.js::periodLabel` 하나가 정하고, 화면의 조건 칩도 같은 함수를 부른다.
 *
 * 누르면 팝오버가 열린다: 위에 프리셋 목록(오늘 · 최근 7일 · 최근 30일 · 이번 달 · 지난달 · 전체), 아래에 직접 선택(시작 · 끝 +
 * 「적용」). 시각 쌍(`mode="datetime"`, 감사 로그)은 최근 1시간 · 24시간 · 7일 · 전체다. 날짜 칸은 늦게 불러온다(`DateField`).
 *
 *   from · to     지금 값(키 쌍 그대로 — `from`/`to` 든 `since`/`until` 이든 호출부가 이름을 안다)
 *   onChange      `({ from, to })` — 둘을 **함께** 바꾼다
 *   presets       프리셋 목록(기본은 모드별 표)
 *   emptyPreset   서버가 빈 값을 무엇으로 읽는가 — 보통 `all`, AI 사용 통계는 `30d`. 그 프리셋을 고르면 두 키를 비운다
 *   emptyLabel    빈 값의 이름을 따로 말할 때(없으면 `emptyPreset` 의 이름)
 *
 * 칸은 선택 상자의 모양을 빌린다(같은 높이 · 같은 접두 · 같은 화살표를 한 부품이 그리게) — 메뉴는 열지 않고 팝오버를 연다. 그래서
 * 보조 기술에는 「대화상자를 여는 콤보 상자」로 알린다(`aria-haspopup="dialog"`). */
export function PeriodFilter({
  label = "기간", from = "", to = "", onChange, mode = "date", presets, emptyPreset = "all", emptyLabel,
  disabled, sx, layout, now: nowProp,
}) {
  const cellRef = React.useRef(null);
  const [anchor, setAnchor] = React.useState(null);
  const [draft, setDraft] = React.useState({ from, to });
  const dialogId = React.useId();
  const open = !!anchor;
  const list = presets || (mode === "datetime" ? TIME_PRESETS : DATE_PRESETS);
  const now = nowProp || new Date();
  const value = { from: from || "", to: to || "" };
  const text = periodLabel(value, { mode, presets: list, emptyPreset, emptyLabel, now });
  const current = matchPreset(value, { mode, presets: list, emptyPreset, now }) || recalledKey(value, mode, text);
  const problem = periodProblem(draft);

  const openPopover = () => {
    if (disabled) return;
    setDraft(value);
    setAnchor(cellRef.current);
  };
  const close = () => setAnchor(null);
  const pick = (key) => {
    const at = nowProp || new Date();
    const next = key === emptyPreset ? { from: "", to: "" } : presetRange(key, { mode, now: at });
    if (!next) return;
    rememberPreset(next, key, mode);
    close();
    if (onChange) onChange(next);
  };
  const apply = (e) => {
    e.preventDefault();
    if (problem) return;
    close();
    if (onChange) onChange({ from: draft.from || "", to: draft.to || "" });
  };

  const fieldSx = withLabelAbove({ width: "100%" });
  return (
    <>
      <TextField
        ref={cellRef}
        select size="small" value="" disabled={disabled}
        data-filter-kind="period"
        sx={kindSx("period", sx, layout, true)}
        inputProps={{ "aria-label": label }}
        SelectProps={{
          displayEmpty: true,
          open: false,
          onOpen: openPopover,
          renderValue: () => (
            <>
              <PrefixLabel>{label}</PrefixLabel>
              <RowValue title={`${label} ${text}`}>{text}</RowValue>
            </>
          ),
          SelectDisplayProps: {
            "aria-haspopup": "dialog",
            "aria-expanded": open ? "true" : "false",
            "aria-controls": open ? dialogId : undefined,
          },
        }}
      >
        {/* 메뉴는 열지 않는다 — 고르는 자리는 아래 팝오버다. 빈 값 하나만 둬서 선택 상자가 값을 「모르는 값」으로 경고하지 않게 한다. */}
        <MenuItem value="" sx={{ display: "none" }} />
      </TextField>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          paper: {
            id: dialogId,
            role: "dialog",
            "aria-label": `${label} 고르기`,
            "data-period-popover": "",
            sx: { mt: 0.5, width: "18rem", maxWidth: "calc(100vw - 2rem)" },
          },
        }}
      >
        <MenuList autoFocusItem={open} dense aria-label={`${label} 프리셋`} sx={{ py: 0.5 }}>
          {list.map((key) => (
            <MenuItem
              key={key}
              role="menuitemradio"
              aria-checked={current === key}
              selected={current === key}
              data-period-preset={key}
              onClick={() => pick(key)}
            >
              <ListItemIcon sx={{ minWidth: "1.75rem" }}>
                {current === key ? <CheckRoundedIcon fontSize="small" /> : null}
              </ListItemIcon>
              {PERIOD_PRESET_LABEL[key] || key}
            </MenuItem>
          ))}
        </MenuList>
        <Box
          component="form"
          noValidate
          onSubmit={apply}
          data-period-custom=""
          sx={{ display: "grid", gap: 1.5, px: 2, pt: 1.5, pb: 2, borderTop: 1, borderColor: "divider" }}
        >
          <Typography component="h3" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold }}>직접 선택</Typography>
          {mode === "datetime" ? (
            <>
              <TextField
                type="datetime-local" size="small" label="시작 시각" value={draft.from}
                onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))}
                InputLabelProps={{ shrink: true }} sx={fieldSx}
              />
              <TextField
                type="datetime-local" size="small" label="끝 시각" value={draft.to}
                onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))}
                InputLabelProps={{ shrink: true }} sx={fieldSx}
              />
            </>
          ) : (
            <>
              <DateField
                id={`${dialogId}-from`} label="시작일" value={draft.from} disablePortal
                onChange={(v) => setDraft((d) => ({ ...d, from: v }))}
              />
              <DateField
                id={`${dialogId}-to`} label="종료일" value={draft.to} disablePortal
                onChange={(v) => setDraft((d) => ({ ...d, to: v }))}
              />
            </>
          )}
          {problem ? (
            <Typography role="alert" sx={{ fontSize: FONT_SIZE.caption, color: "error.main" }}>{problem}</Typography>
          ) : null}
          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1 }}>
            <Button size="sm" onClick={close}>취소</Button>
            <Button size="sm" variant="primary" type="submit" disabled={!!problem}>적용</Button>
          </Box>
        </Box>
      </Popover>
    </>
  );
}

/* 시각 프리셋은 시간이 흐르면 다시 맞출 수 없다 — 이름이 프리셋 이름이면(방금 고른 값) 그 프리셋을 표시한다. */
function recalledKey(value, mode, text) {
  if (mode !== "datetime" || (!value.from && !value.to)) return null;
  const hit = Object.entries(PERIOD_PRESET_LABEL).find(([, name]) => name === text);
  return hit ? hit[0] : null;
}

export default PeriodFilter;
