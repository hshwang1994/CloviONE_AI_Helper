import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import ErrorRoundedIcon from "@mui/icons-material/ErrorRounded";
import HelpRoundedIcon from "@mui/icons-material/HelpRounded";
import RadioButtonUncheckedRoundedIcon from "@mui/icons-material/RadioButtonUncheckedRounded";
import CancelRoundedIcon from "@mui/icons-material/CancelRounded";
import RemoveCircleOutlineRoundedIcon from "@mui/icons-material/RemoveCircleOutlineRounded";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { DotLabel } from "../../ui/kit.jsx";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, ICON, LINE_HEIGHT, MOTION, NAV_ANATOMY, KO_WORD_BREAK, remPx } from "../../ui/theme.js";

/* 체크리스트 한 줄 (D-534).
 *
 * 모든 줄이 **같은 격자 하나**를 쓴다: [상태 20] [이름 12rem] [설명 minmax(0,1fr)] [동작 auto] [펼침 30].
 * 그래서 상태 아이콘 · 이름 시작점 · 설명 시작점 · 동작의 오른쪽 끝 · 펼침 단추가 줄마다 같은 자리에 선다. 줄은 카드가 아니다
 * (F7 카드 규율) — 1px 구분선으로 이어지고, 지금 할 줄만 옅은 보라 면과 왼쪽 선택 레일을 받는다.
 *
 * 목록 칸이 900px(56.25rem) 보다 좁으면 설명이 이름 아래로, 동작이 설명 아래로 접힌다. 기준은 창이 아니라 **목록이 받은 폭**이다
 * (`setup-list` 컨테이너 질의) — 같은 줄을 다른 판(메일의 준비 점검)에 놓아도 그 판의 폭으로 판단한다.
 *
 * 상태는 색으로만 말하지 않는다(WCAG 1.4.1) — 아이콘 모양이 일곱 갈래 모두 다르고, 이름 아래에 상태 낱말이 함께 선다.
 */

export const STATUS_META = {
  done: { Icon: CheckCircleRoundedIcon, color: "success.main", label: "완료" },
  todo: { Icon: ErrorRoundedIcon, color: "warning.main", label: "해야 함" },
  check: { Icon: HelpRoundedIcon, color: "info.main", label: "확인 필요" },
  pending: { Icon: RadioButtonUncheckedRoundedIcon, color: "text.secondary", label: "정하지 않음" },
  problem: { Icon: CancelRoundedIcon, color: "error.main", label: "문제 있음" },
  skipped: { Icon: RemoveCircleOutlineRoundedIcon, color: "text.secondary", label: "사용하지 않음" },
  waiting: { Icon: LockRoundedIcon, color: "text.disabled", label: "앞 항목 대기" },
};

/* 크기는 아이콘 슬롯 이름이다(`theme.js::ICON`) — 줄은 nav 20, 요약 띠는 hero 24. */
export function StatusIcon({ status, size = "nav", label }) {
  const meta = STATUS_META[status] || STATUS_META.pending;
  const Icon = meta.Icon;
  return (
    <Icon
      data-status-icon={status}
      aria-hidden={label ? undefined : "true"}
      aria-label={label || undefined}
      role={label ? "img" : undefined}
      sx={{ fontSize: size === "hero" ? remPx(ICON.hero) : remPx(ICON.nav), color: meta.color, display: "block", flexShrink: 0 }}
    />
  );
}

/* 목록 그릇 — 줄들이 폭을 묻는 컨테이너다. */
export const CHECKLIST_CONTAINER = "setup-list";
const WIDE = `@container ${CHECKLIST_CONTAINER} (min-width: 56.25rem)`;

export function ChecklistList({ children, sx, ...rest }) {
  return (
    <Box
      component="ul"
      data-checklist=""
      sx={{ listStyle: "none", m: 0, p: 0, display: "grid", minWidth: 0, containerType: "inline-size", containerName: CHECKLIST_CONTAINER, ...sx }}
      {...rest}
    >
      {children}
    </Box>
  );
}

const ROW_TRACKS_NARROW = `${remPx(ICON.nav)} minmax(0,1fr) ${remPx(CONTROL.controlDense)}`;
const ROW_TRACKS_WIDE = `${remPx(ICON.nav)} 12rem minmax(0,1fr) auto ${remPx(CONTROL.controlDense)}`;

/**
 * @param status      일곱 상태 중 하나(서버가 고른다).
 * @param statusLabel 상태 낱말(서버가 준다 — 없으면 이 파일의 표).
 * @param current     지금 할 줄 — 옅은 보라 면, 왼쪽 선택 레일, 「지금 할 차례」 낱말.
 * @param actions     줄 오른쪽 끝의 30 단추들.
 * @param expanded / onToggle  펼친 칸(children)을 여닫는다. children 이 없으면 펼침 단추도 없다.
 */
export function ChecklistRow({
  id, name, nameAs = "h3", status, statusLabel, description, current = false, actions, expanded = false, onToggle,
  children, ...rest
}) {
  const panelId = `${id}-panel`;
  const hasPanel = children != null && children !== false;
  const label = statusLabel || (STATUS_META[status] || STATUS_META.pending).label;
  return (
    <Box
      component="li"
      data-checklist-row={id}
      data-row-status={status}
      data-current={current ? "" : undefined}
      data-brand-role={current ? "selected-state" : undefined}
      aria-current={current ? "step" : undefined}
      {...rest}
      sx={{
        position: "relative",
        display: "grid",
        gridTemplateColumns: ROW_TRACKS_NARROW,
        gridTemplateAreas: '"icon name toggle" ". desc desc" ". actions actions" ". panel panel"',
        gridTemplateRows: `minmax(${remPx(CONTROL.control + 10)}, auto)`,
        columnGap: 1.5,
        alignItems: "center",
        px: 1.5, py: 0.5,
        borderTop: 1, borderColor: "rule",
        "&:first-of-type": { borderTop: 0 },
        bgcolor: current ? "primary.soft" : "transparent",
        borderRadius: current ? 1 : 0,
        /* 선택 레일 — 사이드바 · 조직 트리의 활성 표지와 같은 굵기, 줄 왼쪽 가장자리. */
        "&::before": current ? {
          content: '""', position: "absolute", insetInlineStart: 0, top: "0.5rem", bottom: "0.5rem",
          width: remPx(NAV_ANATOMY.rail), borderRadius: 1, bgcolor: "primary.main",
        } : undefined,
        [WIDE]: {
          gridTemplateColumns: ROW_TRACKS_WIDE,
          gridTemplateAreas: '"icon name desc actions toggle" ". panel panel panel panel"',
          gridTemplateRows: `minmax(${remPx(48)}, auto)`,
        },
      }}
    >
      <Box sx={{ gridArea: "icon", display: "flex", alignItems: "center" }}>
        <StatusIcon status={status} />
      </Box>
      <Box sx={{ gridArea: "name", minWidth: 0, display: "grid", rowGap: 0.125, alignContent: "center" }}>
        <Typography
          component={nameAs}
          sx={{ m: 0, fontSize: FONT_SIZE.body, lineHeight: LINE_HEIGHT.bodySm, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}
        >
          {name}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", columnGap: 1, flexWrap: "wrap", minWidth: 0 }}>
          <Typography component="span" data-status-label="" sx={{ fontSize: FONT_SIZE.caption, lineHeight: LINE_HEIGHT.caption, color: "text.secondary" }}>
            {label}
          </Typography>
          {current ? <DotLabel label="지금 할 차례" tone="info" strong size="caption" /> : null}
        </Box>
      </Box>
      {description ? (
        <Typography
          component="p"
          data-row-description=""
          sx={{
            gridArea: "desc", m: 0, mt: 0.25, minWidth: 0, fontSize: FONT_SIZE.bodySm, lineHeight: LINE_HEIGHT.bodySm,
            color: "text.secondary", ...KO_WORD_BREAK,
            [WIDE]: { mt: 0 },
          }}
        >
          {description}
        </Typography>
      ) : null}
      {actions ? (
        <Box
          data-row-actions=""
          sx={{
            gridArea: "actions", display: "flex", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: 1,
            mt: 1, mb: 0.5,
            [WIDE]: { justifyContent: "flex-end", flexWrap: "nowrap", mt: 0, mb: 0 },
          }}
        >
          {actions}
        </Box>
      ) : null}
      {hasPanel ? (
        <Box sx={{ gridArea: "toggle", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <IconButton
            size="small"
            aria-label={`${name} 자세히 보기`}
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={onToggle}
          >
            <ExpandMoreRoundedIcon
              sx={{
                fontSize: remPx(ICON.nav),
                transform: expanded ? "rotate(180deg)" : "none",
                transition: `transform ${MOTION.fast} ${MOTION.ease}`,
              }}
            />
          </IconButton>
        </Box>
      ) : null}
      {hasPanel && expanded ? (
        <Box id={panelId} data-row-panel="" sx={{ gridArea: "panel", minWidth: 0, pt: 0.5, pb: 1.5 }}>
          {children}
        </Box>
      ) : null}
    </Box>
  );
}

export default ChecklistRow;
