import React from "react";

/* 스크롤 창 문맥 (F5 · D-531) — 이 아래의 목록이 **어느 상자 안에서** 굴러가는가.
 *
 * 앱 틀은 보통 창(window)이 굴러간다. 작업 공간의 판 몸(`Workspace.jsx::WorkspacePane`)은 자기 안에서만 굴러가는 상자라, 그 안의
 * 무한 받기 감시점이 창을 기준으로 「보인다」고 판정하면 판을 열자마자 끝까지 받는다(모달 안 목록이 겪은 것과 같은 결함 —
 * `listFooter.js::scrollParent`). 판 몸이 `"auto"` 를 깔면 감시점은 자기 위를 걸어 올라가 실제로 굴리는 조상을 찾는다.
 *
 * 이 파일은 아무것도 import 하지 않는다 — `listFooter.js` · `kit.jsx` · `Workspace.jsx` 가 함께 쓰는데, 문맥이 그중 한 파일에 있으면
 * 서로를 부르는 고리가 생긴다(`kit.jsx` → `listFooter.js` → `Workspace.jsx` → `kit.jsx`).
 *
 *   null    창이 굴러간다(기본)
 *   "auto"  실제로 굴리는 조상을 감시점이 스스로 찾는다
 */
export const ScrollRootContext = React.createContext(null);

/** 지금 자리의 스크롤 창 문맥. */
export function useScrollRoot() {
  return React.useContext(ScrollRootContext);
}
