/* 공통 API 클라이언트. 세션 쿠키(same-origin) + CSRF 헤더. 401은 별도로 표시해
 * 인증 만료를 로그인 안내로 다룬다. 서버 오류는 표준 에러로 던진다(화면이 오류 상태 표시). */
let csrfToken = null;
export function setCsrf(token) { csrfToken = token; }

let unauthorizedHandler = null;

/* 상태 코드 → 사람이 읽는 말 (E10). 서버 봉투에 문구가 있으면 그쪽이 항상 이긴다 —
   이건 봉투가 없을 때(프록시·게이트웨이·타임아웃)만 쓰는 대비책이다. */
function fallbackMessage(status) {
  if (status === 401) return "로그인이 필요합니다.";
  if (status === 403) return "권한이 없습니다.";
  if (status === 404) return "요청한 항목을 찾을 수 없습니다.";
  if (status === 409) return "다른 곳에서 먼저 바뀌었습니다. 새로고침한 뒤 다시 시도해 주세요.";
  if (status === 413) return "보내려는 내용이 너무 큽니다.";
  if (status === 429) return "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.";
  if (status >= 500) return "서버에서 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.";
  return "요청을 처리하지 못했습니다.";
}

export async function api(path, options = {}) {
  const opts = { credentials: "same-origin", headers: {}, ...options };
  opts.headers = { ...opts.headers };
  if (opts.method && opts.method !== "GET") {
    opts.headers["X-CSRF-Token"] = csrfToken || "";
    // FormData(파일 업로드)는 JSON으로 감싸지 않는다 — 브라우저가 multipart 경계를 직접
    // 붙이도록 Content-Type도 설정하지 않는다. 그 외 객체 본문만 JSON 직렬화한다.
    if (opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)) {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
  }
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    const err = new Error("서버에 연결할 수 없습니다.");
    err.kind = "network";
    throw err;
  }
  if (r.status === 401) {
    // `/api/me` 자신의 401 은 예외다 - 그 요청은 이미 `["me"]` 쿼리이고, 실패는 react-query
    // 가 `isError` 로 스스로 반영한다(retry:false). 여기서도 무효화를 부르면: 무효화 →
    // `/api/me` 재요청 → 401 → 무효화 → ... 무한 루프로 브라우저 탭이 죽는다(재현: 새
    // vitest 테스트가 정확히 이 경로를 실행하다 힙이 바닥나며 워커가 죽었다).
    if (unauthorizedHandler && path !== "/api/me") unauthorizedHandler();
    const err = new Error("로그인이 필요합니다.");
    err.status = 401;
    throw err;
  }
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  if (!r.ok) {
    /* 서버가 문구를 안 줬을 때의 대비책 (E10). 예전에는 `"요청 실패 (500)"` 을 그대로 띄웠다 —
       **사용자가 HTTP 상태 코드를 읽는다.** 무엇이 잘못됐는지도, 무엇을 하면 되는지도 말하지
       않는 문자열이다. 상태별로 사람의 말을 준다(문구는 여기 한 곳에만 있다). */
    const msg = (body && body.error && body.error.message) || fallbackMessage(r.status);
    const err = new Error(msg);
    err.status = r.status;
    err.body = body;
    /* 상관 id 를 오류에 싣는다 (Z8).
     *
     * 서버는 이미 요청마다 id 를 만들어 **오류 봉투와 `X-Request-ID` 헤더에 둘 다** 실어
     * 보내고, 감사 로그도 그 값을 저장한다. 그런데 프런트가 그걸 한 번도 읽지 않아서
     * **어느 토스트에도 id 가 없었다** — 사용자가 "화면이 안 나와요" 라고 하면 운영자에게
     * 남는 단서는 경로와 상태 코드뿐이었다. 배관은 다 깔려 있었고 양 끝이 끊겨 있었다.
     *
     * 헤더도 같이 본다: 봉투를 만들기 전에 터지는 오류(프록시·게이트웨이)는 본문이 없다. */
    err.requestId = (body && body.error && body.error.request_id) || r.headers.get("X-Request-ID") || null;
    // 방어적 2중 안전장치 — Layout의 must_change_password 리다이렉트가 아직 실행되기 전(예: /api/me가
    // 아직 응답하지 않은 순간)에 다른 API가 먼저 이 오류를 맞으면, 여기서도 즉시 이동시킨다.
    if (body && body.error && body.error.code === "password_change_required") {
      window.location.href = "/change-password";
    }
    throw err;
  }
  return body;
}

/* '세션 만료' 화면(App.jsx 의 `minimal = auth.isError`)으로 넘어가는 유일한 통로.
 *
 * `["me"]` 쿼리는 `retry:false` + 전역 `refetchOnWindowFocus:false` + `refetchInterval`
 * 없음이다 - **누군가 다시 부르지 않으면 영원히 마지막 성공값을 그대로 보여 준다.** 그런데
 * 이 모듈(api.js)은 react-query 를 모르는 순수 함수라 그 쿼리를 직접 못 건드린다. 그래서
 * `AuthProvider` 가 부팅 시 이 자리에 `queryClient.invalidateQueries` 를 등록해 둔다 - 다른
 * API(예: 티켓 목록)가 401 을 맞는 그 순간, `["me"]` 도 다시 물어 진짜로 세션이 죽었는지
 * 확인하고 셸을 최소 모드로 넘긴다. 등록 전(테스트, 아주 이른 부팅)에는 아무 일도 안 한다 -
 * 로그인 화면 자체의 401(정상 흐름)까지 건드릴 이유는 없다.
 *
 * ⚠️ 별도 named export 가 아니라 **`api` 함수의 속성**으로 붙인다. 이 저장소의 수백 개
 * 테스트가 `vi.mock("../lib/api.js", () => ({ api: ... }))` 로 이 모듈을 부분적으로
 * 흉내 내는데, vitest 의 모듈 목은 factory 가 안 돌려준 named export 에 접근하는 순간(단순
 * 존재 확인조차) 즉시 던진다 - named export 로 추가하면 그 수백 개 목을 전부 고쳐야 했다.
 * `api` 함수 객체의 속성은 그 검사를 안 지난다(평범한 JS 프로퍼티 접근이라, 목이 돌려준
 * 함수에 이 속성이 없으면 그냥 `undefined` 다) - 그래서 기존 목이 전부 그대로 산다. */
api.onUnauthorized = function (fn) { unauthorizedHandler = fn; };
