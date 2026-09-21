import { declaredRowName } from "../../ui/rowName.js";

// 상세 드로어 필드 병합 — columns와 detailFields를 그냥 이어붙이면 같은 key가 두 화면(예: 러너의
// base_url/config_version)에 모두 정의된 경우 드로어에 같은 값이 두 번 보인다. key가 겹치면
// 먼저 오는(columns) 항목만 남기고 detailFields의 중복 항목은 버린다(레지스트리 작성자가 실수로
// 같은 필드를 두 번 넣어도 드로어가 조용히 두 배로 늘어나지 않게).
export function mergeDetailFields(config, columns) {
  const seen = new Set();
  const merged = [];
  [...(columns || config.columns || []), ...(config.detailFields || [])].forEach((c) => {
    if (c.key != null) {
      if (seen.has(c.key)) return;
      seen.add(c.key);
    }
    merged.push(c);
  });
  return merged;
}

/* ── 상세의 빈 값은 한 줄이다 (D-501) ─────────────────────────────────────────
 *
 * 작업 큐의 상세는 열여덟 줄 중 열 줄이 「-」였다(대기 중인 작업이라 시작 · 종료 · 소요 시간 · 오류가 아직 없다).
 * 값이 없는 줄이 값이 있는 줄 사이에 끼어 있으면 눈은 「-」 열 개를 다 지나야 읽을 것을 찾는다. 끝남 · 0 · 없음은
 * 한 줄이고, 값이 있는 것만 펼친다 — 빈 줄들은 마지막 한 줄 「값 없음」이 이름만 나열한다(무엇이 비었는지는 남는다).
 *
 * 무엇이 「없음」인가: 그린 값이 비었거나 `-` 이면 없음이다(`render` 가 없다고 말하는 관례가 `-` 다). 그린 값이
 * 그림(`DateCell` · `Badge`)이라 글자로 판단할 수 없는 필드는 스스로 `isEmpty(row)` 를 든다(`columnHelpers.jsx`). */
export const EMPTY_DETAIL_LABEL = "값 없음";

/** 상세 한 줄에 그릴 값 — 표 칸과 같은 규칙(`render` 가 이기고, 없으면 원시 값 · 빈 값은 `-`). */
export function detailValueOf(field, row) {
  if (field.render) return field.render(row);
  const v = row[field.key];
  return v == null || v === "" ? "-" : String(v);
}

/** 이 줄이 「값 없음」으로 접히는가. */
export function isEmptyDetailValue(field, row, value) {
  if (typeof field.isEmpty === "function") return !!field.isEmpty(row);
  return value == null || value === false || value === "" || value === "-";
}

/** 필드를 값이 있는 줄(그린 값과 함께)과 빈 줄로 가른다. 순서는 그대로다. */
export function partitionDetailFields(fields, row) {
  const filled = [];
  const empty = [];
  for (const field of fields || []) {
    const value = detailValueOf(field, row);
    if (isEmptyDetailValue(field, row, value)) empty.push(field);
    else filled.push({ field, value });
  }
  return { filled, empty };
}

export function detailTitle(row, columns) {
  const cols = columns || [];
  // SEM-01의 rowOpenLabel(kit.jsx)과 같은 기준을 쓴다 — 열 정의가 rowName을 선언했으면(등록
  // 화면 11개가 이미 그렇다) 상세 드로어 제목도 "상세 보기" 버튼과 같은 값을 말해야 한다.
  // 예전엔 이 함수가 declaredRowName을 몰라 columns[0]만 봤다 — 그 열이 render()를 쓰는
  // 화면(예: jobs의 생성 시각, audit-anomalies의 중요도 배지)에서는 제목이 원시 타임스탬프나
  // "high"/"medium"/"low" 같은 raw enum 값으로 샜다(행 버튼은 SEM-01로 이미 고쳐졌는데 같은
  // 화면의 드로어 제목만 고쳐지지 않은 것 — 같은 Root Cause의 또 다른 소비처).
  const declared = declaredRowName(cols, row);
  if (declared) return declared;
  const first = cols[0];
  // 열의 render(예: 날짜 KST 포맷)를 존중한다 — 원시 ISO 타임스탬프가 제목으로 새어 나오지 않게.
  // 단 render가 문자열/숫자가 아닌(배지 등 JSX) 값을 주면 원시 값으로 되돌린다(제목은 문자열이어야 함).
  if (first && first.render) {
    const rendered = first.render(row);
    if (typeof rendered === "string" || typeof rendered === "number") return String(rendered);
  }
  // columnsFrom 화면은 응답이 오기 전 한 프레임 동안 열이 비어 있을 수 있다 — 그때 first가
  // undefined면 여기서 크래시가 난다(드로어가 열려 있는 상태에서만 드러나는 결함).
  if (!first) return String(row.id || "상세");
  return String(row[first.key] != null ? row[first.key] : (row.id || "상세"));
}
