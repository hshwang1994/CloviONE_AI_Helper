import React from "react";
import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import { useToast } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { copyText, plainSegments, safeSourceRoute } from "../chat-helpers.js";

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

/* 앱 안 링크(티켓 키 · 답 안의 출처 링크)의 모양 — 같은 자리에 서는 두 링크가 같아 보여야 한다. */
const APP_LINK_SX = {
  color: "primary.main", fontWeight: FONT_WEIGHT.semibold, textDecoration: "none", "&:hover": { textDecoration: "underline" },
};

/* 조각(`chat-helpers.js::parseInline` · `plainSegments`) → React 노드. 글자는 텍스트 노드로만 들어간다(innerHTML 아님,
 * CLAUDE.md §2). 굵게는 `<strong>`, 출처 링크와 티켓 키는 같은 창의 해시 링크, 바깥 주소는 복사 단추다. 링크 경로는 여기서도
 * 한 번 더 본다 — 앱 안 출처 모양이 아니면 앵커를 만들지 않고 글자로 둔다. */
export function renderInline(segments, keyBase) {
  const list = Array.isArray(segments) ? segments : [];
  return list.map((seg, i) => {
    const key = keyBase + "-" + i;
    if (!seg) return null;
    if (seg.t === "text") return <React.Fragment key={key}>{seg.text}</React.Fragment>;
    if (seg.t === "bold") {
      return <Box key={key} component="strong" sx={{ fontWeight: FONT_WEIGHT.bold }}>{renderInline(seg.children, key)}</Box>;
    }
    if (seg.t === "link" || seg.t === "key") {
      const label = seg.t === "link" ? seg.label : seg.key;
      const route = safeSourceRoute(seg.route);
      if (!route) return <React.Fragment key={key}>{label}</React.Fragment>;
      return <Box key={key} component="a" href={"#" + route} sx={APP_LINK_SX}>{label}</Box>;
    }
    if (seg.t === "url") return <PlainUrl key={key} url={seg.url} />;
    return null;
  });
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면 이전엔 죽은 평문으로만 보였다. 전부
// PlainUrl(복사 버튼)로 낸다. 글 속 티켓 키는 **그 답의 출처에 있는 키만** 앱 안 링크다(D-538) —
// `keyLinks` 는 키 → 앱 안 경로다(서버가 만든 출처에서 화면이 모은다). 쪼개기는 `plainSegments` 가 하고(주소 꼬리 다듬기는
// 팀 채팅 말풍선과 같은 `trimUrlTail` — 잘려 나간 꼬리는 버리지 않고 뒤 글에 되돌려 붙인다), 굵게와 출처 링크는 여기서
// 보지 않는다(그건 답 말풍선의 `RichText` 가 `parseInline` 으로 한다). 문서 · 티켓 본문(`ui/DocBody.jsx`)도 이 함수를 쓴다.
export function linkifyText(text, keyBase, keyLinks) {
  const segments = plainSegments(text, { keyLinks });
  if (!segments.length) return "";
  if (segments.length === 1 && segments[0].t === "text") return segments[0].text;
  return renderInline(segments, keyBase);
}
