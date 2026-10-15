import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, ICON, KO_WORD_BREAK, MOTION, remPx } from "./theme.js";

/* 접기 구획 하나 — 「고급」 · 「문제 해결」처럼 처음에는 닫혀 있고 제목을 누르면 몸이 나오는 구획이다.
 *
 * 전에는 화면마다 `useState` + `aria-expanded` 단추 + 조건부 Box 를 손으로 짰다(메일 설정 넷). 같은 일을 네 번 적으면 접근성
 * 속성 · 셰브론 · 간격이 조금씩 갈린다. 여기 한 벌만 둔다:
 *  - 머리는 단추 하나(제목 + 셰브론)와 그 옆 한 줄 요약이다. 단추의 접근 가능한 이름은 제목뿐이라 요약이 바뀌어도 시험 · 음성
 *    조작이 같은 이름으로 찾는다. 단추 높이는 컨트롤 높이(34)라 같은 줄의 다른 컨트롤과 윗선이 맞는다.
 *  - 몸은 열렸을 때만 그린다(`id` 로 `aria-controls` 를 잇는다). 닫힌 몸의 폼 칸이 저장 · 검증에 섞이지 않게 하려는 뜻이다.
 *  - 상태는 비제어(`defaultOpen`)와 제어(`open` + `onToggle`) 둘 다 된다.
 * `TechDetail` 은 기술 정보 한 줄용 `<details>` 이고, 이것은 폼 구획용이다 — 둘을 합치지 않는다. */
export function Disclosure({
  id, title, summary, defaultOpen = false, open: openProp, onToggle, children, className, sx, ...rest
}) {
  const reactId = React.useId();
  const panelId = id || `k-disclosure-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const controlled = openProp != null;
  const [openState, setOpenState] = React.useState(!!defaultOpen);
  const open = controlled ? !!openProp : openState;
  const toggle = () => {
    if (!controlled) setOpenState((v) => !v);
    if (onToggle) onToggle(!open);
  };
  return (
    <Box
      component="section"
      className={className ? `k-disclosure ${className}` : "k-disclosure"}
      data-disclosure=""
      data-open={open ? "" : undefined}
      sx={(t) => ({ minWidth: 0, ...(typeof sx === "function" ? sx(t) : sx) })}
      {...rest}
    >
      <Box className="k-disclosure-head" sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap", minWidth: 0 }}>
        <ButtonBase
          onClick={toggle}
          aria-expanded={open}
          aria-controls={panelId}
          className="k-disclosure-toggle"
          sx={(t) => ({
            display: "inline-flex", alignItems: "center", gap: 0.5,
            minHeight: remPx(CONTROL.control), px: 0.5, ml: -0.5, borderRadius: 1,
            color: "text.primary", fontFamily: "inherit", textAlign: "left",
            "&.Mui-focusVisible": { outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 },
          })}
        >
          <ExpandMoreRoundedIcon
            aria-hidden="true"
            sx={{
              fontSize: remPx(ICON.nav), color: "text.secondary",
              transform: open ? "rotate(180deg)" : "none",
              transition: `transform ${MOTION.fast} ${MOTION.ease}`,
            }}
          />
          <Typography component="span" sx={{ fontSize: "0.9375rem", fontWeight: FONT_WEIGHT.semibold, lineHeight: 1.4, ...KO_WORD_BREAK }}>
            {title}
          </Typography>
        </ButtonBase>
        {summary ? (
          <Typography component="span" color="text.secondary" className="k-disclosure-summary" sx={{ fontSize: FONT_SIZE.bodySm, minWidth: 0, ...KO_WORD_BREAK }}>
            {summary}
          </Typography>
        ) : null}
      </Box>
      {open ? (
        <Box id={panelId} className="k-disclosure-panel" data-disclosure-panel="" sx={{ pt: 1.5, minWidth: 0 }}>
          {children}
        </Box>
      ) : null}
    </Box>
  );
}

export default Disclosure;
