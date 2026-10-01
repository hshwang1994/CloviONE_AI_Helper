import React from "react";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

/* qa-contract-change: 메일 비밀번호가 서버 파일 이름(`password_ref`) 칸에서 비밀 저장 칸(`SecretField`, 계획 2.3 · D-511)으로
 * 바뀌었다. 「비밀번호를 받는 칸이 없다」 단언을 「비밀번호 칸의 값은 설정 JSON 이 아니라 비밀 저장 API 로만 간다」로 옮기고,
 * 서버 인증서 확인과 사설 CA 칸의 단언을 더했다.
 * qa-contract-change: 비밀번호를 읽는 칸이 하나로 고정됐다(D-545). 「저장하면 옛 파일 이름을 비운다」 단언을
 * 「설정 JSON 에 칸 이름을 적지 않는다」로 옮긴다. */
const apiMock = vi.fn();
vi.mock("../../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

/* H-2 회귀 고정: fmtDuration import 누락으로 '세션 정책' 편집기가 ReferenceError로
 * 크래시했다(ErrorBoundary가 화면 전체를 오류로 덮었다) — StructuredObjectFields.jsx가
 * 같은 디렉터리에 export된 fmtDuration을 import하지 않았다. 이 테스트는 렌더가 던지지
 * 않는 것과, 초 단위 값이 사람이 읽는 시간으로 옆에 나오는 것 둘 다 고정한다.
 */
import { StructuredObjectFields } from "./StructuredObjectFields.jsx";

function renderField(settingKey, val, extra = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiMock.mockImplementation((path) => (String(path) === "/api/admin/secrets"
    ? Promise.resolve({ items: [{ name: "smtp.password", label: "메일 서버 비밀번호", stored: false }] })
    : Promise.resolve({ ok: true })));
  return render(
    <QueryClientProvider client={qc}>
      <StructuredObjectFields
        settingKey={settingKey}
        val={val}
        onChange={() => {}}
        canWrite={true}
        describedBy={undefined}
        invalid={false}
        {...extra}
      />
    </QueryClientProvider>,
  );
}

describe("StructuredObjectFields — session_policy", () => {
  it("크래시 없이 렌더되고 fmtDuration으로 값을 사람이 읽는 단위로 보여준다", () => {
    const val = JSON.stringify({ idle_timeout_seconds: 1800, absolute_timeout_seconds: 28800 });
    renderField("session_policy", val);
    expect(screen.getByText("= 30분")).toBeInTheDocument();
    expect(screen.getByText("= 8시간")).toBeInTheDocument();
  });
});

// SONNET_HANDOFF §5 완료 기준: STRUCTURED_OBJECT_KEYS 4개를 각각 렌더하는 스모크 테스트
// (이 화면군에 렌더 테스트가 0개였다). session_policy는 위에서 이미 다뤘으니 나머지 셋.
describe("StructuredObjectFields — 나머지 STRUCTURED_OBJECT_KEYS 3종 (스모크)", () => {
  it("password_policy: 크래시 없이 렌더되고 저장된 값을 보여준다", () => {
    renderField("password_policy", JSON.stringify({ min_length: 12, min_classes: 3 }));
    expect(screen.getByLabelText("최소 글자 수(8~128자)")).toHaveValue(12);
    expect(screen.getByLabelText("문자 종류 수(1~4)")).toHaveValue(3);
  });

  it("allowed_email_domains: 도메인이 있으면 칩으로, 비어 있으면 빈 상태 문구를 보여준다", () => {
    const { unmount } = renderField("allowed_email_domains", JSON.stringify(["goodmit.co.kr"]));
    expect(screen.getByText("goodmit.co.kr")).toBeInTheDocument();
    unmount();
    renderField("allowed_email_domains", JSON.stringify([]));
    expect(screen.getByText("제한 없음(모든 이메일 도메인 허용)")).toBeInTheDocument();
  });

  it("ui_branding: 크래시 없이 렌더되고 저장된 값을 보여준다", () => {
    renderField("ui_branding", JSON.stringify({ product_name: "ClovirAssist", support_email: "help@goodmit.co.kr" }));
    expect(screen.getByLabelText("제품명")).toHaveValue("ClovirAssist");
    expect(screen.getByLabelText("지원 이메일")).toHaveValue("help@goodmit.co.kr");
  });

  it("파싱 실패(잘못된 JSON)에도 크래시하지 않고 빈 값으로 안전 폴백한다", () => {
    // advanced(raw JSON) 모드에서 편집 중일 때 이 컴포넌트가 잠깐 유효하지 않은 val을 받을 수
    // 있다 - obj=null 폴백(safe={})이 실제로 렌더를 막지 않는지 네 타입 전부에서 확인한다.
    for (const key of ["password_policy", "session_policy", "ui_branding"]) {
      const { unmount } = renderField(key, "{ not valid json");
      unmount();
    }
    renderField("allowed_email_domains", "{ not valid json");
    expect(screen.getByText("제한 없음(모든 이메일 도메인 허용)")).toBeInTheDocument();
  });
});

/* 지시 32 · 36: 메일 설정은 이 저장소에서 마지막까지 raw JSON 편집으로 남아 있었다.
 * 관리자가 중괄호를 손으로 맞추고 `security` 의 허용값을 힌트 문장에서 읽어야 하는 상태가
 * "설정 화면"일 수는 없다. 여기서 고정하는 것은 셋이다.
 *   1) 필드마다 사람이 읽는 이름이 있다.
 *   2) 값의 어휘(`starttls`)가 아니라 이름으로 고른다.
 *   3) **비밀번호는 설정 JSON 에 들어가지 않는다** — 비밀번호 칸은 비밀 저장 API 로만 간다(D-511).
 */
describe("StructuredObjectFields — smtp (지시 32 · 36)", () => {
  const SMTP = JSON.stringify({
    enabled: true, host: "smtp.internal", port: 587, security: "starttls",
    from_address: "portal@goodmit.co.kr", from_name: "ClovirAssist",
    username: "mailer", timeout_seconds: 20,
  });

  it("필드마다 이름이 붙은 입력으로 렌더되고 저장된 값을 보여준다", () => {
    renderField("smtp", SMTP);
    expect(screen.getByLabelText("메일 서버 주소")).toHaveValue("smtp.internal");
    expect(screen.getByLabelText("포트(1~65535)")).toHaveValue(587);
    expect(screen.getByLabelText("보내는 사람 주소")).toHaveValue("portal@goodmit.co.kr");
    expect(screen.getByLabelText("응답 대기 시간(초, 1~300)")).toHaveValue(20);
  });

  it("보안 연결은 값의 어휘가 아니라 이름으로 고른다", () => {
    renderField("smtp", SMTP);
    const select = screen.getByLabelText("보안 연결");
    expect(select).toHaveValue("starttls");
    const names = Array.from(select.options).map((o) => o.textContent);
    expect(names.some((n) => n.startsWith("STARTTLS"))).toBe(true);
    expect(names).toContain("사용 안 함(사내망에서만)");
  });

  it("비밀번호 칸의 값은 설정 JSON 이 아니라 비밀 저장 API 로만 간다", async () => {
    const onChange = vi.fn();
    renderField("smtp", SMTP, { onChange });
    const input = await screen.findByLabelText("로그인 비밀번호");
    expect(input).toHaveAttribute("type", "password");
    expect(screen.queryByLabelText("비밀번호 파일 이름")).toBeNull();
    fireEvent.change(input, { target: { value: "s3cret-value" } });
    // 입력만으로는 설정 값이 바뀌지 않는다 - 평문이 설정 JSON 으로 들어가는 길이 없다.
    expect(onChange.mock.calls.some(([v]) => String(v).includes("s3cret-value"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "로그인 비밀번호 저장" }));
    await waitFor(() => expect(apiMock.mock.calls.some(([p, o]) =>
      p === "/api/admin/secrets/smtp.password" && o && o.method === "PUT")).toBe(true));
    // 비밀번호를 읽는 칸은 하나로 고정이다(D-545) - 저장해도 설정 JSON 에 칸 이름을 적지 않는다.
    expect(onChange.mock.calls.some(([v]) => "password_ref" in JSON.parse(v))).toBe(false);
  });

  it("서버 인증서 확인은 기본으로 켜져 있고, 끄면 경고가 선다", () => {
    const onChange = vi.fn();
    const { rerender } = renderField("smtp", SMTP, { onChange });
    expect(screen.getByLabelText("서버 인증서 확인")).toHaveValue("true");
    expect(screen.getByLabelText("사설 CA 인증서(PEM, 선택)")).toBeInTheDocument();
    const off = JSON.stringify({ ...JSON.parse(SMTP), tls_verify: false });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={qc}>
        <StructuredObjectFields settingKey="smtp" val={off} onChange={onChange} canWrite={true} invalid={false} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/인증서를 확인하지 않으면/)).toBeInTheDocument();
  });

  it("잘못된 JSON 에도 크래시하지 않는다", () => {
    renderField("smtp", "{ not valid json");
    expect(screen.getByLabelText("메일 서버 주소")).toHaveValue("");
  });
});

/* 지시 32 · 36 — 백업 일정에서 cron 문법이 화면의 주된 인터페이스일 이유는 없다.
 * `0 3 * * *` 를 읽을 줄 아는 사람만 백업 시각을 바꿀 수 있는 상태였다.
 * 표현력은 줄이지 않는다: 못 알아보는 표현식은 지우거나 근사하지 않고 원문 그대로 둔다.
 */
describe("StructuredObjectFields — backup_schedule (지시 32 · 36)", () => {
  const daily = JSON.stringify({ enabled: true, cron: "0 3 * * *", timezone: "Asia/Seoul", keep: 14 });

  it("매일 3시는 주기 '매일' + 시각 03:00 으로 읽힌다", () => {
    renderField("backup_schedule", daily);
    expect(screen.getByLabelText("주기")).toHaveValue("daily");
    expect(screen.getByLabelText("시각")).toHaveValue("03:00");
    expect(screen.getByLabelText("남길 백업 개수(1~365)")).toHaveValue(14);
  });

  it("매주는 요일을 함께 고른다", () => {
    renderField("backup_schedule", JSON.stringify({ enabled: true, cron: "30 2 * * 0", keep: 7 }));
    expect(screen.getByLabelText("주기")).toHaveValue("weekly");
    expect(screen.getByLabelText("요일")).toHaveValue("0");
  });

  it("알아볼 수 없는 표현식은 '직접 입력'으로 떨어지고 원문이 그대로 남는다", () => {
    const odd = "*/15 9-18 * * 1-5";
    renderField("backup_schedule", JSON.stringify({ enabled: true, cron: odd, keep: 30 }));
    expect(screen.getByLabelText("주기")).toHaveValue("custom");
    expect(screen.getByLabelText("cron 표현식")).toHaveValue(odd);
  });

  it("잘못된 JSON 에도 크래시하지 않는다", () => {
    renderField("backup_schedule", "{ not valid json");
    expect(screen.getByLabelText("주기")).toBeTruthy();
  });
});

/* 🔴 **보관 기간을 고칠 칸이 없었다** (2026-09-01).
 *
 * 서버는 지울지 말지를 개수와 나이 **둘 다** 보고 정한다
 * (`app/backups/service.py::apply_retention` — 개수만 걸면 하루에 여러 번 돌린 날이 지난
 * 주를 통째로 밀어낸다). 그런데 이 편집기에는 개수 칸만 있어서, 「복구 리허설」 화면이
 * «보관 기간 7일» 이라는 카드를 보여 주는데 그 값을 바꿀 자리가 제품 어디에도 없었다.
 * 이 설정의 설명문(«정한 개수와 기간만큼 남깁니다»)은 절반이 지킬 수 없는 약속이었다.
 */
describe("StructuredObjectFields — backup_schedule 의 보관 기간", () => {
  it("저장된 keep_days 를 그 칸이 보여 준다", () => {
    renderField("backup_schedule", JSON.stringify({
      enabled: true, cron: "0 3 * * *", keep: 14, keep_days: 30,
    }));
    expect(screen.getByLabelText("보관 기간(0~365일)")).toHaveValue(30);
  });

  it("0 도 값이다 — 「개수로만 정리한다」를 고른 것이지 빈 칸이 아니다", () => {
    renderField("backup_schedule", JSON.stringify({
      enabled: true, cron: "0 3 * * *", keep: 14, keep_days: 0,
    }));
    expect(screen.getByLabelText("보관 기간(0~365일)")).toHaveValue(0);
  });

  it("칸을 고치면 keep_days 가 담긴 JSON 으로 돌려준다 — 다른 값은 그대로 둔다", () => {
    const seen = [];
    renderField(
      "backup_schedule",
      JSON.stringify({ enabled: true, cron: "0 3 * * *", keep: 14, keep_days: 7 }),
      { onChange: (v) => seen.push(JSON.parse(v)) },
    );
    fireEvent.change(screen.getByLabelText("보관 기간(0~365일)"), { target: { value: "21" } });
    expect(seen).toHaveLength(1);
    expect(seen[0].keep_days).toBe(21);
    expect(seen[0].keep).toBe(14);
    expect(seen[0].cron).toBe("0 3 * * *");
  });
});
