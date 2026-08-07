/* 운영 화면(진단/유지보수) — 실제 구현은 ./ops/ 아래로 나뉘어 있다(파일당 800줄 상한 + 응집도).
 * 이 파일은 기존 경로("./Ops.jsx")를 그대로 쓰는 라우트(AdminRoutes.jsx)와 테스트
 * (ops-*.test.jsx)를 깨지 않기 위한 재노출 지점이다.
 *
 * 분리 지도:
 *   ops/opsHelpers.js          판정 임계값·순수 함수(errorBuckets/healthVerdict 등, JSX 없음)
 *   ops/LogList.jsx             이력 목록 한 줄(최근 작업 오류·최근 주요 변경 공용)
 *   ops/ServiceStatusPanel.jsx  서비스 상태 카드(시스템 리소스 + 서비스 상태 + 재시작 안내)
 *   ops/JobQueuePanel.jsx       잡 큐 패널(작업 지표 + 최근 작업 오류)
 *   ops/DiagnosticActions.jsx   진단 액션(수집/복사/다운로드 버튼)
 *   ops/Diagnostics.jsx         진단 화면 본체(오케스트레이터)
 *   ops/Maintenance.jsx         유지보수 화면 본체 */
export { Diagnostics } from "./ops/Diagnostics.jsx";
export { Maintenance } from "./ops/Maintenance.jsx";
export { errorBuckets } from "./ops/opsHelpers.js";
