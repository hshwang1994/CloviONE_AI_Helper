/* SRCH-04 — 팔레트 빈 질의 상태가 사이드바 메뉴 전부를 복제했다("사이드바가 바로 옆에
 * 열려 있는데 같은 목록을 모달로 한 번 더 보여 주는 셈"). 실제로 이동한 메뉴 경로만
 * 최근 순으로 기억해 뒀다가, 빈 질의일 때 그 목록만 보여준다(VSCode Cmd+P·Slack Cmd+K와
 * 같은 관용). 서버 없이 로컬에서 끝나야 팔레트가 열리자마자 항상 즉시 반응한다.
 */
const KEY = "cv.recentNav.v1";
export const RECENT_LIMIT = 6;

export function recordNavVisit(pathname) {
  if (!pathname) return;
  try {
    const list = readRecentNav().filter((p) => p !== pathname);
    list.unshift(pathname);
    window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, RECENT_LIMIT)));
  } catch {
    // 프라이빗 모드 등으로 localStorage를 못 쓰면 "최근 방문"만 조용히 비어 있다 —
    // 팔레트 자체(메뉴 검색·서버 검색)는 계속 정상 동작해야 한다.
  }
}

export function readRecentNav() {
  try {
    const raw = window.localStorage.getItem(KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.filter((p) => typeof p === "string") : [];
  } catch {
    return [];
  }
}
