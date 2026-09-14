/* 실패는 **그 자리의 메시지 박스**로 말한다 — 토스트가 아니다 (핸드오프 RULES §1 · ACCEPTANCE I3).
 *
 * 토스트는 몇 초 뒤 사라진다. 저장 실패 · 권한 없음 · 다시 눌러야 하는 실패가 거기 실리면 사용자가
 * 읽기 전에 사라지고, 무엇이 안 됐는지 화면 어디에도 남지 않는다. 그래서 실패는 그 동작이 속한 자리
 * (폼 · 모달 · 판 · 줄)에 남기고, 그 자리의 다음 시도가 시작되면 걷는다.
 *
 * ## 새 상태를 만들지 않는다
 *
 * 요청(`useMutation`)은 이미 자기 실패를 들고 있다 — `error` 와 보낸 시각 `submittedAt`. 한 자리에
 * 동작이 여럿이면(복원 · 삭제 · 비우기) **가장 나중에 보낸 요청** 하나만 말한다:
 *
 *   - 새로 시도하면 그 요청이 가장 나중 것이 되고, 아직 결과가 없으니 이전 실패는 사라진다.
 *   - 그 요청이 성공하면 다시 서지 않는다(성공한 요청이 가장 나중 것이다).
 *   - `reset()` 은 보낸 시각을 0 으로 되돌리므로 그 요청은 후보에서 빠진다(모달을 다시 열 때).
 *
 * 문구는 토스트 때와 **같다** — 서버가 준 문장, 없으면 그 동작의 기본 문장. */

/** 요청 여럿 중 가장 나중에 보낸 것. 하나도 안 보냈으면 `null`. */
export function latestMutation(...mutations) {
  let latest = null;
  for (const m of mutations) {
    if (!m || !m.submittedAt) continue;
    if (!latest || m.submittedAt >= latest.submittedAt) latest = m;
  }
  return latest;
}

/** `[요청, 기본 문장]` 쌍 여럿 중 가장 나중에 보낸 요청의 실패 문장. 실패가 아니면 `null`. */
export function failureText(...pairs) {
  const live = pairs.filter((pair) => pair && pair[0]);
  const latest = latestMutation(...live.map((pair) => pair[0]));
  if (!latest || !latest.isError) return null;
  const fallback = live.find((pair) => pair[0] === latest)[1];
  const e = latest.error;
  return (e && e.message) || fallback || null;
}

/** 손으로 부른 요청(try/catch)의 실패 문장 — 토스트와 같은 규칙으로 고른다. */
export function errorText(e, fallback) {
  return (e && e.message) || fallback || null;
}
