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

/* 기본 제품명. **설정값(`ui_branding.product_name`)이 있으면 그쪽이 이긴다** (N5).
 * 마이그레이션 0034 가 "제품명은 코드 상수가 아니라 설정값" 이라고 선언해 놓고, 정작
 * 사용자가 하루 종일 보는 SPA 는 상수였다 — 값을 바꾸면 **로그인 화면만** 바뀌었다.
 * 서버 값이 아직 안 왔을 때(첫 렌더)를 위한 폴백으로만 남긴다. */
export const BRAND = "ClovirAssist";

let brandOverride = "";

/* `/api/me` 의 `branding.product_name` 을 셸이 여기 흘려 넣는다. 전역 한 곳에 두는 이유:
 * 탭 제목은 라우트 변경 시 훅 밖에서도 불리고, 값을 컴포넌트마다 들고 다니면 어딘가 하나는
 * 반드시 옛 이름을 그린다. */
export function setBrand(name) {
  brandOverride = (name || "").trim();
}

export function brand() {
  return brandOverride || BRAND;
}

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
  const b = brand();
  return label ? `${label} | ${b}` : b;
}

/** 경로가 바뀔 때마다 탭 제목을 맞춘다. */
export function useDocumentTitle(pathname) {
  React.useEffect(() => {
    document.title = titleForPath(pathname);
  }, [pathname]);
}
