import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Tag } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { SubHeading } from "./RelaySection.jsx";

/* 받은 편지함 아이콘 안내 (계획 M2 · M4, D-574) — 받는 쪽 메일 프로그램이 보낸 사람 자리에 그림을 그리는 조건을 제공자별로 보인다.
 *
 * 값은 서버가 준다(`GET /api/admin/mail/status` 의 `help.inbox_icon` — 제공자 · 필요한 것 · 하는 사람 · 바깥 일인가 · 덧붙임). 화면은
 * 조건을 지어내지 않는다. 서버가 아직 이 칸을 주지 않는 설치(옛 서버)나 빈 목록이면 아무것도 그리지 않는다 — 제목만 선 빈 구획은
 * 「안내가 없다」가 아니라 「무언가 덜 그려졌다」로 읽힌다.
 *
 * 이 서버 밖에서 해야 하는 일(도메인 DNS · 메일 관리자 · 인증서 발급)은 「외부」 꼬리표를 단다. 제품이 끝낼 수 없는 일을 끝낼 수
 * 있는 일처럼 보이게 하지 않는다.
 */

function itemsOf(help) {
  const list = help && Array.isArray(help.inbox_icon) ? help.inbox_icon : [];
  return list.filter((it) => it && typeof it === "object" && (it.provider || it.what));
}

export function InboxIconHelp({ help }) {
  const items = itemsOf(help);
  if (!items.length) return null;
  return (
    <Box component="section" aria-label="받은 편지함 아이콘" data-testid="mail-inbox-icon-help" sx={{ display: "grid", gap: 1, minWidth: 0 }}>
      <SubHeading>받은 편지함 아이콘</SubHeading>
      <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
        받는 쪽 메일 프로그램이 보낸 사람 자리에 그림을 보이는 조건입니다. 외부 꼬리표가 붙은 일은 이 서버 밖의 담당자가 해야 합니다.
      </Typography>
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", minWidth: 0 }}>
        {items.map((it, i) => (
          <Box
            component="li"
            key={`${it.provider || "item"}-${i}`}
            data-inbox-provider={it.provider || ""}
            data-external={it.external ? "" : undefined}
            sx={{
              display: "grid", gap: 0.25, py: 1, minWidth: 0,
              borderTop: 1, borderColor: "rule", "&:first-of-type": { borderTop: 0, pt: 0.5 },
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
              <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
                {it.provider || "기타"}
              </Typography>
              {it.external ? <Tag label="외부" /> : null}
            </Box>
            {it.what ? <Typography variant="body2" sx={KO_WORD_BREAK}>{it.what}</Typography> : null}
            {it.who ? (
              <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                {`하는 사람: ${it.who}`}
              </Typography>
            ) : null}
            {it.note ? (
              <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>{it.note}</Typography>
            ) : null}
          </Box>
        ))}
      </Box>
    </Box>
  );
}

export default InboxIconHelp;
