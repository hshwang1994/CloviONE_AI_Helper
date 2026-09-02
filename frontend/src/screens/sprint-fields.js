/* 새 스프린트 폼 필드 — `WorkBoard.jsx`(스프린트 추가)와 `Sprint.jsx`(회의 빈 상태의
 * 스프린트 추가, §8.3)가 **같은 폼**을 쓴다. 이 상수를 한쪽 화면 파일에 두고 다른 쪽이
 * 그 파일을 import 하면, 두 화면이 각자 다른 경로로 지연 로드되는 라우트 청크라는 사실이
 * 깨진다 — Vite 가 실제로 "WorkBoard.jsx 가 지연 import 되면서 동시에 Sprint.jsx 에
 * 정적으로도 import 된다" 는 경고를 냈다(정적 경로가 있으면 그 모듈은 더는 독립된 지연
 * 청크가 되지 못하고 정적으로 문 자리에 합쳐진다). 그래서 둘 다 이 작은 공용 파일을 본다.
 *
 * 기간은 ISO 날짜라 서버 스키마(`SprintCreate`)와 같은 모양이다. 프로젝트를 비우면 팀
 * 전체 회차다 — 그 갈래가 있어야 한 프로젝트에 묶이지 않는 주간 회차를 만들 수 있다.
 *
 * 🔴 프로젝트 칸이 폼에 **보인다.** 예전에는 화면의 현재 필터값을 조용히 썼는데, 필터가
 * 「전체」인 채로 만들면 사용자가 모르는 사이 팀 전체 회차가 됐다 — 팀 전체 회차는 조직에
 * 하나만 열 수 있고(`uq_sprints_active`) 후보 목록도 전 프로젝트에서 나오므로 동작이
 * 완전히 다르다. 기본값은 여전히 현재 필터다(`initial`) — 고른 값이 보이는 것과 조용히
 * 쓰이는 것의 차이다. */
export function sprintFields(projectOptions) {
  return [
    { name: "name", label: "이름", required: true, maxLength: 120 },
    {
      name: "project_id", label: "프로젝트", type: "entity",
      options: projectOptions || [], emptyLabel: "팀 전체 회차",
    },
    { name: "starts_on", label: "시작일", type: "date", required: true },
    { name: "ends_on", label: "종료일", type: "date", required: true },
    { name: "goal", label: "목표", type: "textarea", maxLength: 2000 },
  ];
}
