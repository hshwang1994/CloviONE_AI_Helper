import React from "react";
import Box from "@mui/material/Box";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { FONT_SIZE } from "../ui/theme.js";

/* 상단바 검색 — 기준선의 `.top-search`.
 *
 * 입력을 여기서 직접 받지 않는다. 결과 목록이 뜰 자리가 상단바에는 없고, 커맨드 팔레트가
 * 이미 그 일(키보드 이동, 그룹, 최근 항목)을 한다. 기준선도 같은 이유로 이 자리를
 * `<button class="top-search" data-action="command">` 로 둔다 — 입력처럼 생긴 버튼이 아니라
 * **같은 기능의 더 큰 표적**이다. 그래서 커서도 text 가 아니라 pointer 다(눌리는 것이다).
 *
 * 치수는 전부 기준선에서 왔다:
 *   height 40 / border-radius 12 / border 1px rgba(255,255,255,.24)
 *   background rgba(7,12,34,.22) / padding 0 10px 0 42px
 * 왼쪽 42px 은 돋보기가 절대 위치로 앉는 자리다(`.search-ico { left:14px }`).
 */

// 기준선의 반응형 두 지점. MUI 기본 브레이크포인트(600/900)와 값이 달라 그대로 적는다.
const HIDE_KBD_BELOW = "@media (max-width:960px)";
const HIDE_BELOW = "@media (max-width:720px)";

/* WF1 R4 — 예전엔 "채팅"이 들어 있었다. app/search/models.py(SEARCH_KINDS)는 채팅을 **의도적으로,
 * 타협 없이** 뺀다(1:1 DM이 공용 검색 인덱스에 들어가는 순간 방 멤버십 확인 코드 한 줄만
 * 틀려도 남의 DM이 유출된다 — tests/security/test_search_no_chat.py가 그 경계를 못박는다).
 * 검색되지 않는 것을 검색된다고 광고하고 있었다. 실제 4종(KIND_LABELS와 맞춘다) + 메뉴로 교체. */
export default function TopSearch({ onOpen, placeholder = "티켓, 문서, 게시판, 사용자, 메뉴 검색" }) {
  return (
    <Box
      component="button"
      type="button"
      onClick={onOpen}
      aria-label="통합 검색과 명령 열기"
      sx={{
        position: "relative",
        display: "flex", alignItems: "center",
        flex: 1, maxWidth: "720px", mx: 2,
        height: "40px", pl: "42px", pr: "10px",
        border: "1px solid rgba(255,255,255,.24)", borderRadius: "12px",
        background: "rgba(7,12,34,.22)", color: "#fff",
        cursor: "pointer", textAlign: "left", font: "inherit",
        "&:hover": { background: "rgba(7,12,34,.3)" },
        "&:focus-visible": { outline: "2px solid #fff", outlineOffset: 2 },
        [HIDE_KBD_BELOW]: { maxWidth: "none" },
        [HIDE_BELOW]: { display: "none" },
      }}
    >
      {/* 기준선 `.top-search .search-ico { position:absolute; left:14px; top:9px }` — 19px 아이콘. */}
      <Box
        aria-hidden="true"
        sx={{ position: "absolute", left: "14px", top: "9px", display: "grid", opacity: 0.9 }}
      >
        <SearchRoundedIcon sx={{ fontSize: "19px" }} />
      </Box>
      <Box
        component="span"
        data-testid="top-search-placeholder"
        sx={{
          flex: 1, minWidth: 0,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          color: "rgba(255,255,255,.82)", fontSize: FONT_SIZE.bodySm,
        }}
      >
        {placeholder}
      </Box>
      {/* 기준선 `.kbd` + `.top-search .kbd { position:static; margin-left:12px }`. */}
      <Box
        component="kbd"
        sx={{
          flexShrink: 0, ml: "12px",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          border: "1px solid currentColor", borderRadius: "6px", px: "6px", py: "1px",
          fontSize: FONT_SIZE.caption, fontFamily: "inherit", opacity: 0.8,
          [HIDE_KBD_BELOW]: { display: "none" },
        }}
      >
        Ctrl K
      </Box>
    </Box>
  );
}
