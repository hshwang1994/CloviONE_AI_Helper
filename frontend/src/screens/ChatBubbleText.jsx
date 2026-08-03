import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import { LINK_REL, LINK_TARGET, tokenizeMessage } from "./chat-text.js";

/* 말풍선 본문 렌더러 — 조각 배열(chat-text.js)을 React 노드로만 그린다.
 *
 * **`dangerouslySetInnerHTML`을 쓰지 않는다.** 본문은 사용자가 친 글자라서, 한 번이라도
 * HTML로 취급하는 순간 저장형 XSS가 된다(누가 채팅에 붙여 넣고 다른 사람이 누른다).
 * 글자는 전부 텍스트 노드로 들어가고, 링크는 `href` 속성 하나만 받는다 — 그 값도
 * chat-text.js의 스킴 화이트리스트(http/https)를 통과한 것뿐이다.
 *
 * 새 창 링크에는 `rel="noopener noreferrer"`가 반드시 붙는다. 없으면 열린 문서가
 * `window.opener`로 이 앱의 탭을 다른 주소로 갈아치울 수 있다(피싱 경로).
 * 그 값은 chat-text.js가 상수로 소유한다 — 여기서 문자열을 다시 적으면 언젠가 빠진다.
 *
 * 멘션은 밑줄이 아니라 **배경 칩**으로 그린다. 링크와 같은 밑줄을 쓰면 누를 수 있는 것처럼
 * 보이는데 실제로는 아무 데도 가지 않는다(누를 곳이 없는 밑줄은 고장으로 읽힌다).
 */

export function ChatBubbleText({ body, names, mine }) {
  const tokens = React.useMemo(() => tokenizeMessage(body, names), [body, names]);
  if (!tokens.length) return null;
  return (
    <>
      {tokens.map((t, i) => {
        if (t.kind === "link") {
          return (
            <Link
              key={i}
              href={t.href}
              target={LINK_TARGET}
              rel={LINK_REL}
              // 내 말풍선은 배경이 primary라 기본 링크색이 묻힌다 — 글자색을 그대로 쓰고
              // 밑줄로 링크임을 알린다(색만으로 정보를 전하지 않는다, WCAG 1.4.1).
              sx={{
                color: mine ? "inherit" : "primary.main",
                textDecorationColor: "currentColor",
                wordBreak: "break-all",
                fontWeight: mine ? 700 : 600,
              }}
            >
              {t.text}
            </Link>
          );
        }
        if (t.kind === "mention") {
          return (
            <Box
              key={i}
              component="span"
              sx={{
                px: 0.5, borderRadius: 1, fontWeight: 700,
                bgcolor: mine ? "rgba(255,255,255,0.22)" : "action.selected",
                color: "inherit",
              }}
            >
              {t.text}
            </Box>
          );
        }
        return <React.Fragment key={i}>{t.text}</React.Fragment>;
      })}
    </>
  );
}
