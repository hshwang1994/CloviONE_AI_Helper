import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import { useToast } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { URL_RE, copyText } from "../chat-helpers.js";
import { trimUrlTail } from "../chat-text.js";

/* 본문·카드 안 URL을 안전하게 그리는 부품 - **어떤 주소도 앵커로 만들지 않고** 복사 버튼으로
 * 낸다. 예전에는 notion.so 계열만 진짜 링크로 열어 줬는데, 그 호스트를 특별히 믿을 근거가
 * 없어졌다(chat-helpers.js 의 그 자리에 남긴 설명 참고). CardStack, RichText(말풍선 프로즈)가
 * 모두 이 부품을 공유한다 - 같은 판정을 두 번 정의하면 언젠가 한쪽만 고쳐진다. */

// 링크로 열지 않는 외부 URL. 죽은 텍스트처럼 보이지 않도록 클릭하면 주소를 복사하는
// 버튼으로 렌더한다.
export function PlainUrl({ url }) {
  const toast = useToast();
  return (
    <Tooltip title="외부 링크는 열 수 없습니다. 눌러서 주소를 복사합니다.">
      <Box
        component="button"
        type="button"
        onClick={() => copyText(url).then((ok) => toast(ok ? "주소를 복사했습니다." : "복사에 실패했습니다. 직접 선택해 복사하세요.", ok ? "success" : "error"))}
        sx={{
          font: "inherit", fontSize: FONT_SIZE.bodySm, border: 0, background: "none", p: 0, m: 0,
          textAlign: "left", cursor: "pointer", color: "text.secondary", ...KO_WORD_BREAK,
          textDecoration: "underline dotted", textUnderlineOffset: "2px",
          "&:hover, &:focus-visible": { color: "text.primary", textDecorationStyle: "solid" },
        }}
      >
        {url}
      </Box>
    </Tooltip>
  );
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면 이전엔 죽은 평문으로만 보였다. 전부
// PlainUrl(복사 버튼)로 낸다. 텍스트 노드만 쓴다(innerHTML 아님, CLAUDE.md §2).
export function linkifyText(text, keyBase) {
  const s = String(text == null ? "" : text);
  const parts = s.split(URL_RE);
  if (parts.length === 1) return s;
  // URL_RE는 공백 전까지 욕심껏 먹는다 - "(https://a.b/c)에서"처럼 뒤에 괄호·조사가 바로
  // 붙으면 그것까지 통째로 "URL"에 들어간다. 팀 채팅 말풍선(chat-text.js)이 이미 겪고
  // 고친 문제라 같은 다듬기(trimUrlTail)를 쓴다 - 잘려 나간 꼬리는 버리지 않고 바로 뒤
  // 텍스트 조각 앞에 되돌려 붙인다(글자를 잃지 않는다).
  const out = [];
  let carry = "";
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const raw = trimUrlTail(part);
      carry = part.slice(raw.length);
      out.push(<PlainUrl key={keyBase + "-u" + i} url={raw} />);
    } else {
      out.push(carry + part);
      carry = "";
    }
  });
  return out;
}
