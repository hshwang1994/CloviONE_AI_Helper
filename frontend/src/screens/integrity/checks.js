import { roleLabel } from "../../lib/roles.js";
import { SPRINT_STATE_LABEL } from "../SprintLifecycle.jsx";

/* 조직 정합성 — 검사의 종류별 열과 일괄 작업 어휘 (계획 3.2, D-508).
 *
 * 검사는 서버가 정한다(`app/integrity/service.py::CHECKS`). 화면은 검사의 **행 종류**(`kind`)로 열을
 * 고르고, 검사가 허용한 작업(`fixes`)으로 단추를 고른다. 검사 이름을 화면에 적지 않는다 - 서버가
 * 검사를 더해도 화면을 안 고쳐도 되게.
 *
 * 열의 정렬은 열 타입이 정한다(D-506): 이름과 원인은 왼쪽, 상태와 번호는 가운데, 건수는 오른쪽이다. */

export const KIND_UNIT = { user: "명", ticket: "건", project: "건", space: "건", sprint: "건" };

export const SEARCH_PLACEHOLDER = {
  user: "이름, 이메일 검색",
  ticket: "제목, 번호 검색",
  project: "이름, 코드 검색",
  space: "이름 검색",
  sprint: "이름 검색",
};

/* 작업마다 고를 대상. `membership` 은 부서 또는 조직 전체, `department` 는 활성 부서 하나,
   `project` 는 프로젝트 하나, `null` 은 고를 것이 없다. 서버의 `_validate_target` 과 같은 표다. */
export const FIX_TARGET = {
  membership: "membership",
  space_owner: "membership",
  project_department: "department",
  sprint_team: "department",
  ticket_project: "project",
  remove_from_sprint: null,
};

export const FIX_PICKER_LABEL = {
  membership: "지정할 소속",
  space_owner: "지정할 소속",
  project_department: "옮길 부서",
  sprint_team: "지정할 팀",
  ticket_project: "옮길 프로젝트",
};

/* 부서 대신 조직 전체를 고르는 선택지의 이름. 사람은 「조직 직속」, 공간은 「조직 공통」이다
   (`app/core/ownership.py` 의 두 낱말 그대로). */
export const ORG_CHOICE_LABEL = {
  membership: "조직 직속(부서 없음)",
  space_owner: "조직 공통",
};

export const ORG_CHOICE = "__org__";

/** 적용 단추의 문구. 고른 수와 단위를 그대로 말한다. */
export function applyLabel(fix, count, unit) {
  if (fix === "remove_from_sprint") return `선택한 ${count}${unit}을 회차에서 빼기`;
  return `선택한 ${count}${unit}에 적용`;
}

/** 서버로 보낼 본문. 대상 값은 작업마다 하나만 싣는다(나머지는 보내지 않는다). */
export function fixBody(fix, target, ids) {
  const body = { fix, ids };
  const kind = FIX_TARGET[fix];
  if (kind === "membership") {
    if (target === ORG_CHOICE) body.organization_direct = true;
    else body.department_id = target;
  } else if (kind === "department") {
    body.department_id = target;
  } else if (kind === "project") {
    body.project_id = target;
  }
  return body;
}

const REASON = { key: "reason", label: "원인", type: "text", overflow: "word" };

const COLUMNS = {
  user: [
    { key: "display_name", label: "이름", type: "title", rowName: (r) => r.display_name || r.id },
    { key: "email", label: "이메일", type: "identifier" },
    { key: "role", label: "역할", type: "enum", value: (r) => roleLabel(r.role) },
    REASON,
  ],
  ticket: [
    { key: "key", label: "번호", type: "code", value: (r) => r.key || "-" },
    { key: "title", label: "제목", type: "title", rowName: (r) => r.title || r.id },
    { key: "status", label: "상태", type: "status", value: (r) => r.status || "-" },
    REASON,
  ],
  project: [
    { key: "name", label: "이름", type: "title", rowName: (r) => r.name || r.id },
    { key: "code", label: "코드", type: "code", value: (r) => r.code || "-" },
    REASON,
  ],
  space: [
    { key: "name", label: "이름", type: "title", rowName: (r) => r.name || r.id },
    { key: "doc_count", label: "문서", type: "count" },
    REASON,
  ],
  sprint: [
    { key: "name", label: "이름", type: "title", rowName: (r) => r.name || r.id },
    { key: "state", label: "상태", type: "enum", value: (r) => SPRINT_STATE_LABEL[r.state] || r.state || "-" },
    { key: "starts_on", label: "시작", type: "date" },
    { key: "ends_on", label: "종료", type: "date" },
    REASON,
  ],
};

/** 행 종류별 열. 모르는 종류는 제목과 원인만 그린다 - 서버가 새 종류를 먼저 내보내도 표가 선다. */
export function columnsFor(kind) {
  return COLUMNS[kind] || [
    { key: "title", label: "대상", type: "title", rowName: (r) => r.title || r.id },
    REASON,
  ];
}
