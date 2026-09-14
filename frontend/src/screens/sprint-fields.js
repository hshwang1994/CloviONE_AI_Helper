/* 새 회차 폼 필드 — `WorkBoard.jsx`(회차 추가)와 `Sprint.jsx`(회의 빈 상태의 회차 추가,
 * §8.3)가 **같은 폼**을 쓴다. 이 상수를 한쪽 화면 파일에 두고 다른 쪽이 그 파일을 import
 * 하면, 두 화면이 각자 다른 경로로 지연 로드되는 라우트 청크라는 사실이 깨진다 — Vite 가
 * 실제로 "WorkBoard.jsx 가 지연 import 되면서 동시에 Sprint.jsx 에 정적으로도 import 된다"
 * 는 경고를 냈다. 그래서 둘 다 이 작은 공용 파일을 본다.
 *
 * 기간은 ISO 날짜라 서버 스키마(`SprintCreate`)와 같은 모양이다.
 *
 * 🔴 **프로젝트 칸이 없다** (D-482). 회차는 팀의 것이고 프로젝트는 티켓의 필터다 — 폼에
 * 프로젝트를 두면 「프로젝트별 회차」라는 옛 모형이 화면에 다시 산다. 어느 팀의 회차를
 * 만드는지는 이름 칸 아래 한 줄이 말한다(`teamLabel`). 팀 자체는 화면의 팀 선택기가 이미
 * 골라 둔 값이고 서버가 `department_id` 로 다시 검증한다. */
export function sprintFields({ teamLabel } = {}) {
  return [
    {
      name: "name", label: "이름", required: true, maxLength: 120,
      help: teamLabel ? `${teamLabel}의 회차를 추가합니다.` : undefined,
    },
    { name: "starts_on", label: "시작일", type: "date", required: true },
    { name: "ends_on", label: "종료일", type: "date", required: true },
    { name: "goal", label: "목표", type: "textarea", maxLength: 2000 },
  ];
}

/** 팀 후보 한 줄의 표시 이름 — 경로가 있으면 경로(「A본부 › A-1팀」), 없으면 이름. */
export function teamLabelOf(option) {
  if (!option) return "";
  const path = Array.isArray(option.path) ? option.path.map((n) => n.name).filter(Boolean) : [];
  return path.length ? path.join(" › ") : (option.name || "");
}
