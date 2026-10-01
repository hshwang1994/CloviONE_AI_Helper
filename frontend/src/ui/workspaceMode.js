import React from "react";

/* 지금 이 판 격자가 채움 모드인가 (F5 · D-531).
 *
 *   null   작업 공간 밖 — 부품은 호출부가 고른 대로 그린다
 *   true   채움 — 판 몸이 남은 높이를 받고, 그 안의 표(`DataTable fill`)가 직접 굴린다
 *   false  흐름(좁거나 낮은 창) — 판이 문서와 함께 흐르므로 표도 흐른다
 *
 * `ui/Workspace.jsx` 가 값을 내고, `ui/kit.jsx::DataTable` 이 읽는다. 둘 사이의 가져오기 고리(Workspace → kit)를 만들지 않으려고
 * 따로 둔다(`scrollRoot.js` 와 같은 이유). 흐름에서 표 상자를 스크롤 창으로 두면 높이 제한이 없어 굴러가지 않고, 그 안의 더 받기
 * 감시점은 언제나 「보인다」고 판정되어 끝까지 받는다 — 그래서 판정은 화면마다가 아니라 표 한 곳에서 한다. */
export const WorkspaceModeContext = React.createContext(null);

export function useWorkspaceMode() {
  return React.useContext(WorkspaceModeContext);
}
