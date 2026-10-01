/* 조직 관리 — 주소 넷(`/organizations` · `/org-tree` · `/departments` · `/departments/:id`)이 여는 화면.
 *
 * 본문은 관리 작업 공간 `screens/org/OrgWorkspace.jsx` 다(O1 · D-533). 이 파일은 라우트 표(`app/AdminRoutes.jsx`)와 시험이 부르는
 * 옛 이름을 그대로 둔다 — 주소 계약은 바뀌지 않았다. */
export { OrgWorkspace as OrgConsole, OrgWorkspace as default } from "./org/OrgWorkspace.jsx";
