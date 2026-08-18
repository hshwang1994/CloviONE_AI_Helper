/* 브라우저 탭 제목 — "<페이지> | ClovirAssist".
 *
 * 문서 제목 규약은 `${routeTitle(route)} | ClovirAssist`
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
// setBrand()가 오면 여기 등록된 훅들에게 "다시 그려라"를 알린다. `/api/me`는 비동기라 AppShell은
// 먼저 기본 경로(보통 /me)로 마운트되고, 브랜드는 그 뒤에 도착한다. 사이드바 로고는 auth.data가
// 바뀌며 컴포넌트가 다시 렌더될 때 `brand()`를 새로 읽어 저절로 맞는데, 탭 제목은 useEffect가
// pathname 하나에만 걸려 있어서 — 로그인 뒤 같은 화면에 머무르는 흔한 경우 — 브랜드가 와도 그
// 사실을 몰라 기본 브랜드에 갇혔다(로고와 탭이 서로 다른 이름을 말하는 상태). 구독자에게 알려
// 값이 바뀐 다음 렌더에서 tabTitle의 effect가 실제로 다시 실행되게 한다.
const brandListeners = new Set();

/* `/api/me` 의 `branding.product_name` 을 셸이 여기 흘려 넣는다. 전역 한 곳에 두는 이유:
 * 탭 제목은 라우트 변경 시 훅 밖에서도 불리고, 값을 컴포넌트마다 들고 다니면 어딘가 하나는
 * 반드시 옛 이름을 그린다. */
export function setBrand(name) {
  const next = (name || "").trim();
  if (next === brandOverride) return;   // 값이 그대로면 구독자를 깨울 이유가 없다
  brandOverride = next;
  brandListeners.forEach((fn) => fn());
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

/** 경로 → 화면 이름(제품명 없이). 아는 화면이 아니면 "".
 *
 * 탭 제목과 **같은 표**를 쓰기 위해 따로 뺐다. 화면 전환 낭독(routeAnnounce.js)도 이 이름을
 * 읽는데, 거기에 경로→이름 표를 한 벌 더 두면 메뉴 이름을 바꿀 때 한쪽만 고치게 된다. */
export function labelForPath(pathname) {
  const paths = [...Object.keys(ROUTE_LABELS), ...Object.keys(EXTRA_LABELS)];
  const best = bestNavMatch(pathname || "/", paths);
  return (best ? ROUTE_LABELS[best] || EXTRA_LABELS[best] : "") || "";
}

// VIS-133: 나브 라벨만으로는 상세 화면 탭이 전부 같은 이름이다("티켓 | ClovirAssist"가
// 티켓 100장 전부의 탭 제목) — 여러 탭을 열어 두면 구분이 안 된다. 화면이 자기 데이터를
// 읽은 뒤 더 구체적인 제목(실제 티켓/문서/글 제목)을 여기 등록하면 탭에 그게 대신 쓰인다.
// setBrand()와 같은 모듈 전역 + 구독자 패턴이다 — 이유도 같다: pathname 이 그대로면
// useDocumentTitle 의 effect 가 다시 안 돈다.
let itemTitle = "";
let itemTitlePath = null;
const itemTitleListeners = new Set();

/** pathname 이 지금 화면과 안 맞으면 조용히 무시한다 — 사용자가 이미 다른 화면으로 옮긴
 * 뒤에 이전 화면의 지연 응답(예: 느린 API)이 도착해도 새 화면의 제목을 덮지 않는다. */
export function setItemTitle(pathname, text) {
  const next = (text || "").trim();
  if (itemTitlePath === pathname && itemTitle === next) return;
  itemTitlePath = pathname;
  itemTitle = next;
  itemTitleListeners.forEach((fn) => fn());
}

function itemTitleFor(pathname) {
  return itemTitlePath === pathname ? itemTitle : "";
}

export function titleForPath(pathname) {
  const specific = itemTitleFor(pathname);
  const label = specific || labelForPath(pathname);
  const b = brand();
  return label ? `${label} | ${b}` : b;
}

/** 경로가 바뀔 때마다, 그리고 브랜드가 늦게 도착했을 때도 탭 제목을 맞춘다.
 *
 * `brandTick` 은 값 자체가 아니라 "브랜드가 바뀌었다"는 신호일 뿐이다 — setBrand() 는 React
 * 상태가 아닌 모듈 전역 변수를 바꾸므로, 이 훅이 그 변화를 스스로 구독해 다시 렌더되지
 * 않으면 아래 effect 는 pathname 이 그대로인 한 절대 다시 돌지 않는다. */
export function useDocumentTitle(pathname) {
  const [brandTick, setBrandTick] = React.useState(0);
  React.useEffect(() => {
    const onChange = () => setBrandTick((n) => n + 1);
    brandListeners.add(onChange);
    itemTitleListeners.add(onChange);
    return () => { brandListeners.delete(onChange); itemTitleListeners.delete(onChange); };
  }, []);
  React.useEffect(() => {
    document.title = titleForPath(pathname);
    // brandTick 은 값을 읽지 않고 재실행 신호로만 쓴다 — 그래서 결과에 안 쓰여도 deps 에 있어야 한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, brandTick]);
}
