/**
 * 운영 콘솔 시스템 설정 화면 (§S, 9-6/9-7/9-8).
 *
 * 여기서 보는 것은 **화면이 진실을 말하는가** 다. 특권 헬퍼는 없을 수도 있는 부품이라
 * (개발 머신·컨테이너·안 깐 설치) "없음" 을 정확히 전하는 것이 기능의 일부다.
 *
 * 가장 나쁜 실패는 도우미가 없는데 화면이 성공한 것처럼 보이는 것이다 - 사용자는 타임존을
 * 바꿨다고 믿고 떠난다.
 */
import { describe, expect, it } from "vitest";
import { buildParams, outcomeText } from "./SystemOps.jsx";

describe("보낼 값 만들기", () => {
  it("끄면 서버 목록을 함께 보내지 않는다", () => {
    // 빈 값에 뜻을 싣지 않는다 - 끄는 것은 끄겠다고 말한다(F5 가 정확히 그 결함이었다).
    expect(buildParams("ntp.set", { enabled: false, servers: "a, b" })).toEqual({ enabled: false });
  });

  it("쉼표 목록을 배열로 바꾸고 빈 칸을 버린다", () => {
    expect(buildParams("dns.set", { enabled: true, servers: "10.0.0.1, 10.0.0.2, " }))
      .toEqual({ enabled: true, servers: ["10.0.0.1", "10.0.0.2"] });
  });

  it("검색 도메인이 비면 아예 안 보낸다", () => {
    const got = buildParams("dns.set", { enabled: true, servers: "10.0.0.1", search: "" });
    expect(Object.keys(got)).not.toContain("search");
  });

  it("FQDN 이 비면 키를 아예 빼고 보낸다", () => {
    // 빈 문자열을 보내면 서버가 "FQDN 이 비었다" 로 거절한다. 안 보내는 것과는 다르다.
    const got = buildParams("hostname.set", { hostname: "srv1", fqdn: "" });
    expect(got).toEqual({ hostname: "srv1" });
  });

  it("FQDN 이 있으면 함께 보낸다", () => {
    expect(buildParams("hostname.set", { hostname: "srv1", fqdn: "srv1.example.com" }))
      .toEqual({ hostname: "srv1", fqdn: "srv1.example.com" });
  });

  it("프록시를 끄면 주소를 함께 보내지 않는다", () => {
    expect(buildParams("proxy.set", { enabled: false, url: "http://p:3128" }))
      .toEqual({ enabled: false });
  });
});

describe("결과 문구", () => {
  it("도우미가 없으면 성공이라고 말하지 않는다", () => {
    const text = outcomeText({ available: false, ok: false, detail: "도우미가 설치되어 있지 않습니다." });
    expect(text).toContain("도우미");
    expect(text).not.toContain("적용했습니다");
  });

  it("되돌아간 시도를 단순 실패로 뭉개지 않는다", () => {
    // 되돌아갔다는 사실 자체가 정보다 - 시스템이 반쯤 바뀐 것은 아닌지 알려 준다.
    const text = outcomeText({
      available: true, ok: false, rolled_back: true, detail: "nginx 설정 검사에 실패했습니다.",
    });
    expect(text).toContain("되돌렸습니다");
  });

  it("성공은 서버가 준 문장을 그대로 쓴다", () => {
    expect(outcomeText({ available: true, ok: true, detail: "타임존을 Asia/Seoul 로 바꿨습니다." }))
      .toBe("타임존을 Asia/Seoul 로 바꿨습니다.");
  });

  it("되돌아가지 않은 실패는 되돌렸다고 말하지 않는다", () => {
    const text = outcomeText({ available: true, ok: false, rolled_back: false, detail: "실패." });
    expect(text).not.toContain("되돌렸습니다");
  });
});
