import { describe, it, expect } from "vitest";

import { GROUP_GAP_MINUTES, groupMessages } from "./chat-groups.js";
import { chatDayLabel, kstDayKey } from "../lib/format.js";

/* 대화를 읽는 단위로 묶는 판정 (지시 17).
 *
 * 이 판정이 틀리는 자리는 화면에서 눈에 잘 안 띈다 — 대화는 어떻게 묶여도 그럴듯하게
 * 보이기 때문이다. 그래서 순수 함수로 꺼내 직접 본다.
 *
 * 시각은 전부 **naive UTC** 다(서버가 주는 모양). KST 는 UTC+9 라 UTC 15:00 이 KST 자정이고,
 * 이 파일의 자정 경계 표본은 그 사실 위에 서 있다.
 */

const ME = "u-me";
const PEER = "u-peer";

function msg(over) {
  return { seq: 1, sender_user_id: PEER, sender_name: "상대", body: "말", kind: "text", created_at: "2026-08-27T01:00:00", ...over };
}

/** 「오늘·어제」가 아니라 날짜로 적히게 하는 기준 시각. 표본과 멀리 떨어뜨려 둔다. */
const LATER = new Date("2027-01-01T00:00:00Z");

describe("날짜 구분선", () => {
  it("첫 메시지 앞에는 언제나 구분선이 선다", () => {
    const rows = groupMessages([msg({ seq: 1 })], ME, LATER);
    expect(rows[0].kind).toBe("day");
    expect(rows[0].day).toBe("2026-08-27");
  });

  it("같은 날의 메시지 사이에는 구분선이 없다", () => {
    const rows = groupMessages(
      [
        msg({ seq: 1, created_at: "2026-08-27T01:00:00" }),
        msg({ seq: 2, created_at: "2026-08-27T09:00:00" }),
      ],
      ME, LATER,
    );
    expect(rows.filter((r) => r.kind === "day")).toHaveLength(1);
  });

  it("🔴 날이 바뀌면 구분선이 선다 — 판정은 KST 달력일이다", () => {
    /* UTC 14:59 와 15:01 은 한 시간도 안 떨어져 있지만 KST 로는 **다른 날**이다
       (15:00 UTC = 다음 날 00:00 KST). UTC 로 날을 세면 이 두 줄 사이에 구분선이
       안 서고, 자정 직후에 온 말이 어제 대화에 붙는다. */
    const rows = groupMessages(
      [
        msg({ seq: 1, created_at: "2026-08-27T14:59:00" }),
        msg({ seq: 2, created_at: "2026-08-27T15:01:00" }),
      ],
      ME, LATER,
    );
    const days = rows.filter((r) => r.kind === "day").map((r) => r.day);
    expect(days).toEqual(["2026-08-27", "2026-08-28"]);
  });

  it("🔴 자정을 넘긴 연속 발언은 묶음이 끊긴다 — 구분선 아래 첫 줄에 이름이 선다", () => {
    /* 같은 사람이 1분 간격으로 이어 말했더라도, 구분선 **아래**의 첫 줄이 이름 없이
       시작하면 그 날의 대화가 익명으로 열린다. */
    const rows = groupMessages(
      [
        msg({ seq: 1, created_at: "2026-08-27T14:59:00" }),
        msg({ seq: 2, created_at: "2026-08-27T15:00:30" }),
      ],
      ME, LATER,
    );
    const messages = rows.filter((r) => r.kind === "message");
    expect(messages.map((r) => r.head)).toEqual([true, true]);
  });

  it("오늘과 어제는 이름으로 부른다", () => {
    const now = new Date("2026-08-27T05:00:00Z");
    expect(chatDayLabel("2026-08-27T01:00:00", now)).toBe("오늘");
    // KST 로 8월 26일인 시각 — UTC 로는 26일 오후다.
    expect(chatDayLabel("2026-08-26T04:00:00", now)).toBe("어제");
    expect(chatDayLabel("2026-08-20T04:00:00", now)).toContain("8월");
  });

  it("🔴 월이 바뀌는 자리에서도 「어제」가 하루만 뒤로 간다", () => {
    /* 오늘에서 24시간을 빼는 방식이면 월초에서 어긋난다. 달력일에서 하루를 뺀다. */
    const now = new Date("2026-09-01T05:00:00Z");  // KST 9월 1일 14시
    expect(chatDayLabel("2026-08-31T04:00:00", now)).toBe("어제");
  });

  it("KST 달력일 키는 UTC 오후를 다음 날로 읽는다", () => {
    expect(kstDayKey("2026-08-27T14:59:00")).toBe("2026-08-27");
    expect(kstDayKey("2026-08-27T15:00:00")).toBe("2026-08-28");
    expect(kstDayKey(null)).toBe("");
  });
});

describe("같은 사람의 연속 발언", () => {
  it("짧은 사이의 이어지는 말은 머리를 한 번만 그린다", () => {
    const rows = groupMessages(
      [
        msg({ seq: 1, created_at: "2026-08-27T01:00:00" }),
        msg({ seq: 2, created_at: "2026-08-27T01:01:00" }),
        msg({ seq: 3, created_at: "2026-08-27T01:02:00" }),
      ],
      ME, LATER,
    ).filter((r) => r.kind === "message");
    expect(rows.map((r) => r.head)).toEqual([true, false, false]);
  });

  it("사람이 바뀌면 머리가 다시 선다", () => {
    const rows = groupMessages(
      [
        msg({ seq: 1, sender_user_id: PEER, created_at: "2026-08-27T01:00:00" }),
        msg({ seq: 2, sender_user_id: ME, sender_name: "나", created_at: "2026-08-27T01:00:30" }),
      ],
      ME, LATER,
    ).filter((r) => r.kind === "message");
    expect(rows.map((r) => r.head)).toEqual([true, true]);
  });

  it("🔴 내 말도 예외가 아니다 — 묶임도 머리도 남과 같은 규칙이다", () => {
    /* 예전 화면은 내 말을 오른쪽 말풍선으로 그리고 **아바타도 이름도 안 그렸다.**
       그 예외가 여기서 되살아나지 않게 못박는다. */
    const rows = groupMessages(
      [
        msg({ seq: 1, sender_user_id: ME, sender_name: "나", created_at: "2026-08-27T01:00:00" }),
        msg({ seq: 2, sender_user_id: ME, sender_name: "나", created_at: "2026-08-27T01:01:00" }),
      ],
      ME, LATER,
    ).filter((r) => r.kind === "message");
    expect(rows.map((r) => r.head)).toEqual([true, false]);
  });

  it("사이가 벌어지면 머리가 다시 선다", () => {
    const rows = groupMessages(
      [
        msg({ seq: 1, created_at: "2026-08-27T01:00:00" }),
        msg({ seq: 2, created_at: `2026-08-27T01:${String(GROUP_GAP_MINUTES + 1).padStart(2, "0")}:00` }),
      ],
      ME, LATER,
    ).filter((r) => r.kind === "message");
    expect(rows.map((r) => r.head)).toEqual([true, true]);
  });

  it("🔴 시스템 메시지는 묶음을 끊는다", () => {
    /* 「나갔습니다」 아래에 그 사람의 옛 발언이 이름 없이 이어 붙으면, 방금 나간
       사람이 계속 말하는 것처럼 읽힌다. */
    const rows = groupMessages(
      [
        msg({ seq: 1, created_at: "2026-08-27T01:00:00" }),
        msg({ seq: 2, kind: "system", body: "상대 님이 나갔습니다.", created_at: "2026-08-27T01:00:30" }),
        msg({ seq: 3, created_at: "2026-08-27T01:01:00" }),
      ],
      ME, LATER,
    ).filter((r) => r.kind === "message");
    expect(rows.map((r) => r.head)).toEqual([true, true, true]);
  });
});

describe("빈 입력", () => {
  it("메시지가 없으면 줄도 없다 — 구분선만 있는 화면을 만들지 않는다", () => {
    expect(groupMessages([], ME, LATER)).toEqual([]);
    expect(groupMessages(null, ME, LATER)).toEqual([]);
  });
});
