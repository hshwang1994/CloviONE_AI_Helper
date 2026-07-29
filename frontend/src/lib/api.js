/* 공통 API 클라이언트. 세션 쿠키(same-origin) + CSRF 헤더. 401은 별도로 표시해
 * 인증 만료를 로그인 안내로 다룬다. 서버 오류는 표준 에러로 던진다(화면이 오류 상태 표시). */
let csrfToken = null;
export function setCsrf(token) { csrfToken = token; }

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
    const err = new Error("로그인이 필요합니다.");
    err.status = 401;
    throw err;
  }
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  if (!r.ok) {
    const msg = (body && body.error && body.error.message) || ("요청 실패 (" + r.status + ")");
    const err = new Error(msg);
    err.status = r.status;
    err.body = body;
    // 방어적 2중 안전장치 — Layout의 must_change_password 리다이렉트가 아직 실행되기 전(예: /api/me가
    // 아직 응답하지 않은 순간)에 다른 API가 먼저 이 오류를 맞으면, 여기서도 즉시 이동시킨다.
    if (body && body.error && body.error.code === "password_change_required") {
      window.location.href = "/change-password";
    }
    throw err;
  }
  return body;
}
