import React from "react";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

import { EMOJI_GROUPS, EMOJI_LABELS } from "../screens/chat-compose.js";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

/* 이모지 고르기 — **부품 하나다.**
 *
 * 채팅 컴포저가 이 격자를 제 안에 갖고 있었고, 본문 편집기가 같은 것을 필요로 하면서
 * 두 번째 소비자가 됐다. 두 번째가 생기는 순간 복사할지 부품으로 뺄지가 갈리는데, 복사하면
 * 이름표(`aria-label`)와 격자 폭과 초점 표시가 화면마다 갈라진다 — 이 저장소가 카드 접기와
 * 표 정렬에서 이미 두 번 잃은 자리다.
 *
 * 이모지 표 자체는 `screens/chat-compose.js` 가 계속 소유한다. 그 파일은 DOM 없이 검증되는
 * 순수 로직 모음이고 시험이 「유니코드 문자만」과 「모든 글자에 이름표가 있다」를 거기서
 * 고정하고 있다 — 표를 옮기면 그 시험이 지키던 자리가 옮겨 다닌다.
 */

export function EmojiPicker({ anchorEl, onClose, onPick, ariaLabel = "이모지 고르기" }) {
  return (
    <Popover
      open={!!anchorEl}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{ paper: { sx: { p: 1.25, maxWidth: "20rem" }, "aria-label": ariaLabel } }}
    >
      {EMOJI_GROUPS.map((g) => (
        <Box key={g.label} sx={{ mb: 1, "&:last-of-type": { mb: 0 } }}>
          <Typography sx={{ mb: 0.5, fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.bold, color: "text.secondary" }}>
            {g.label}
          </Typography>
          {/* MUI Grid 대신 Box + sx 그리드 — 프로젝트 규약. */}
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 0.25 }}>
            {g.emojis.map((emoji) => (
              <Box
                key={emoji}
                component="button"
                type="button"
                /* 이름표는 **표준 명칭**이다(`EMOJI_LABELS`). 이모지 글자를 그대로 이름으로
                   두면 플랫폼·폰트에 따라 스크린리더가 아무것도 못 읽는다(VIS-86). */
                aria-label={EMOJI_LABELS[emoji] || emoji}
                onClick={() => onPick(emoji)}
                sx={{
                  border: 0, background: "none", cursor: "pointer", p: 0.25, borderRadius: 1,
                  fontSize: "1.125rem", lineHeight: 1.2, color: "inherit",
                  "&:hover": { bgcolor: (t) => alpha(t.palette.primary.main, 0.12) },
                  "&:focus-visible": { outline: (t) => `2px solid ${t.palette.primary.main}`, outlineOffset: "-2px" },
                }}
              >
                {emoji}
              </Box>
            ))}
          </Box>
        </Box>
      ))}
    </Popover>
  );
}
