/* 브라우저 탭 제목 — "<페이지> | ClovirAssist".
 *
 * 기준 파일(preview-standalone.html)이 `document.title = \`${routeTitle(route)} | ClovirAssist\``
 * 로 쓰는 형식 그대로다.
 *
 * 왜 필요한가: 이 앱은 HashRouter SPA 라 서버가 내려주는 HTML 은 한 벌뿐이고, 정적 <title> 도
 * 하나뿐이다. 그래서 어느 화면에 있든 탭 제목이 같았다 — 탭을 여러 개 열어 두면 어느 것이
 * 티켓이고 어느 것이 채팅인지 구분할 수 없다(북마크 이름도 전부 같아진다).
 *
 * 라벨의 출처는 navConfig 다. 여기에 경로→이름 표를 따로 쓰면 메뉴 이름을 바꿀 때마다
 * 두 곳을 고쳐야 하고, 반드시 한쪽을 잊는다.
 */

import React from "react";
import { NAV, USER_NAV, bestNavMatch } from "./navConfig.js";

export const BRAND = "ClovirAssist";

/* 경로 → 메뉴 라벨. navConfig 의 두 나브를 펼쳐 한 표로 만든다. */
const ROUTE_LABELS = (() => {
  const out = {};
  for (const group of [...NAV, ...USER_NAV]) {
    for (const item of group.items) out[item.to] = item.label;
  }
  return out;
})();

/* 나브에 없는 화면들 — 상세 화면이나 나브 항목이 아닌 경로다. */
const EXTRA_LABELS = {
  "/chat": "AI 도우미",
  "/tickets": "티켓",
  "/search": "검색",
  "/notifications": "알림",
  "/team-docs": "문서",
  "/board": "자유게시판",
};

export function titleForPath(pathname) {
  const paths = [...Object.keys(ROUTE_LABELS), ...Object.keys(EXTRA_LABELS)];
  const best = bestNavMatch(pathname || "/", paths);
  const label = best ? ROUTE_LABELS[best] || EXTRA_LABELS[best] : null;
  return label ? `${label} | ${BRAND}` : BRAND;
}

/** 경로가 바뀔 때마다 탭 제목을 맞춘다. */
export function useDocumentTitle(pathname) {
  React.useEffect(() => {
    document.title = titleForPath(pathname);
  }, [pathname]);
}
