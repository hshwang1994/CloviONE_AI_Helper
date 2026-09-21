import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { KO_WORD_BREAK } from "../../ui/theme.js";

/* 상세 판 머리 — 조직 판과 부서 판이 **같은 모양**으로 선다.
 *
 * 왼쪽은 「무엇을 고르고 있는가」(이름 · 상태 배지 · 둘째 줄의 정체 — 부서는 전체 경로, 조직은
 * 식별자), 오른쪽은 「그것에 할 수 있는 일」 묶음 하나다. 예전 판 머리는 링크 둘 · 활성/비활성 ·
 * 삭제 · 수정이 한 줄에 같은 무게로 늘어섰고, 이 화면의 주 동작(부서 추가)은 선택과 무관한 페이지
 * 머리에 있었다 — 무엇에 대한 동작인지가 자리로 드러나지 않았다.
 *
 * 폭이 모자라면(1366 · 1200 · 한 칸 배치) 동작 묶음은 **묶음째** 정체 줄 아래로 내려간다.
 * 정체 칸의 바닥 폭(`32rem`)이 그 문턱이다 — 1600 · 1920 의 판에서는 한 줄에 서고, 그보다 좁은
 * 판에서는 이름이 줄을 다 쓰고 동작이 그 아래 왼쪽에서 시작한다. 묶음 안은 줄바꿈하지 않는다.
 *
 * 제목은 `tabIndex=-1` 이다 — 한 칸 배치에서 트리를 고르면 초점이 이 제목으로 온다(OrgConsole). */
export function OrgPanelHead({ title, badges, identity, actions, actionsLabel, headingRef }) {
  return (
    <Box
      data-org-panel-head=""
      sx={{
        display: "flex", flexWrap: "wrap", alignItems: "flex-start",
        columnGap: 2, rowGap: 1.5, pb: 2, borderBottom: 1, borderColor: "divider",
      }}
    >
      <Box sx={{ flex: "1 1 32rem", minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
          <Typography
            ref={headingRef}
            tabIndex={-1}
            component="h2"
            variant="sectionTitle"
            sx={{ ...KO_WORD_BREAK, minWidth: 0 }}
          >
            {title}
          </Typography>
          {badges}
        </Box>
        {identity ? <Box sx={{ mt: 0.5, minWidth: 0 }}>{identity}</Box> : null}
      </Box>
      {actions ? (
        <Box
          role="group"
          aria-label={actionsLabel}
          sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "nowrap", flex: "0 0 auto" }}
        >
          {actions}
        </Box>
      ) : null}
    </Box>
  );
}

/* 「정보」 절의 격자 — `kit.jsx::DetailGrid` 의 줄을 `xl`(1536) 부터 두 줄기로 접는다.
 * 기본 격자는 `xxl` 부터 두 줄기라 1600 · 1920 의 판(약 900~1,200px)이 한 줄기로 길게 늘어진다.
 * 1366 · 1200 의 판은 좁아서 한 줄기가 맞다. 긴 안내 문장은 `INFO_WIDE_ROW` 로 두 줄기를 다 쓴다. */
export const INFO_GRID_SX = {
  gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" },
};
export const INFO_WIDE_ROW = { gridColumn: "1 / -1" };
