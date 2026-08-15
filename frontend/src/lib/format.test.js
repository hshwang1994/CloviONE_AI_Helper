/* format.js::fmtTimeShort — 채팅 말풍선 시각이 실행 환경 로컬 시간대와 무관하게 항상
 * KST로 나오는가 (whole-product 재감사, 2026-08-15).
 *
 * 이 파일은 지금까지 직접 테스트가 없었다(수십 개 화면이 간접적으로 가져다 쓸 뿐).
 * fmtTimeShort는 한동안 `d.toLocaleTimeString("ko-KR", {hour,minute})`처럼 timeZone
 * 옵션 없이 호출해, 실행 환경(뷰어의 브라우저/OS)의 로컬 시간대로 시각이 나갔다 — 개발
 * 서버·CI가 우연히 KST면 안 보이고, KST가 아닌 뷰어(VPN·해외 출장·시계 오설정)에게만
 * 몇 시간 밀린 시각이 보이는 결함이었다(불변규칙 §3-7: 표시는 항상 Asia/Seoul).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fmtTimeShort } from "./format.js";

describe("fmtTimeShort — 항상 KST(UTC+9)로 표시한다", () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  it("빈 값/파싱 불가 문자열은 빈 문자열", () => {
    expect(fmtTimeShort(null)).toBe("");
    expect(fmtTimeShort(undefined)).toBe("");
    expect(fmtTimeShort("")).toBe("");
    expect(fmtTimeShort("이건-날짜가-아니다")).toBe("");
  });

  it("실행 환경의 로컬 시간대가 KST가 아니어도 KST로 나온다", () => {
    // 개발 서버·CI가 우연히 KST면 결함이 안 보인다 — 실행기 시간대를 명시적으로 다른 값으로
    // 고정해 놓고도 KST가 나오는지 직접 본다(timeUtils.test.js::fmtTime과 같은 방법).
    vi.stubEnv("TZ", "America/Los_Angeles");
    // 백엔드는 naive UTC를 준다 — "Z"가 없으면 이 함수가 UTC로 해석한다(toUTCDate).
    // UTC 05:30 == KST(UTC+9) 14:30 == 오후 2:30(ko-KR 기본 12시간제).
    const out = fmtTimeShort("2026-07-29T05:30:00");
    expect(out).toMatch(/오후\s*0?2:30/);
    // LA(2026-07 기준 UTC-7)로 새면 이 값과 달라야 한다.
    const misparsedAsLA = new Date("2026-07-29T05:30:00Z")
      .toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
    expect(out).not.toBe(misparsedAsLA);
  });

  it("이미 오프셋이 붙은 값도 같은 순간이면 같은 KST 시각을 낸다", () => {
    // +09:00 14:30 == UTC 05:30 — toUTCDate가 오프셋을 존중하므로 위 시험과 같은 순간이어야 한다.
    expect(fmtTimeShort("2026-07-29T14:30:00+09:00")).toBe(fmtTimeShort("2026-07-29T05:30:00Z"));
  });
});
