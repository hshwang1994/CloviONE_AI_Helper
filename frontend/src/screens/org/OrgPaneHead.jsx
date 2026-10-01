import React from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import BusinessRoundedIcon from "@mui/icons-material/BusinessRounded";
import GroupsRoundedIcon from "@mui/icons-material/GroupsRounded";
import { Button, OverflowMenu } from "../../ui/kit.jsx";
import { PaneHead } from "../../ui/Workspace.jsx";
import { FONT_SIZE, ICON, remPx } from "../../ui/theme.js";

/* 오른쪽 판 머리 (O1 · D-533) — 고른 조직이나 부서가 **무엇이고 어디에 있는가**, 그리고 그 대상에 대한 동작.
 *
 * 1줄 경로(작은 글자, 조상을 누르면 그 노드로), 2줄 머리 줄(`PaneHead` — 종류 아이콘 20 · 이름 h2 · 정상이 아닐 때만 상태 점 낱말 …
 * 주 동작 34 · 「더 보기」 34). 대상 동작은 판 머리에 선다(D-510 을 뒤집는다 — 페이지 머리는 「조직 추가」 하나다). 판 안에서도
 * 주 동작이 34 라 머리의 보조 단추보다 작아 위계가 거꾸로 읽히던 문제(D-510 의 까닭)가 없다. ID · 식별자 · 삭제 판정 같은 기술
 * 정보는 평소에 보이지 않고 「더 보기 › 상세 정보」 안에만 있다.
 *
 * 제목은 `tabIndex=-1` 이다 — 한 열 배치에서 트리를 고르면 초점이 이 제목으로 온다(`OrgWorkspace`). */

export function OrgPathLine({ crumbs = [], onPick }) {
  if (!crumbs.length) return null;
  return (
    <Box component="nav" aria-label="위치" data-org-path="" sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", columnGap: 0.5, minWidth: 0, fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
      {crumbs.map((c, i) => (
        <React.Fragment key={c.id || i}>
          {i ? <Box component="span" aria-hidden="true">›</Box> : null}
          {onPick && c.id ? (
            <ButtonBase
              onClick={() => onPick(c)}
              sx={(t) => ({
                fontSize: FONT_SIZE.caption, color: "inherit", borderRadius: 0.5,
                "&:hover": { color: "text.primary", textDecoration: "underline" },
                "&:focus-visible": { outline: `2px solid var(--clovir-focus-ring, ${t.palette.focusRing})`, outlineOffset: 1 },
              })}
            >
              {c.name}
            </ButtonBase>
          ) : <span>{c.name}</span>}
        </React.Fragment>
      ))}
    </Box>
  );
}

/** 정상이 아닐 때만 서는 상태 낱말 — 점 + 낱말(배지가 아니다, RULES §2). */
export function PaneStatus({ status }) {
  if (!status) return null;
  return (
    <Box component="span" data-pane-status="" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, fontSize: FONT_SIZE.caption, color: "text.secondary", whiteSpace: "nowrap" }}>
      <Box component="span" aria-hidden="true" sx={{ width: "0.375rem", height: "0.375rem", borderRadius: "50%", bgcolor: status.tone }} />
      {status.label}
    </Box>
  );
}

export function OrgPaneHead({ kind, name, crumbs, onPick, status, primary, menu, headingRef }) {
  const Icon = kind === "organization" ? BusinessRoundedIcon : GroupsRoundedIcon;
  const items = (menu || []).filter(Boolean);
  return (
    <PaneHead
      above={<OrgPathLine crumbs={crumbs} onPick={onPick} />}
      lead={<Icon aria-hidden="true" sx={{ fontSize: remPx(ICON.action), color: "text.secondary" }} />}
      title={name}
      titleRef={headingRef}
      meta={<PaneStatus status={status} />}
      action={(primary || items.length) ? (
        <Box role="group" aria-label={`${name} 작업`} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {items.length ? <OverflowMenu ariaLabel={`${name} 작업 더 보기`} items={items} /> : null}
          {primary ? <Button variant="primary" onClick={primary.onClick}>{primary.label}</Button> : null}
        </Box>
      ) : null}
    />
  );
}

export default OrgPaneHead;
