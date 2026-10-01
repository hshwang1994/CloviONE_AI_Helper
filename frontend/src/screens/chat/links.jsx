import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import { useToast } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
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
  /* 복사 실패는 토스트가 아니라 **그 주소 바로 뒤의 한 줄**이다(핸드오프 RULES §1 — 사용자가 직접 해야 할 일이 남는
     실패는 사라지는 알림으로 말하지 않는다). 다시 눌러 복사되면 걷힌다. 잘 된 복사는 그대로 토스트다. */
  const [copyFailed, setCopyFailed] = React.useState(false);
  const copy = () => copyText(url).then((ok) => {
    setCopyFailed(!ok);
    if (ok) toast("주소를 복사했습니다.", "success");
  });
  return (
    <>
    <Tooltip title="외부 링크는 열 수 없습니다. 눌러서 주소를 복사합니다.">
      <Box
        component="button"
        type="button"
        onClick={copy}
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
    {copyFailed ? (
      <Box component="span" role="alert" sx={{ display: "block", mt: 0.25, fontSize: FONT_SIZE.caption, color: "error.strong", ...KO_WORD_BREAK }}>
        복사에 실패했습니다. 직접 선택해 복사하세요.
      </Box>
    ) : null}
    </>
  );
}

/* 글 속 티켓 키를 앱 안 링크로 — **그 답의 출처에 있는 키만**이다(D-538). 모델이 지어낸 키나 남의 키는 링크가 되지 않는다.
 * `keyLinks` 는 키 → 앱 안 경로다(서버가 만든 출처에서 화면이 모은다). */
function linkKeys(text, keyLinks, keyBase) {
  if (!keyLinks || !keyLinks.size || !text) return text;
  // 티켓 키는 글자 · 숫자 · 하이픈뿐이다. 그 모양만 받아 정규식 메타문자가 들어올 자리를 없앤다.
  const keys = [...keyLinks.keys()].filter((k) => /^[A-Za-z0-9-]{3,40}$/.test(k)).sort((a, b) => b.length - a.length);
  if (!keys.length) return text;
  const re = new RegExp("(" + keys.join("|") + ")", "g");
  const parts = String(text).split(re);
  if (parts.length === 1) return text;
  return parts.map((part, i) => (i % 2 === 1
    ? <Box key={keyBase + "-k" + i} component="a" href={"#" + keyLinks.get(part)}
        sx={{ color: "primary.main", fontWeight: FONT_WEIGHT.semibold, textDecoration: "none", "&:hover": { textDecoration: "underline" } }}>{part}</Box>
    : part));
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면 이전엔 죽은 평문으로만 보였다. 전부
// PlainUrl(복사 버튼)로 낸다. 텍스트 노드만 쓴다(innerHTML 아님, CLAUDE.md §2).
export function linkifyText(text, keyBase, keyLinks) {
  const s = String(text == null ? "" : text);
  const parts = s.split(URL_RE);
  if (parts.length === 1) return linkKeys(s, keyLinks, keyBase);
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
      out.push(linkKeys(carry + part, keyLinks, keyBase + "-t" + i));
      carry = "";
    }
  });
  return out;
}
