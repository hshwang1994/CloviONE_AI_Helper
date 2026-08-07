/* 방 목록 캐시에서 '그 방을 읽었다'를 반영한다 (PF3).
 *
 * 왜 필요한가. 채팅 창은 새 메시지를 받으면 읽음 위치를 서버에 올린다. 그리고 그 성공을
 * 계기로 **방 목록 전체를 다시 받았다.** 방 목록은 이 앱에서 가장 비싼 조회 축이고(H4),
 * 모든 화면에서 이미 주기적으로 돈다. 결과적으로 메시지 한 통이 요청 세 개(메시지 폴링 +
 * 읽음 쓰기 + 목록 재조회)가 됐다 — 대화가 활발할수록 배로 늘어나는 구조다.
 *
 * 그런데 읽음 처리가 목록에서 바꾸는 값은 **그 방의 안 읽음 하나뿐**이다. 마지막 메시지도,
 * 제목도, 참여자 수도 그대로다. 서버에 다시 물을 이유가 없다 — 우리가 방금 무엇을 했는지
 * 알고 있으니 캐시를 그대로 고치면 된다. 어긋나더라도 목록은 계속 폴링되므로 스스로 맞는다.
 *
 * 합계(`unread_total`)를 다시 계산하는 규칙은 서버(app/team_chat/router.py list_rooms)와
 * 같아야 한다: items 의 합 + 팀 방 + 전체 채팅. 여기만 고치고 서버를 안 보면 사이드바
 * 숫자와 목록 숫자가 서로 다른 말을 하게 된다.
 *
 * 새 객체를 만들어 돌려준다(제자리 수정 금지 — 저장소 규칙). 바뀐 게 없으면 **받은 것을
 * 그대로** 돌려준다: 참조가 그대로여야 react-query 가 화면을 헛되이 다시 그리지 않는다.
 */

function clearUnread(room, roomId, changed) {
  if (!room || room.id !== roomId || !room.unread) return room;
  changed.hit = true;
  return { ...room, unread: 0 };
}

function sumUnread(data) {
  const items = (data.items || []).reduce((n, r) => n + (r.unread || 0), 0);
  const team = (data.team && data.team.unread) || 0;
  const glob = (data.global && data.global.unread) || 0;
  return items + team + glob;
}

/**
 * @param {object|undefined} data  `/api/team-chat/rooms` 응답 모양의 캐시 값
 * @param {string} roomId          방금 읽은 방
 * @returns {object|undefined}     안 읽음을 0으로 만든 새 값(바뀐 게 없으면 원본 그대로)
 */
export function markRoomRead(data, roomId) {
  if (!data || !roomId) return data;
  const changed = { hit: false };
  const items = (data.items || []).map((r) => clearUnread(r, roomId, changed));
  const team = clearUnread(data.team, roomId, changed);
  const glob = clearUnread(data.global, roomId, changed);
  if (!changed.hit) return data;
  const next = { ...data, items };
  if (data.team !== undefined) next.team = team;
  if (data.global !== undefined) next.global = glob;
  next.unread_total = sumUnread(next);
  return next;
}
