/* 프로젝트 화면이 쓰는 **말 만들기**. 순수 함수라 DOM 도 API 도 모른다.
 *
 * ## 왜 따로 빼는가
 *
 * 목록 카드와 상세가 같은 값을 그린다. 문구를 화면마다 조립하면 "목록에서는 42.9%인데
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

/* 트리에 못 넣은 작업의 이유. 두 경우의 **고칠 곳이 다르다** — 순환은 노션에서 상위 작업을
 * 고쳐야 하고, 깊이 초과는 대개 데이터가 이상하다는 신호다(app/projects/wbs.py). */
export const WBS_UNPLACED_KO = {
  cycle: "상위 작업이 서로를 가리켜 트리에 넣지 못했습니다. 노션에서 상위 작업을 고쳐 주세요.",
  too_deep: "계층이 너무 깊어 트리에 넣지 못했습니다. 노션에서 계층을 줄여 주세요.",
};

export const NO_PROGRESS_CACHE = "아직 계산하지 않았습니다";
export const NO_PROGRESS_SAMPLE = "작업이 아직 없습니다";
export const NO_NOTION_PROGRESS = "Notion 값이 없습니다";
export const NO_HEALTH_SCORE = "점수를 낼 수 없습니다";
export const NO_HEALTH_CACHE = "Health 를 아직 계산하지 않았습니다";

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

/* 두 진행률이 **실제로** 다른가.
 *
 * 화면이 소수 한 자리까지만 보여 주므로 그 자리까지 같으면 같은 값으로 본다. 42.94 와
 * 42.95 를 "다릅니다"라고 말하면서 화면에는 둘 다 42.9% 로 그리면, 그 안내가 오히려
 * 화면을 못 믿게 만든다.
 *
 * 한쪽이 없으면 **다르다고 말하지 않는다.** 그건 두 주장이 갈린 것이 아니라 한쪽이 아직
 * 말을 안 한 것이고, 그 사실은 값 자리의 문구가 이미 말하고 있다.
 */
export function progressDiffers(appPercent, notionPercent) {
  if (appPercent == null || notionPercent == null) return false;
  const a = Number(appPercent);
  const b = Number(notionPercent);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
  return Math.round(a * 10) !== Math.round(b * 10);
}

/* 두 값이 다를 때의 설명. **왜 다른지**까지 말하지 않으면 사용자는 둘 중 하나를 거짓말로
 * 받아들이고, 그 다음부터 둘 다 안 본다(app/projects/progress.py 모듈 docstring). */
export const DIFFERS_NOTE =
  "두 값이 다릅니다. Notion 쪽 진행률은 취소한 작업을 완료로 세고, 하위 작업을 상위 작업과 "
  + "두 번 셉니다. 포털은 취소를 분모에서 빼고 리프 작업만 셉니다.";

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
    + "건은 뺐습니다. 완료 " + n(b.done_tasks) + "건.";
}

/** 가중 방식. 섞였으면 섞였다고 말한다 - 모르면 두 값이 갈렸을 때 어느 쪽이 맞는지 못 고른다. */
export function weightModeText(basis) {
  const b = basis || {};
  if (b.weight_mode === "est_wd") return "예상 WD 로 가중해서 셌습니다.";
  if (b.weight_mode === "mixed") {
    return "예상 WD 로 가중해서 셌습니다. 예상 WD 가 없는 " + (b.est_wd_missing || 0)
      + "건은 1건으로 셌습니다.";
  }
  if (b.weight_mode === "count") return "예상 WD 가 적힌 작업이 없어 건수로 셌습니다.";
  return "셀 작업이 없어 가중 방식을 정하지 않았습니다.";
}

/** 기간 한 줄. 한쪽만 있으면 있는 쪽만 말한다(없는 날짜를 오늘로 채우지 않는다). */
export function periodText(startsOn, endsOn) {
  if (startsOn && endsOn) return startsOn + " ~ " + endsOn;
  if (startsOn) return startsOn + " 부터";
  if (endsOn) return endsOn + " 까지";
  return "기간이 정해지지 않았습니다";
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
