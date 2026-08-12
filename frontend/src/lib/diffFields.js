/* 수정 폼이 전체 스냅샷을 다시 보내지 않고 실제로 바뀐 필드만 PATCH하게 한다 (CONC-01) —
 * 그대로 전부 재전송하면 그 사이 다른 관리자가 바꾼 필드를 조용히 덮어쓸 수 있다. 서버는
 * `payload.model_dump(exclude_unset=True)`로 받으므로 JSON에 아예 없는 키는 "안 건드림"으로
 * 정확히 해석한다 — 이 함수가 만드는 부분 body만으로 백엔드 쪽 변경은 필요 없다.
 *
 * 원래 Users.jsx 전용이었다가 DataScreen.jsx의 공용 수정 폼에도 같은 문제(config_version이
 * 있는데 검사도 안 하고 매번 전체 재전송)가 있어 여기로 옮겼다. 옮기며 값 비교를
 * `String(obj)`("[object Object]"로 뭉개져 내용이 달라도 항상 "같음"으로 잘못 판정하던 버그) 대신
 * JSON 직렬화 비교로 바꿨다 — Users.jsx는 필드가 전부 원시값이라 안 드러났지만, DataScreen의
 * toApiBody가 만드는 객체 필드(예: templates의 approval_policy)에는 실제로 걸린다.
 */
function isEmpty(v) {
  return v == null || v === "";
}

function sameValue(before, after) {
  if (typeof before === "boolean" || typeof after === "boolean") return !!before === !!after;
  if (isEmpty(before) && isEmpty(after)) return true;
  if ((before && typeof before === "object") || (after && typeof after === "object")) {
    try { return JSON.stringify(before) === JSON.stringify(after); } catch (e) { return false; }
  }
  return String(before) === String(after);
}

export function diffFields(body, initial) {
  const out = {};
  for (const k of Object.keys(body || {})) {
    const before = initial ? initial[k] : undefined;
    const after = body[k];
    if (!sameValue(before, after)) out[k] = after;
  }
  return out;
}
