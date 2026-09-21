import React from "react";
import { useLocation, useNavigate } from "react-router-dom";

/* 같은 화면을 다시 누르면 **새로 들어온 것**이다 — 셸 한 곳의 규칙 (항목 6).
 *
 * ## 무엇이 문제였나
 *
 * 사이드바 항목은 맨 `<Link to="/work-board">` 다. 이미 그 화면에 있을 때 다시 누르면 주소는
 * 질의 없는 `/work-board` 로 바뀌는데 **화면은 다시 마운트되지 않는다** — 본문 경계의 키가
 * `pathname` 이라 같은 경로에서는 그대로 산다. 그래서 「진입 때 한 번」 도는 상태가 되살아나지
 * 않았다: 작업 보드는 팀 자동 선택만 다시 돌고 회차 자동 선택은 무장이 풀린 채라, 두 번 누른
 * 화면이 한 번 누른 화면과 달랐다(회차 없는 전체 판). 스프린트 회의도 같은 모양이었다.
 * 운영 로그에도 그 순서가 그대로 찍혀 있다(2026-09-21).
 *
 * ## 규칙
 *
 * 지금 경로와 **같은 경로**로 가는 셸 이동(사이드바 · 명령 팔레트 · 콘솔 전환 · 상단 로고)은
 * 진입 번호를 하나 올리고 주소를 `replace` 로 바꾼다. 본문 경계의 키가 `경로:진입 번호` 라
 * 화면이 통째로 새로 마운트된다 — 그러면 **두 번 누른 끝 상태가 한 번 누른 끝 상태와 같다.**
 * react-query 캐시는 셸 위에 있으므로 새 마운트가 요청을 두 배로 늘리지 않는다. 예외로 죽은
 * 화면도 메뉴를 다시 누르면 살아난다.
 *
 * 번호를 history state 에 두지 않는 이유: 화면이 자기 주소를 `replace` 로 고쳐 쓰는 순간(작업
 * 보드의 팀 · 회차 자동 선택) 그 state 가 사라져 화면이 한 번 더 마운트된다. 셸의 상태에 둔다.
 *
 * 다른 경로로 가는 이동은 지금과 같다(push). 새 탭 · 수정키 클릭은 브라우저에 그대로 맡긴다. */

const NavEntryContext = React.createContext({ entry: 0, bump: () => {} });

export function NavEntryProvider({ children }) {
  const [entry, setEntry] = React.useState(0);
  const bump = React.useCallback(() => setEntry((n) => n + 1), []);
  const value = React.useMemo(() => ({ entry, bump }), [entry, bump]);
  return <NavEntryContext.Provider value={value}>{children}</NavEntryContext.Provider>;
}

/** 지금 진입 번호 — 본문 경계의 키에 쓴다. */
export function useNavEntry() {
  return React.useContext(NavEntryContext).entry;
}

/* ── 화면 한 벌이 그리는 경로 묶음 ─────────────────────────────────────────────────────────────
 *
 * 목록과 상세를 한 화면에 두고 주소에 고른 것만 싣는 화면이 있다. 사용자 관리(`/users` · `/users/:id`), 조직 관리
 * (`/organizations` · `/org-tree` · `/departments` · `/departments/:id`), 채팅방(`/chat-rooms` · `/chat-rooms/:id`)이다.
 * 라우트는 두 주소에 **같은 element** 를 걸어 인스턴스를 지키도록 만들어져 있다(`AdminRoutes.jsx` PA-RC-0024 ·
 * `UserRoutes.jsx` S1 주석).
 *
 * 🔴 그런데 본문 경계의 키가 경로(pathname)라서 그 의도가 처음부터 한 번도 서지 않았다. 부서 하나를 고를 때마다 화면
 * 전체가 다시 마운트돼 조직도의 펼침 · 스크롤과 초점을 잃었고(조직 관리 재설계 회차가 짚었다, 2026-09-21), 사용자 목록 ·
 * 채팅방 목록도 같았다. 경계의 키는 경로가 아니라 **화면**이어야 한다 — 이 표가 그 묶음이다. 묶음 안에서 주소만 바뀌는
 * 이동은 화면 안의 선택이라 다시 마운트하지 않고, 화면 이동 알림(`routeAnnounce.js`)도 초점을 본문으로 빼앗지 않는다.
 * 묶음에 없는 경로는 지금처럼 경로가 곧 화면이다. */
const SCREEN_FAMILIES = [
  { key: "screen:users", test: /^\/users(\/[^/]+)?$/ },
  { key: "screen:org-console", test: /^\/(organizations|org-tree|departments(\/[^/]+)?)$/ },
  { key: "screen:chat-rooms", test: /^\/chat-rooms(\/[^/]+)?$/ },
];

/** 이 경로를 그리는 화면의 열쇠 — 묶음에 들면 묶음 이름, 아니면 경로 그대로다. 본문 경계의 키가 쓴다. */
export function screenKeyOf(pathname) {
  const path = String(pathname || "");
  const family = SCREEN_FAMILIES.find((f) => f.test.test(path));
  return family ? family.key : path;
}

/** 이동 대상의 경로 부분. 질의 · 해시는 뗀다. */
export function targetPathname(to) {
  if (to && typeof to === "object") return to.pathname || "";
  return String(to || "").split(/[?#]/)[0];
}

/** 이동 대상의 질의 부분(`?` 부터, 없으면 빈 글자). 해시는 뗀다. */
export function targetSearch(to) {
  if (to && typeof to === "object") return to.search || "";
  const s = String(to || "").split("#")[0];
  const i = s.indexOf("?");
  return i < 0 ? "" : s.slice(i);
}

/** 이 이동이 지금 화면에 **다시 들어오는 것**인가 — 경로가 같고, 대상이 자기 질의를 들지 않았거나 지금과 같은 질의다.
 *
 * 메뉴 항목은 화면 자체(`/work-board`)를 가리키므로 같은 경로면 재진입이다. 같은 경로라도 **다른 질의**를 든 이동은
 * 화면 안의 다른 상태로 가는 것이라 평범한 이동(push)이다 — 명령 팔레트의 「모든 결과 보기」가 `/search?q=가` 에서
 * `/search?q=나` 로 가면 뒤로 가기로 앞 검색에 돌아갈 수 있어야 한다. */
export function isReentry(to, loc) {
  if (targetPathname(to) !== loc.pathname) return false;
  const search = targetSearch(to);
  return search === "" || search === "?" || search === loc.search;
}

/** 이 클릭을 브라우저에 맡겨야 하는가 — 새 탭 · 새 창 · 가운데 단추. */
export function isModifiedClick(event) {
  if (!event) return false;
  return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
}

/** 셸 이동 함수. 재진입(`isReentry`)이면 새 진입(`replace` + 진입 번호), 아니면 평범한 이동이다.
 *  돌려주는 값은 새 진입이었는가다(시험과 호출부의 기록용).
 *
 * 🔴 **진입 번호와 주소는 한 번에 그려져야 한다.** 라우터는 주소 갱신을 `startTransition` 으로 감싼다(React Router 7 의
 * HashRouter · MemoryRouter). 번호만 급한 갱신으로 올리면 React 가 그것을 먼저 그려서, 새로 마운트된 화면이 **옛 주소**
 * (`?team=A&sprint=S`)를 보고 한 번 선다. 「진입 때 한 번」 상태는 마운트 때의 주소로 무장하므로(작업 보드의
 * `autoSelectedFor`, 스프린트 회의의 `autoFor`) 그 한 번에 「이미 골랐다」가 박히고, 한 박자 뒤 비워진 주소가 와도 회차를
 * 다시 고르지 않았다. 고친 빌드를 재현 하네스로 잰 결과가 그것이었다(작업 보드 · 스프린트 회의 72건이 `?team=A` 에서 멈춤,
 * 2026-09-21). 번호를 같은 전환 안에서 올리면 번호와 주소가 같은 렌더에 들어가 새 화면은 처음부터 새 주소를 본다. */
export function useEntryNavigate() {
  const navigate = useNavigate();
  const loc = useLocation();
  const { bump } = React.useContext(NavEntryContext);
  return React.useCallback((to, options) => {
    if (isReentry(to, loc)) {
      React.startTransition(() => {
        bump();
        navigate(to, { ...(options || null), replace: true });
      });
      return true;
    }
    navigate(to, options);
    return false;
  }, [navigate, loc, bump]);
}

/** `<Link>` 로 그린 셸 항목의 클릭 처리기. 재진입이면 기본 이동을 막고 새 진입으로 바꾼다.
 *  나머지는 `<Link>` 가 하던 대로 둔다(주소 · 새 탭 열기 · 히스토리가 그대로다). */
export function useEntryLinkClick() {
  const enter = useEntryNavigate();
  const loc = useLocation();
  return React.useCallback((event, to) => {
    if (isModifiedClick(event) || !isReentry(to, loc)) return false;
    event.preventDefault();
    enter(to);
    return true;
  }, [enter, loc]);
}
