/* celebration.js — deriveCelebrateKey unit 테스트.
 *
 * 배경 — 지금까지 이 함수를 직접 부르는 테스트가 없었다. gameroom.test.jsx는 GameRoom을
 * 렌더해 축포 함수(confetti mock)가 호출되는지만 간접 확인했고, deriveCelebrateKey 자체의
 * 분기(게임 종류별 신호 문자열, "아직 승자 없음"/"무승부"일 때 null)는 한 번도 직접
 * 단정되지 않았다. 이 함수가 null을 잘못 돌려주면(예: 방이 finished인데 신호가 없다고
 * 오판) 실제로 이긴 사람이 있는데 축포가 안 터지는 조용한 회귀가 되고, 반대로 자바스크립트
 * 코드 상 truthy 값 하나만 잘못 세면 무승부에도 축포가 터지는 회귀가 된다 — 둘 다 화면
 * 스냅샷만으로는 못 잡는다(confetti는 mock되어 있어 어떤 인자로도 "그냥 호출됨"만 보인다). */
import { describe, it, expect } from "vitest";
import { deriveCelebrateKey } from "./celebration.js";

const room = (overrides = {}) => ({
  id: "r1", title: "t", game_type: "random_draw", status: "finished", ...overrides,
});

describe("deriveCelebrateKey — 방이 finished + 승자가 있을 때만 키를 낸다", () => {
  it("방이 없거나 상태가 finished가 아니면 null (진행 중 오발화 방지)", () => {
    expect(deriveCelebrateKey(null)).toBeNull();
    expect(deriveCelebrateKey({})).toBeNull();
    expect(deriveCelebrateKey({ room: room({ status: "playing" }), state: { result: [{ user_id: "u1" }] } })).toBeNull();
  });

  it("finished인데 result가 없으면 null (아직 집계 전)", () => {
    expect(deriveCelebrateKey({ room: room(), state: {} })).toBeNull();
    expect(deriveCelebrateKey({ room: room(), state: { result: null } })).toBeNull();
  });

  it("random_draw: 당첨자 배열 → 방 id + 당첨자 user_id 목록으로 신호를 만든다", () => {
    const data = { room: room({ game_type: "random_draw" }), state: { result: [{ user_id: "u1" }, { user_id: "u2" }] } };
    expect(deriveCelebrateKey(data)).toBe("r1d:u1,u2");
  });

  it("random_draw: 결과 배열이 비어 있으면 null (당첨자 없음)", () => {
    const data = { room: room({ game_type: "random_draw" }), state: { result: [] } };
    expect(deriveCelebrateKey(data)).toBeNull();
  });

  it("quick_vote: 승자가 있을 때만 신호, 빈 winners면 null", () => {
    const win = { room: room({ game_type: "quick_vote" }), state: { result: { winners: ["짜장"] } } };
    expect(deriveCelebrateKey(win)).toBe("r1v:짜장");
    const none = { room: room({ game_type: "quick_vote" }), state: { result: { winners: [] } } };
    expect(deriveCelebrateKey(none)).toBeNull();
  });

  it("number: winner가 있을 때만 신호", () => {
    const win = { room: room({ game_type: "number" }), state: { result: { winner: { user_id: "u9" } } } };
    expect(deriveCelebrateKey(win)).toBe("r1n:u9");
    const none = { room: room({ game_type: "number" }), state: { result: {} } };
    expect(deriveCelebrateKey(none)).toBeNull();
  });

  it("rps 토너먼트: champion이 있을 때만 신호", () => {
    const data = {
      room: room({ game_type: "rps" }),
      state: { result: { mode: "tournament", champion: { user_id: "u5" } } },
    };
    expect(deriveCelebrateKey(data)).toBe("r1t:u5");
  });

  it("rps 일반전: 무승부(draw)면 null — 승자 없는데 축포가 터지면 안 된다", () => {
    const draw = { room: room({ game_type: "rps" }), state: { result: { outcome: "draw", winners: [] } } };
    expect(deriveCelebrateKey(draw)).toBeNull();
  });

  it("rps 일반전: outcome이 win일 때만 신호, 승자 목록을 그대로 담는다", () => {
    const data = {
      room: room({ game_type: "rps" }),
      state: { result: { outcome: "win", winners: [{ user_id: "u1" }, { user_id: "u2" }] } },
    };
    expect(deriveCelebrateKey(data)).toBe("r1r:u1,u2");
  });

  it("quiz: 승자 목록이 있을 때만 신호", () => {
    const win = { room: room({ game_type: "quiz" }), state: { result: { winners: ["u1"] } } };
    expect(deriveCelebrateKey(win)).toBe("r1q:u1");
    const none = { room: room({ game_type: "quiz" }), state: { result: { winners: [] } } };
    expect(deriveCelebrateKey(none)).toBeNull();
  });

  it("결과가 같으면 키도 같다 — 1.2초 폴링을 돌아도 재발화하지 않는다는 계약의 전제", () => {
    const a = { room: room({ game_type: "random_draw" }), state: { result: [{ user_id: "u1" }] } };
    const b = { room: room({ game_type: "random_draw" }), state: { result: [{ user_id: "u1" }] } };
    expect(deriveCelebrateKey(a)).toBe(deriveCelebrateKey(b));
  });

  it("알 수 없는 game_type이면 null (신규 게임 종류 추가 전까지는 조용히 무시)", () => {
    const data = { room: room({ game_type: "unknown_future_game" }), state: { result: { winners: ["u1"] } } };
    expect(deriveCelebrateKey(data)).toBeNull();
  });
});
