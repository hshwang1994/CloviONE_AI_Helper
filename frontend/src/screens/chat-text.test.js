import { describe, it, expect } from "vitest";
import { LINK_REL, LINK_TARGET, mentionNames, safeHref, tokenizeMessage } from "./chat-text.js";

/* 말풍선 본문 해석 — 링크 화이트리스트와 @멘션.
 *
 * 이 파일이 지키는 가장 중요한 것: **사용자가 친 글자가 링크가 되는 조건**이다.
 * `javascript:` / `data:` 가 한 번이라도 통과하면 그건 저장형 XSS다(누가 채팅에 붙여 넣고,
 * 다른 사람이 누른다). 정규식과 파싱 두 겹을 각각 시험한다.
 */

const NAMES = ["홍길동", "김철", "김철수", "Ann"];

// ── 1. 스킴 화이트리스트 ────────────────────────────────────────────────────

describe("safeHref — http/https만 통과한다", () => {
  it("http와 https는 통과한다", () => {
    expect(safeHref("https://intra.example/a")).toBe("https://intra.example/a");
    expect(safeHref("http://10.100.64.71/x")).toBe("http://10.100.64.71/x");
  });

  it.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "//evil.example/steal",
    "",
    null,
  ])("위험하거나 상대적인 주소는 null이다: %s", (raw) => {
    expect(safeHref(raw)).toBeNull();
  });
});

// ── 2. 토큰화: 링크 ─────────────────────────────────────────────────────────

describe("tokenizeMessage — 링크", () => {
  it("문장 속 http(s) 주소만 링크 조각이 된다", () => {
    const tokens = tokenizeMessage("배포 문서는 https://intra.example/deploy 입니다", NAMES);
    const link = tokens.find((t) => t.kind === "link");
    expect(link).toEqual({ kind: "link", text: "https://intra.example/deploy", href: "https://intra.example/deploy" });
    expect(tokens.map((t) => t.text).join("")).toBe("배포 문서는 https://intra.example/deploy 입니다");
  });

  it("javascript: / data: 는 링크가 되지 않고 평범한 글자로 남는다", () => {
    const tokens = tokenizeMessage("javascript:alert(1) 와 data:text/html,<script>x</script> 조심", NAMES);
    expect(tokens.some((t) => t.kind === "link")).toBe(false);
    // 글자 자체는 하나도 사라지지 않는다(조용히 지우면 무슨 말을 했는지 알 수 없다).
    expect(tokens.map((t) => t.text).join("")).toContain("<script>x</script>");
  });

  it("스킴 없는 도메인은 링크가 아니다 — 오탐이 늘면 화이트리스트가 무의미해진다", () => {
    expect(tokenizeMessage("www.example.com 참고", NAMES).some((t) => t.kind === "link")).toBe(false);
  });

  it("문장 끝 마침표·괄호는 주소에서 뺀다", () => {
    const [link] = tokenizeMessage("여기 https://a.example/b. 확인", NAMES).filter((t) => t.kind === "link");
    expect(link.text).toBe("https://a.example/b");
    const [inParen] = tokenizeMessage("(https://a.example/b) 참고", NAMES).filter((t) => t.kind === "link");
    expect(inParen.text).toBe("https://a.example/b");
  });

  it("주소 안의 균형 잡힌 괄호는 그대로 둔다", () => {
    const [link] = tokenizeMessage("https://ko.example/wiki/A_(B) 참고", NAMES).filter((t) => t.kind === "link");
    expect(link.text).toBe("https://ko.example/wiki/A_(B)");
  });

  it("한 줄에 여러 주소가 있어도 각각 잡는다", () => {
    const links = tokenizeMessage("https://a.example 와 https://b.example", NAMES).filter((t) => t.kind === "link");
    expect(links.map((l) => l.href)).toEqual(["https://a.example/", "https://b.example/"]);
  });

  it("링크에 붙일 rel/target 은 모듈이 소유한다 — 호출부가 빠뜨릴 수 없게", () => {
    expect(LINK_REL).toBe("noopener noreferrer");
    expect(LINK_TARGET).toBe("_blank");
  });
});

// ── 3. 토큰화: 멘션(서버 규칙과 같아야 한다) ────────────────────────────────

describe("tokenizeMessage — @멘션", () => {
  it("아는 이름만 멘션 조각이 된다", () => {
    const tokens = tokenizeMessage("@홍길동 확인 부탁", NAMES);
    expect(tokens[0]).toEqual({ kind: "mention", text: "@홍길동", name: "홍길동" });
  });

  it("최장 일치 — '김철'이 '김철수'를 잘라먹지 않는다", () => {
    expect(tokenizeMessage("@김철수 봐요", NAMES)[0].name).toBe("김철수");
    expect(tokenizeMessage("@김철 봐요", NAMES)[0].name).toBe("김철");
  });

  it("모르는 이름은 멘션이 아니다 — 알림이 안 갔는데 밑줄이 있으면 거짓말이다", () => {
    expect(tokenizeMessage("@없는사람 확인", NAMES).some((t) => t.kind === "mention")).toBe(false);
    expect(tokenizeMessage("@홍길 확인", NAMES).some((t) => t.kind === "mention")).toBe(false);
  });

  it("이메일 속 @는 멘션이 아니다", () => {
    const tokens = tokenizeMessage("문의는 Ann@goodmit.co.kr 로", ["goodmit", ...NAMES]);
    expect(tokens.some((t) => t.kind === "mention")).toBe(false);
  });

  it("아는 이름 목록이 비면 멘션 조각을 만들지 않는다", () => {
    expect(tokenizeMessage("@홍길동 확인", []).every((t) => t.kind === "text")).toBe(true);
  });

  it("멘션과 링크가 한 줄에 섞여도 각각 잡고 글자는 보존한다", () => {
    const src = "@홍길동 https://a.example/x 봐주세요";
    const tokens = tokenizeMessage(src, NAMES);
    expect(tokens.map((t) => t.kind)).toEqual(["mention", "text", "link", "text"]);
    expect(tokens.map((t) => t.text).join("")).toBe(src);
  });

  it("빈 본문·비문자열은 빈 배열이다", () => {
    expect(tokenizeMessage("", NAMES)).toEqual([]);
    expect(tokenizeMessage(null, NAMES)).toEqual([]);
    expect(tokenizeMessage(undefined, NAMES)).toEqual([]);
  });
});

// ── 4. 부를 수 있는 이름의 출처 ─────────────────────────────────────────────

describe("mentionNames — 서버와 같은 출처를 본다", () => {
  const members = [{ user_id: "u1", name: "나" }, { user_id: "u2", name: "너" }];
  const directory = [{ user_id: "u1", display_name: "나" }, { user_id: "u9", display_name: "전사멤버" }];

  it("일반 방은 참여자, 전체 채팅은 디렉터리를 쓴다", () => {
    expect(mentionNames({ isGlobal: false, members, directory, meId: "u1" })).toEqual(["너"]);
    expect(mentionNames({ isGlobal: true, members, directory, meId: "u1" })).toEqual(["전사멤버"]);
  });

  it("meId를 주면 그 사람만 빠진다 — 고르기 버튼용(자기 멘션은 알림이 안 간다)", () => {
    expect(mentionNames({ isGlobal: false, members, meId: "u1" })).not.toContain("나");
  });

  it("meId가 없으면 아무도 빠지지 않는다 — 말풍선 렌더용(남이 나를 부른 말도 강조돼야 한다)", () => {
    expect(mentionNames({ isGlobal: false, members })).toEqual(["나", "너"]);
  });

  it("동명이인은 통째로 빠진다 — 누가 받는지 모르는 멘션을 만들지 않는다", () => {
    const dup = [{ user_id: "a", name: "같은이름" }, { user_id: "b", name: "같은이름" }, { user_id: "c", name: "다른이름" }];
    expect(mentionNames({ isGlobal: false, members: dup, meId: "z" })).toEqual(["다른이름"]);
  });

  it("값이 없어도 빈 배열이다(첫 렌더에서 터지지 않는다)", () => {
    expect(mentionNames({ isGlobal: false })).toEqual([]);
    expect(mentionNames({ isGlobal: true })).toEqual([]);
  });
});
