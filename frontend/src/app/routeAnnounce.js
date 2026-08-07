import React from "react";
import { labelForPath } from "./documentTitle.js";

/* 화면이 바뀐 사실을 키보드·스크린리더 사용자에게 알린다 (Z14).
 *
 * 왜 필요한가: 이 앱은 SPA 라 메뉴를 눌러도 문서가 새로 로드되지 않는다. 그래서 브라우저가
 * 공짜로 해 주던 두 가지가 조용히 사라진다.
 *   1) **포커스.** 새 문서를 열면 브라우저가 포커스를 문서 맨 앞으로 옮긴다. SPA 에는 그
 *      일이 없어서 포커스가 방금 누른 사이드바 항목에 남는다 — 본문에 닿으려면 메뉴 스무
 *      항목을 Tab 으로 다시 지나야 한다.
 *   2) **낭독.** 화면이 통째로 바뀐 것을 아무도 말해 주지 않는다. 탭 제목은 바뀌지만
 *      스크린리더가 그걸 다시 읽어 주지는 않는다.
 *
 * ── 무엇을, 언제 알리는가 (시끄러우면 그것도 못 쓰는 화면이 된다) ──
 *
 *  - **경로(pathname)가 실제로 바뀔 때만.** 같은 화면 안의 검색어·필터·페이지 번호는
 *    쿼리스트링만 바꾼다. 그때마다 알리면 목록에서 한 글자 칠 때마다 낭독이 끼어들어
 *    검색 자체를 못 한다.
 *  - **첫 진입에는 알리지 않는다.** 그때는 문서 로드 자체가 낭독을 만들고, 탭 제목이 이미
 *    어느 화면인지 말해 준다. 같은 말을 두 번 하면 다음부터는 안 듣는다.
 *  - **화면 이름 한 줄만.** 본문 요약이나 항목 수를 읽지 않는다. 무엇을 더 읽을지는
 *    사용자가 정할 일이고, 포커스가 이미 본문 맨 앞에 가 있다.
 *  - **polite.** 사용자가 스스로 누른 이동이라 급하지 않다 — 읽고 있던 문장을 자르지 않는다.
 *    (assertive 는 오류 토스트처럼 다음 행동이 달라지는 소식에만 쓴다.)
 *  - 포커스는 첫 heading 이 아니라 `<main>` 으로 보낸다. '본문 바로가기' 링크와 **같은
 *    목적지**라 다음 Tab 이 본문 안에서 이어지고, 화면마다 heading 구조가 달라도 흔들리지
 *    않는다.
 *
 * 이름의 출처는 navConfig(documentTitle.js) 다 — 탭 제목과 같은 표를 쓴다. 여기에 경로→이름
 * 표를 따로 두면 메뉴 이름을 바꿀 때 한쪽만 고치게 된다.
 */
export function useRouteAnnounce(pathname) {
  const [message, setMessage] = React.useState("");
  // 첫 렌더의 경로를 '이미 본 것'으로 두면 진입 알림이 저절로 빠진다.
  const seen = React.useRef(pathname);

  React.useEffect(() => {
    if (seen.current === pathname) return;
    seen.current = pathname;
    const main = typeof document === "undefined" ? null : document.getElementById("main-content");
    if (main && typeof main.focus === "function") main.focus();
    const label = labelForPath(pathname);
    setMessage(label ? `${label} 화면으로 이동했습니다.` : "화면을 이동했습니다.");
  }, [pathname]);

  return message;
}
