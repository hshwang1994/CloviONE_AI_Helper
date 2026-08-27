/* 새 스프린트 폼 필드 — `WorkBoard.jsx`(스프린트 추가)와 `Sprint.jsx`(회의 빈 상태의
 * 스프린트 추가, §8.3)가 **같은 폼**을 쓴다. 이 상수를 한쪽 화면 파일에 두고 다른 쪽이
 * 그 파일을 import 하면, 두 화면이 각자 다른 경로로 지연 로드되는 라우트 청크라는 사실이
 * 깨진다 — Vite 가 실제로 "WorkBoard.jsx 가 지연 import 되면서 동시에 Sprint.jsx 에
 * 정적으로도 import 된다" 는 경고를 냈다(정적 경로가 있으면 그 모듈은 더는 독립된 지연
 * 청크가 되지 못하고 정적으로 문 자리에 합쳐진다). 그래서 둘 다 이 작은 공용 파일을 본다.
 *
 * 기간은 ISO 날짜라 서버 스키마(`SprintCreate`)와 같은 모양이다. 프로젝트를 비우면 팀
 * 전체 회차다 — 그 갈래가 있어야 한 프로젝트에 묶이지 않는 주간 회차를 만들 수 있다. */
export const SPRINT_FIELDS = [
  { name: "name", label: "이름", required: true, maxLength: 120 },
  { name: "starts_on", label: "시작일", type: "date", required: true },
  { name: "ends_on", label: "종료일", type: "date", required: true },
  { name: "goal", label: "목표", type: "textarea", maxLength: 2000 },
];
