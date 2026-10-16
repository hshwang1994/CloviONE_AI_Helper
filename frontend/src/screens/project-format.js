/* 프로젝트 화면이 쓰는 **말 만들기**. 순수 함수라 DOM 도 API 도 모른다.
 *
 * ## 왜 따로 빼는가
 *
 * 목록 표와 상세가 같은 값을 그린다. 문구를 화면마다 조립하면 "목록에서는 42.9%인데
 * 상세에서는 43%" 같은 어긋남이 생기고, 사용자는 그것을 계산이 틀린 것으로 읽는다.
 * 서버가 진행률과 헬스를 한 함수에 모아 둔 것과 같은 이유다(app/projects/progress.py).
 *
 * ## null 은 0 이 아니다 (이 파일에서 가장 중요한 계약)
 *
 * 진행률과 헬스 점수는 **두 가지 이유로** 비어 있을 수 있고 그 둘은 다른 말이다.
 *
 *   - 프로젝트 행의 `progress_pct` / `health_score` 가 null   = 아직 한 번도 계산 안 함
 *   - `/progress` 응답의 `percent` 가 null                    = 세어 봤는데 분모가 0 (작업이 없음)
 *
 * 둘 다 0% 가 아니다. 0으로 채워 그리면 "작업이 아직 안 붙은 프로젝트"와 "붙었는데 하나도
 * 못 끝낸 프로젝트"가 화면에서 똑같아 보이고, 그럴듯해서 아무도 신고하지 않는다.
 * 그래서 두 상태에 **서로 다른 문구**를 준다.
 */

/* 프로젝트를 만들고 고칠 수 있는 역할. 서버의 `CONSOLE_OPS_ROLES`(app/core/authz.py)와
 * **같은 목록**이다. 여기가 서버보다 넓으면 사용자가 버튼을 눌러 놓고 403 을 받고, 좁으면
 * 권한이 있는 사람에게 버튼이 안 보인다.
 *
 * ⚠️ 화면의 이 목록은 **편의**이지 권한이 아니다. 실제 차단은 서버가 한다 - 여기만 고쳐서
 * 권한이 늘어나지는 않는다. */
export const PROJECT_WRITE_ROLES = ["operator", "admin", "system_admin"];

/* 상태 어휘는 계약(영어 열거값)이고 화면 문구는 한국어다. 계약을 한국어로 바꾸면 화면
 * 코드가 표시용 문자열로 분기하게 되고, 문구를 영어로 두면 읽는 사람이 뜻을 모른다
 * (app/projects/weekly.py::MILESTONE_STATUS_LABELS 가 서버에서 같은 판단을 기록한다). */
export const PROJECT_STATUS_KO = {
  planned: "계획",
  active: "진행",
  on_hold: "보류",
  done: "완료",
};

export const MILESTONE_STATUS_KO = {
  planned: "예정",
  done: "완료",
  missed: "놓침",
};

/** 선택지. 계약 값(영어)을 value 로, 화면 문구(한국어)를 label 로. */
function optionsFrom(table) {
  return Object.keys(table).map((value) => ({ value, label: table[value] }));
}

export const PROJECT_STATUS_OPTIONS = optionsFrom(PROJECT_STATUS_KO);
export const MILESTONE_STATUS_OPTIONS = optionsFrom(MILESTONE_STATUS_KO);

/* 프로젝트 생성·수정 폼의 필드. **한 벌만 둔다.**
 *
 * 만들기와 고치기가 각자 필드 목록을 들고 있으면 한쪽에만 칸이 생기고, 그러면 "만들 때는
 * 넣었는데 고칠 때는 못 고치는 값" 이 생긴다. 서버의 `EDITABLE_FIELDS`
 * (app/projects/service.py) 를 따른다 - 서버가 안 받는 칸을 그리면 저장 버튼이 조용히
 * 아무 일도 안 한다.
 *
 * ## 서버가 받는데 여기 **없는** 세 가지와 그 이유
 *
 *   `dept_id`        선택지를 만들려면 부서 이름이 필요한데 그 경로는 관리자군만 부를 수
 *                    있다(project-queries.js::useDeptNames). 운영자에게는 빈 선택기가 되고,
 *                    빈 선택기는 "고를 것이 없다" 가 아니라 "고장" 으로 읽힌다.
 *   `owner_user_id`  같은 이유(사용자 명부가 필요하다). 게다가 잘못 고르면 그 프로젝트가
 *                    내 범위 밖으로 나갈 수 있고, 나가면 되돌릴 수도 없다.
 *   `code`           서버가 짓는다(D-282). 사용자가 고를 수 없고 나중에 바꿀 수도 없다 —
 *                    코드가 바뀌면 그 프로젝트 티켓 전부의 이름이 바뀌고, 어제 공유한
 *                    링크가 아무 데도 닿지 않는다. 읽기로만 보여 준다.
 */
export const PROJECT_FORM_FIELDS = [
  { name: "name", label: "이름", required: true },
  { name: "status", label: "상태", type: "select", required: true, options: PROJECT_STATUS_OPTIONS },
  { name: "starts_on", label: "시작일", type: "date" },
  { name: "ends_on", label: "종료일", type: "date" },
  { name: "biz_type", label: "사업 유형" },
  { name: "product", label: "제품" },
  { name: "goal", label: "목표", type: "textarea" },
];

export const MILESTONE_FORM_FIELDS = [
  { name: "name", label: "이름", required: true },
  { name: "due_on", label: "기한", type: "date", help: "비워 두면 일정 준수 여부를 판정하지 않습니다." },
  { name: "status", label: "상태", type: "select", required: true, options: MILESTONE_STATUS_OPTIONS },
  /* 필수로 두는 이유: 서버에서 NOT NULL 이다(app/projects/milestones.py::REQUIRED_FIELDS).
     비워 두면 폼이 `null` 을 보내 400 이 나는데, 그 400 을 여기서 미리 막으면 사용자가
     서버 왕복 없이 그 자리에서 안다. */
  { name: "sort_order", label: "정렬 순번", type: "number", required: true, help: "작은 값이 위로 옵니다." },
];

/* 트리에 못 넣은 작업의 이유. 두 경우의 **고칠 곳이 다르다** — 순환은 노션에서 상위 작업을
 * 고쳐야 하고, 깊이 초과는 대개 데이터가 이상하다는 신호다(app/projects/wbs.py). */
export const WBS_UNPLACED_KO = {
  cycle: "상위 작업이 서로를 가리켜 트리에 넣지 못했습니다. 상위 작업을 수정해 주세요.",
  too_deep: "계층이 너무 깊어 트리에 넣지 못했습니다. 계층을 줄여 주세요.",
};

export const NO_PROGRESS_CACHE = "아직 계산하지 않았습니다.";
export const NO_PROGRESS_SAMPLE = "작업이 아직 없습니다.";
export const NO_HEALTH_SCORE = "점수를 낼 수 없습니다.";
export const NO_HEALTH_CACHE = "건강도를 아직 계산하지 않았습니다.";

/* 목록 칸에 들어가는 **짧은 낱말** (계획 3.1).
 *
 * 진행률 열은 6.5rem 이고 `nowrap` 이다. 예전에는 빈 값을 문장(「아직 계산하지 않았습니다」)으로
 * 채워서 글이 옆 칸 위로 넘쳐 그려졌다. 칸에는 다섯 글자 넘는 글을 넣지 않고, 완전한 문장은
 * `title` · `aria-label` 로 준다. 상태는 서버가 준다(`progress.state` · `health.state`) -
 * 화면이 NULL 을 보고 추측하지 않는다(값이 NULL 인 뜻이 둘이기 때문이다). */
export const PROGRESS_STATE_WORD = { pending: "계산 전", no_tasks: "작업 없음" };
export const PROGRESS_STATE_HINT = {
  pending: "아직 계산하지 않았습니다. 곧 계산됩니다.",
  no_tasks: "셀 작업이 없어 진행률을 낼 수 없습니다.",
};
export const HEALTH_STATE_WORD = { pending: "계산 전", unknown: "판정 불가" };
export const HEALTH_STATE_HINT = {
  pending: "아직 계산하지 않았습니다. 곧 계산됩니다.",
  unknown: "판정할 규칙이 없어 점수를 낼 수 없습니다.",
};

function progressStateOf(p) {
  const st = p && p.progress && p.progress.state;
  if (st) return st;
  return p && p.progress_pct != null ? "computed" : "pending";
}

function healthStateOf(p) {
  const st = p && p.health && p.health.state;
  if (st) return st;
  return p && p.health_score != null ? "scored" : "pending";
}

/** 진행률 칸의 글자와 풀이. `{ text, hint, empty }` — empty 면 흐린 색으로 그린다. */
export function progressCell(p) {
  const st = progressStateOf(p);
  if (st === "computed") return { text: percentText(p.progress_pct), hint: null, empty: false };
  return { text: PROGRESS_STATE_WORD[st] || "계산 전", hint: PROGRESS_STATE_HINT[st] || PROGRESS_STATE_HINT.pending, empty: true };
}

/** Health 칸의 글자와 풀이. */
export function healthCell(p) {
  const st = healthStateOf(p);
  if (st === "scored") return { text: p.health_score + "점", hint: null, empty: false };
  return { text: HEALTH_STATE_WORD[st] || "계산 전", hint: HEALTH_STATE_HINT[st] || HEALTH_STATE_HINT.pending, empty: true };
}

/** 차질 문턱. **판정의 정본은 서버다**(`app/projects/health.py::TROUBLE_HEALTH_SCORE`) —
 * 화면은 그 값으로 **색만** 고른다(원을 빨갛게 할지 초록으로 할지). 여기서 판정을 새로
 * 하지 않는다: 요약의 「Health 하위 3건」은 서버가 센 값이고, 화면이 다른 문턱으로 색을
 * 칠하면 3 건이라고 적힌 줄 아래에 빨간 원 다섯 개가 서는 화면이 된다.
 * 두 값이 갈리지 않는 것은 `projects.test.jsx` 가 맞물어 둔다. */
export const TROUBLE_HEALTH_SCORE = 60;

/** 숫자를 화면용 문자열로. 소수점 뒤 0은 떨군다(70.0% 는 사람이 쓰는 말이 아니다). */
function trimmed(value, digits) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return String(Number(n.toFixed(digits)));
}

/** 진행률 문자열. **없으면 null 을 돌려준다** — 여기서 "0%"로 바꾸면 이 파일의 계약이 깨진다. */
export function percentText(value) {
  if (value == null || !Number.isFinite(Number(value))) return null;
  return trimmed(value, 1) + "%";
}

/** 가중 합처럼 소수 둘째 자리까지 오는 값. */
export function weightText(value) {
  if (value == null || !Number.isFinite(Number(value))) return "0";
  return trimmed(value, 2);
}

/* 여기 있던 `progressDiffers` 와 `DIFFERS_NOTE` 는 지웠다(사용자 지시).
 *
 * 포털 계산값과 Notion 값을 나란히 놓고 "두 값이 다릅니다" 라고 경고하던 부품이다. 정본은
 * 포털이고 Notion 은 데이터 소스일 뿐이라, 그 비교는 사용자에게 어느 쪽도 믿지 말라고
 * 말하는 것이었다. 안 쓰게 됐으니 남겨 두지 않는다 - 죽은 코드는 다음 사람에게 "아직 쓰는
 * 규칙" 으로 읽힌다. */

/** 계산식. 숫자를 넣어 적는다 - 식만 적으면 이 프로젝트에서 무엇이 나왔는지 알 수 없다. */
export function formulaText(basis) {
  const b = basis || {};
  return "진행률 = 완료 가중 " + weightText(b.done_weight)
    + " ÷ 전체 가중 " + weightText(b.total_weight) + " × 100";
}

/** 표본 수. 무엇을 몇 건 세고 무엇을 뺐는지 한 줄로. */
export function sampleText(basis) {
  const b = basis || {};
  const n = (v) => (v == null ? 0 : v);
  return "작업 " + n(b.sample_tasks) + "건 중 " + n(b.counted_tasks) + "건을 셌습니다. "
    + "부모 작업 " + n(b.parent_tasks_excluded) + "건, 취소 " + n(b.cancelled_excluded)
    + "건은 뺐습니다. 완료한 작업은 " + n(b.done_tasks) + "건입니다.";
}

/** 가중 방식. 섞였으면 섞였다고 말한다 - 모르면 두 값이 갈렸을 때 어느 쪽이 맞는지 못 고른다. */
export function weightModeText(basis) {
  const b = basis || {};
  if (b.weight_mode === "est_wd") return "예상 WD로 가중해서 셌습니다.";
  if (b.weight_mode === "mixed") {
    return "예상 WD로 가중해서 셌습니다. 예상 WD가 없는 " + (b.est_wd_missing || 0)
      + "건은 1건으로 셌습니다.";
  }
  if (b.weight_mode === "count") return "예상 WD가 적힌 작업이 없어 건수로 셌습니다.";
  return "셀 작업이 없어 가중 방식을 정하지 않았습니다.";
}

/** 기간 한 줄. 한쪽만 있으면 있는 쪽만 말한다(없는 날짜를 오늘로 채우지 않는다). */
export function periodText(startsOn, endsOn) {
  if (startsOn && endsOn) return startsOn + " ~ " + endsOn;
  if (startsOn) return startsOn + " 부터";
  if (endsOn) return endsOn + " 까지";
  return "기간이 정해지지 않았습니다.";
}

/* 부서 이름.
 *
 * 프로젝트 API 는 `dept_id` 만 준다. 이름을 주는 경로는 `/api/admin/departments` 하나뿐이고
 * 그건 관리자군만 부를 수 있다(app/org/router.py). 그래서 **이름을 모르는 사람에게는 아무것도
 * 그리지 않는다** — UUID 를 그려 두면 그건 정보가 아니라 소음이고, "부서 있음" 같은 말은
 * 아무것도 알려 주지 않는다(§불변 6: 없는 것을 있는 척 그리지 않는다).
 */
export function deptLabel(project, names) {
  const p = project || {};
  if (!p.dept_id) return "부서 미지정";
  const table = names || {};
  return table[p.dept_id] || null;
}

/** 마일스톤 상태의 배지 톤. 놓침만 위험이다 — 예정은 정상 상태라 조용해야 한다. */
export const MILESTONE_STATUS_KIND = {
  planned: "neutral",
  done: "ok",
  missed: "danger",
};

/** 두 ISO 날짜 사이 일수. 못 읽으면 null — 지어내지 않는다.
 * 목록의 「n일 지남」과 마일스톤 탭이 같은 산수를 쓴다(다섯 자리 규칙 D-390 의 화면 절반). */
export function daysBetween(from, to) {
  const a = Date.parse(String(from || "") + "T00:00:00Z");
  const b = Date.parse(String(to || "") + "T00:00:00Z");
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return Math.round((b - a) / 86400000);
}
