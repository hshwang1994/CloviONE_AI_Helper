/* 목록 상태 일곱 갈래 (F4 · D-530) — 「검색 결과가 없습니다」 하나로 뭉치지 않는다.
 *
 * 예전 목록 화면은 조건이 하나라도 걸려 있으면 0건을 「검색 결과가 없습니다」로, 실패는 거의 다 같은 오류 판으로 그렸다.
 * 그래서 권한이 없는 사람, 기능이 꺼진 설치, 서버에 닿지 못한 순간, 정말 자료가 없는 새 설치가 같은 얼굴로 보였다 — 사용자는
 * 무엇을 하면 되는지(권한을 받는다 · 설정을 켠다 · 잠시 뒤 다시 한다 · 조건을 지운다 · 하나를 만든다)를 알 수 없었다.
 *
 * 판정 순서가 곧 우선순위다:
 *
 *   loading         첫 요청이 진행 중이다(받아 둔 행이 없다)
 *   forbidden       401 · 403 — 다시 시도로 풀리지 않는다
 *   disabled        서버가 「꺼짐」 사유 코드(`feature_disabled` · `ai_unavailable` · `module_disabled`)로 거절했다
 *   unreachable     네트워크 오류 · 시간 초과 · 502 · 503 · 504 — 잠시 뒤 다시 시도하면 풀릴 수 있다
 *   error           그 밖의 5xx · 예상하지 못한 응답 — 다시 시도 + 문의 번호
 *   filtered-empty  조건이 있는데 0건 — 조건을 지우면 보일 수 있다(표 머리 아래 한 줄 띠)
 *   empty           조건 없이 0건 — 자료가 아직 없다(만드는 동작이 있으면 그 단추)
 *   ready           보일 행이 있다
 */

export const LIST_STATES = Object.freeze([
  "loading", "forbidden", "disabled", "unreachable", "error", "filtered-empty", "empty", "ready",
]);

/* 서버가 「기능이 꺼져 있다」는 뜻으로 보내는 사유 코드. 기능을 켜면 풀리는 거절이라 오류 판이 아니라 그 사실을 말한다.
   `feature_disabled` 는 기능 깃발 문(`app/core/errors.py::FeatureDisabledError`, 상태는 404 그대로)이 보낸다. */
export const DISABLED_CODES = Object.freeze(["feature_disabled", "ai_unavailable", "module_disabled"]);
const UNREACHABLE_STATUS = new Set([502, 503, 504]);

/* 갈래마다 화면이 쓰는 기본 문장 — 제목은 무엇이 일어났는가, 도움말은 무엇을 하면 되는가다. 둘 다 완전한 문장이다.
   서버가 사유 문장을 주면 기능 꺼짐의 제목은 그 문장이 이긴다(「문서 기능이 비활성화되어 있습니다.」처럼 어느 기능인지 말한다). */
export const LIST_STATE_COPY = Object.freeze({
  forbidden: { title: "이 목록을 볼 권한이 없습니다.", help: "권한이 필요하면 관리자에게 요청하세요." },
  disabled: { title: "이 기능이 꺼져 있습니다.", help: "관리자가 기능을 켜면 목록을 볼 수 있습니다." },
  unreachable: { title: "서버에 연결하지 못했습니다.", help: "잠시 뒤 다시 시도하세요." },
  error: { title: "목록을 불러오지 못했습니다.", help: "잠시 뒤 다시 시도하세요." },
  "filtered-empty": { title: "검색 조건에 맞는 항목이 없습니다.", help: "" },
  empty: { title: "등록된 항목이 없습니다.", help: "" },
});

/* 받침에 따른 주격 조사 — 「티켓이」 · 「게시글이」 · 「승인 요청이」 · 「감사 기록이」(`lib/format.js::hasFinalConsonant` 와 같은 규칙,
   이 파일은 의존 없이 쓰이도록 셈을 따로 둔다). */
function subjectParticle(word) {
  const last = String(word || "").trim().slice(-1);
  const code = last.charCodeAt(0) - 0xac00;
  if (code < 0 || code > 11171) return "이(가)";
  return code % 28 === 0 ? "가" : "이";
}

/** 조건 0건 문장 — 「검색 조건에 맞는 {대상}이 없습니다.」(D-587). 대상이 없으면 기본 문장이다. */
export function filteredEmptyTitle(noun) {
  return noun ? `검색 조건에 맞는 ${noun}${subjectParticle(noun)} 없습니다.` : LIST_STATE_COPY["filtered-empty"].title;
}

/** 조건 없는 0건 문장 — 「등록된 {대상}이 없습니다.」(D-587). */
export function emptyTitle(noun) {
  return noun ? `등록된 ${noun}${subjectParticle(noun)} 없습니다.` : LIST_STATE_COPY.empty.title;
}

/** 오류 봉투의 사유 코드(`body.error.code`). 없으면 null. */
export function errorCode(error) {
  const e = error || {};
  return (e.body && e.body.error && e.body.error.code) || e.code || null;
}

/**
 * 목록 상태 하나를 정한다.
 *   loading       첫 요청이 진행 중인가(react-query 의 `isLoading` — 받아 둔 행이 없다)
 *   error         실패한 요청의 오류(`lib/api.js` 의 Error — `status` · `kind` · `body`)
 *   hasCondition  사용자가 건 조건(검색 · 필터 · 기본값 조건)이 하나라도 있는가 — 보기 기준(묶음)은 조건이 아니다
 *   count         보일 행 수
 */
export function resolveListState({ loading = false, error = null, hasCondition = false, count = 0 } = {}) {
  if (loading && !error) return "loading";
  if (error) {
    const status = Number(error.status) || 0;
    if (status === 401 || status === 403) return "forbidden";
    if (DISABLED_CODES.includes(errorCode(error))) return "disabled";
    if (error.kind === "network" || error.kind === "timeout" || UNREACHABLE_STATUS.has(status)) return "unreachable";
    return "error";
  }
  if (!count) return hasCondition ? "filtered-empty" : "empty";
  return "ready";
}

/** 다시 시도가 뜻이 있는 갈래인가 — 권한 · 꺼짐은 같은 요청을 다시 보내도 풀리지 않는다. */
export function canRetry(state) {
  return state === "unreachable" || state === "error";
}

/** 오류 판으로 그리는 갈래인가 — 표 대신 그 자리에 선다(불러오는 중 · 조건 0건 · 행은 표가 그린다). */
export function isFailureState(state) {
  return state === "forbidden" || state === "disabled" || state === "unreachable" || state === "error";
}
