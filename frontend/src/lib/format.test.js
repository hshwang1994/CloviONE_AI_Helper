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
import { fmtDayLongKo, fmtListStamp, fmtRelative, fmtTimeShort, uaSummary } from "./format.js";

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

/* 화면 머리의 하루 이름. **요일이 밀리지 않는가**가 이 함수의 전부다 — 지역 시간으로
   만들면 브라우저 시간대에 따라 서버가 「오늘」이라고 준 날의 요일이 달라진다. */
describe("fmtDayLongKo", () => {
  it("해와 달과 날과 요일을 함께 말한다", () => {
    expect(fmtDayLongKo("2026-09-07")).toBe("2026년 9월 7일 월요일");
    expect(fmtDayLongKo("2026-01-01")).toBe("2026년 1월 1일 목요일");
    expect(fmtDayLongKo("2026-09-06")).toBe("2026년 9월 6일 일요일");
  });

  it("시각이 붙어 와도 날짜만 읽는다", () => {
    expect(fmtDayLongKo("2026-09-07T23:59:59Z")).toBe("2026년 9월 7일 월요일");
  });

  it("모르는 값은 지어내지 않는다", () => {
    expect(fmtDayLongKo(null)).toBe("");
    expect(fmtDayLongKo("")).toBe("");
    expect(fmtDayLongKo("어제")).toBe("어제");
  });
});

describe("fmtListStamp — 목록 행 시각(이레 안은 상대, 그 뒤는 짧은 달력일)", () => {
  afterEach(() => { vi.useRealTimers(); });

  it("이레 안은 상대 시간 형식기와 같은 말을 한다", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-15T03:00:00Z"));
    expect(fmtListStamp("2026-09-15T02:59:40")).toBe("방금 전");
    expect(fmtListStamp("2026-09-15T01:00:00")).toBe("2시간 전");
    expect(fmtListStamp("2026-09-12T03:00:00")).toBe("3일 전");
    expect(fmtListStamp("2026-09-12T03:00:00")).toBe(fmtRelative("2026-09-12T03:00:00"));
  });

  it("이레가 넘으면 「M월 D일」(KST 달력일)이고 긴 절대 시각이 아니다", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-15T03:00:00Z"));
    // UTC 8월 24일 15:30 은 KST 8월 25일 00:30 이다 — 달력일은 KST 로 잰다.
    expect(fmtListStamp("2026-08-24T15:30:00")).toBe("8월 25일");
    expect(fmtListStamp("2026-08-24T03:00:00")).toBe("8월 24일");
    expect(fmtListStamp("2026-08-24T03:00:00")).not.toMatch(/오전|오후|\d{4}\./);
  });

  it("해가 다르면 해를 붙인다", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-10T03:00:00Z"));
    expect(fmtListStamp("2025-12-20T03:00:00")).toBe("2025년 12월 20일");
  });

  it("미래 값과 못 읽는 값은 상대 시간 형식기 규칙 그대로다", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-15T03:00:00Z"));
    expect(fmtListStamp("2026-09-20T03:00:00")).toBe(fmtRelative("2026-09-20T03:00:00"));
    expect(fmtListStamp("")).toBe("-");
  });
});

/* 내 기기 · 사용자 세션의 「기기/브라우저」 — 원문 대신 브라우저와 운영체제 한 줄(r23 28). 순서가 뜻이다: Edge 는 Chrome 도, iPhone 은
   Mac OS X 도 적는다. 모르는 모양은 첫 제품 토큰, 그것도 없으면 잘린 원문이다. */
describe("uaSummary", () => {
  it("흔한 브라우저와 운영체제를 한 줄로 말한다", () => {
    expect(uaSummary("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"))
      .toBe("Chrome 128, Windows");
    expect(uaSummary("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"))
      .toBe("Edge 141, Windows");
    expect(uaSummary("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"))
      .toBe("Safari 17, iOS");
    expect(uaSummary("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0")).toBe("Firefox 131, Linux");
    expect(uaSummary("Mozilla/5.0 (Linux; Android 14; SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36"))
      .toBe("삼성 인터넷 26, Android");
  });

  it("모르는 모양은 첫 제품 토큰, 비었으면 「-」다", () => {
    expect(uaSummary("python-httpx/0.28.1")).toBe("python-httpx 0.28.1");
    expect(uaSummary("")).toBe("-");
    expect(uaSummary(null)).toBe("-");
  });
});
