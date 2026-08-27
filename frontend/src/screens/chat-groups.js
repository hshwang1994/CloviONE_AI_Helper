import { chatDayLabel, kstDayKey, toUTCDate } from "../lib/format.js";

/* 대화 줄을 **읽는 단위로 묶는다** (지시 17).
 *
 * ## 왜 순수 함수인가
 *
 * 「이 줄이 묶음의 첫 줄인가」와 「여기서 날이 바뀌었는가」는 렌더가 아니라 **판정**이다.
 * JSX 안에 인라인으로 두면 그 판정을 렌더 하네스를 통해서만 만질 수 있고, 실제로 틀리는
 * 자리(자정을 넘긴 연속 발언, 시스템 메시지를 사이에 둔 같은 사람의 두 말)는 화면에서
 * 눈에 잘 안 띈다 — 대화가 그럴듯하게 보이기 때문이다.
 *
 * ## 규칙 셋
 *
 *   1. **날이 바뀌면 구분선이 선다.** KST 달력일 기준이다(`kstDayKey`). 브라우저 로컬로
 *      재면 시계가 어긋난 사람에게만 구분선이 하루 밀린다.
 *   2. **같은 사람이 짧은 사이에 이어 말하면 머리를 한 번만 그린다.** 다섯 줄을 연달아
 *      쓴 사람의 이름과 얼굴이 다섯 번 서면 대화가 아니라 명단으로 보인다.
 *   3. **그래도 누가 언제 썼는지는 항상 확인할 수 있다.** 이어지는 줄은 머리를 안 그리는
 *      대신 왼쪽 홈통에 자기 시각을 갖는다(화면 쪽 책임) — 그래서 여기서는 묶더라도
 *      `message` 를 통째로 넘긴다. 무엇을 감출지는 여기서 정하지 않는다.
 *
 * ## 묶이지 않는 것들
 *
 * 시스템 메시지는 자기 줄로 서고 **묶음을 끊는다.** 「A 님이 나갔습니다」 아래에 A 의
 * 옛 발언이 이어 붙으면 방금 나간 사람이 계속 말하는 것처럼 읽힌다.
 */

/** 같은 사람의 말을 한 묶음으로 볼 수 있는 최대 간격(분).
 *
 * 5분이다. 이보다 길게 잡으면 오전에 한 말과 점심 뒤에 한 말이 한 덩어리가 되어 「언제
 * 한 얘기지」가 흐려지고, 짧게 잡으면 타자가 느린 사람의 연속 발언이 매번 갈린다.
 */
export const GROUP_GAP_MINUTES = 5;

function minutesBetween(a, b) {
  const x = toUTCDate(a);
  const y = toUTCDate(b);
  if (!x || !y) return Infinity;
  return Math.abs(y.getTime() - x.getTime()) / 60000;
}

/** 메시지 목록 → 화면이 그대로 그리는 줄 목록.
 *
 * 돌려주는 것은 두 종류다.
 *
 *     { kind: "day", day: "2026-08-27", label: "오늘" }
 *     { kind: "message", message, head: true|false }
 *
 * `head` 가 참이면 얼굴과 이름과 시각이 서는 줄이고, 거짓이면 본문만 있는 이어지는 줄이다.
 *
 * `now` 는 「오늘·어제」 판정에 쓴다. 인자로 받는 이유는 시험이 시계를 고정할 수 있어야
 * 하기 때문이다 — 안 받으면 자정 근처에서만 깨지는 검사가 된다.
 */
export function groupMessages(messages, meId, now) {
  const list = Array.isArray(messages) ? messages : [];
  const out = [];
  let day = null;
  let prev = null;
  for (const m of list) {
    if (!m) continue;
    const key = kstDayKey(m.created_at);
    if (key && key !== day) {
      day = key;
      out.push({ kind: "day", day: key, label: chatDayLabel(m.created_at, now) });
      // 날이 바뀌면 묶음도 끊는다. 자정을 넘긴 연속 발언이 어제 묶음에 붙으면 구분선
      // **아래**의 첫 줄이 이름 없이 시작한다.
      prev = null;
    }
    if (m.kind === "system") {
      out.push({ kind: "message", message: m, head: true });
      prev = null;
      continue;
    }
    const head =
      prev === null ||
      prev.sender_user_id !== m.sender_user_id ||
      minutesBetween(prev.created_at, m.created_at) > GROUP_GAP_MINUTES;
    out.push({ kind: "message", message: m, head });
    prev = m;
  }
  return out;
}
