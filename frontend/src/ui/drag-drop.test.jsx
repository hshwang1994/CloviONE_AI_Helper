import { describe, expect, it } from "vitest";
import { neighboursForBoard, neighboursForList } from "./DragDrop.jsx";

/* 끌어 놓기 공통 부품의 **자리 계산** (S6).
 *
 * 서버는 「놓인 자리의 두 이웃」만 받아 소수 순위로 그 사이 값을 만든다
 * (`app/work/rank.py`). 그래서 이 계산이 틀리면 카드가 한 칸 어긋난 자리에 앉는데,
 * **화면은 정상으로 보인다** — 순서가 하나 밀렸을 뿐이라 눈으로는 못 잡는다.
 *
 * 인덱스가 아니라 이웃 두 개를 보내는 이유도 여기서 함께 고정한다: 인덱스는 다른
 * 사람이 그 사이에 한 줄 넣는 순간 뜻이 달라지지만, 이웃 두 개는 그렇지 않다. */

const IDS = ["a", "b", "c", "d"];

describe("목록 안에서 옮기기", () => {
  it("아래로 끌면 대상의 **뒤**에 놓인다", () => {
    // a 를 c 자리로 → c 와 d 사이
    expect(neighboursForList(IDS, "a", "c")).toEqual({ beforeId: "c", afterId: "d" });
  });

  it("위로 끌면 대상의 **앞**에 놓인다", () => {
    // d 를 b 자리로 → a 와 b 사이
    expect(neighboursForList(IDS, "d", "b")).toEqual({ beforeId: "a", afterId: "b" });
  });

  it("맨 위로 끌면 앞 이웃이 없다", () => {
    expect(neighboursForList(IDS, "c", "a")).toEqual({ beforeId: null, afterId: "a" });
  });

  it("맨 아래로 끌면 뒤 이웃이 없다", () => {
    expect(neighboursForList(IDS, "a", "d")).toEqual({ beforeId: "d", afterId: null });
  });

  it("제자리에 놓으면 아무것도 안 보낸다", () => {
    // 안 걸러내면 순위만 바뀌는 요청이 서버로 가고, 그 요청도 버전을 올려
    // 다른 사람의 편집이 헛 충돌한다.
    expect(neighboursForList(IDS, "b", "b")).toBeNull();
  });

  it("목록에 없는 id 는 무시한다", () => {
    expect(neighboursForList(IDS, "zz", "b")).toBeNull();
    expect(neighboursForList(IDS, "a", "zz")).toBeNull();
  });
});

describe("칸 사이로 옮기기", () => {
  it("카드 위에 놓으면 그 카드의 앞에 앉는다", () => {
    expect(neighboursForBoard(["x", "y", "z"], "a", "y")).toEqual({
      beforeId: "x",
      afterId: "y",
    });
  });

  it("빈 칸에 놓으면 맨 뒤로 간다", () => {
    // 받을 카드가 없으면 `over.id` 가 칸 자신이다. 이 갈래가 없으면 **빈 칸으로는
    // 영영 못 옮긴다** — 칸반에서 마지막 카드를 뺀 순간 정확히 그 상태가 된다.
    expect(neighboursForBoard(["x", "y"], "a", "__column__")).toEqual({
      beforeId: "y",
      afterId: null,
    });
  });

  it("아무것도 없는 칸에 놓으면 이웃이 둘 다 없다", () => {
    expect(neighboursForBoard([], "a", "__column__")).toEqual({
      beforeId: null,
      afterId: null,
    });
  });

  /* qa-contract-change: 같은 칸 안의 이동이 방향을 본다. 예전 계약(항상 대상 앞)은
   * 「b 를 c 위에 놓으면 a 와 c 사이」였는데, 그 자리는 b 의 **원래 자리**다 — 한 칸
   * 아래로 끌기가 no-op 이었고, 이 시험이 그 결함을 계약으로 고정하고 있었다. */
  it("🔴 같은 칸에서 아래로 끌면 대상의 **뒤**에 놓인다 — 제자리 no-op 이 아니다", () => {
    expect(neighboursForBoard(["a", "b", "c"], "b", "c")).toEqual({
      beforeId: "c",
      afterId: null,
    });
    expect(neighboursForBoard(["a", "b", "c", "d"], "a", "c")).toEqual({
      beforeId: "c",
      afterId: "d",
    });
  });

  it("같은 칸에서 위로 끌면 대상의 **앞**에 놓인다", () => {
    expect(neighboursForBoard(["a", "b", "c"], "c", "a")).toEqual({
      beforeId: null,
      afterId: "a",
    });
  });

  it("같은 칸의 제자리에 놓으면 아무것도 안 보낸다", () => {
    // 걸러내지 않으면 순위만 바뀌는 헛 요청이 서버로 가고, 그 요청도 version 을 올려
    // 뒤이은 드래그가 자기 자신과 409 충돌한다.
    expect(neighboursForBoard(["a", "b", "c"], "b", "b")).toBeNull();
  });
});
