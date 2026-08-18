import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import { FormModal, ToastProvider, ConfirmProvider } from "./kit.jsx";
import { REGISTRY } from "../screens/registry.js";

/* 조건에 맞지 않는 입력 칸을 그리지 않는다 (사용자 지적 #15).
 *
 * 사용자가 본 것: AI 쿼터의 '상한 추가' 에서 범위를 **'전체'** 로 골라도
 * "범위가 '사용자'일 때만 필요합니다" 라고 적힌 사용자 ID 칸이 계속 떠 있었다.
 * 도움말은 조건을 말하는데 **화면이 그 조건을 모르는** 상태였다 — 폼 스키마에 조건부
 * 장치가 아예 없었기 때문이다.
 *
 * `showIf` 는 세 가지를 함께 해야 한다. 하나만 빠져도 더 나쁜 결함이 된다:
 *   · 안 그린다        — 안 그러면 사용자가 "필요 없다면서 왜 있지" 를 묻는다
 *   · 검증하지 않는다   — 안 그러면 **보이지 않는 칸이 필수**가 되어 저장이 막힌다
 *   · 보내지 않는다     — 안 그러면 서버가 지워진 값을 받는다
 */

function wrap(ui) {
  return (
    <ToastProvider>
      <ConfirmProvider>{ui}</ConfirmProvider>
    </ToastProvider>
  );
}

const FIELDS = [
  { name: "scope_type", label: "범위", type: "select", value: "global", required: true,
    options: [{ value: "global", label: "전체" }, { value: "user", label: "사용자" }] },
  { name: "user_id", label: "사용자 ID", type: "text", required: true,
    showIf: (v) => v.scope_type === "user" },
  { name: "max_calls", label: "상한", type: "number", value: 10, required: true },
];

describe("조건부 폼 필드", () => {
  it("조건이 거짓이면 그리지 않는다", () => {
    render(wrap(<FormModal open title="상한 추가" fields={FIELDS} onSubmit={vi.fn()} onClose={vi.fn()} />));
    expect(screen.queryByLabelText(/사용자 ID/)).toBeNull();
    expect(screen.getByLabelText(/범위/)).toBeInTheDocument();
  });

  it("조건이 참이면 나타난다", async () => {
    /* MUI select 의 내부 구현에 기대지 않으려고 초기값으로 조건을 만든다 —
       여기서 보려는 것은 "조건이 참일 때 그린다" 이지 select 위젯의 동작이 아니다. */
    render(wrap(
      <FormModal open title="상한 추가" fields={FIELDS} initial={{ scope_type: "user" }}
                 onSubmit={vi.fn()} onClose={vi.fn()} />,
    ));
    await waitFor(() => expect(screen.getByLabelText(/사용자 ID/)).toBeInTheDocument());
  });

  it("숨겨진 필수 칸이 저장을 막지 않는다", async () => {
    /* 🔴 여기가 가장 중요하다 — 안 그리면서 검증하면 사용자는 **원인을 볼 수 없는 오류**를
       만난다("필수 항목입니다" 인데 그 칸이 화면에 없다). */
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(wrap(<FormModal open title="상한 추가" fields={FIELDS} onSubmit={onSubmit} onClose={vi.fn()} />));
    await user.click(screen.getByRole("button", { name: /저장/ }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(Object.keys(onSubmit.mock.calls[0][0])).not.toContain("user_id");
  });
});

describe("AI 쿼터 화면의 계약", () => {
  it("사용자 ID 칸에 조건이 실제로 걸려 있다", () => {
    /* 부품에 장치만 만들고 화면에 안 걸면 아무 일도 안 일어난다
       (X4 에서 겪었다 — 순수 함수 테스트는 배선을 증명하지 않는다). */
    const field = REGISTRY["ai-quotas"].create.fields.find((f) => f.name === "user_id");
    expect(field, "AI 쿼터 생성 폼에 user_id 가 없다").toBeTruthy();
    expect(typeof field.showIf).toBe("function");
    expect(field.showIf({ scope_type: "global" })).toBe(false);
    expect(field.showIf({ scope_type: "user" })).toBe(true);
  });

  it("도움말이 더는 거짓말하지 않는다", () => {
    /* X11 로 채팅에 상한을 건 뒤 "채팅 전송처럼 자주 일어나는 경로에는 걸지 않습니다" 가
       거짓이 됐는데 문구가 그대로 남아 있었다. 한 곳을 고치면 그 근거를 인용한 문구도
       함께 고쳐야 한다(계획서 규칙 ⑩). */
    const help = REGISTRY["ai-quotas"].help;
    expect(help).not.toMatch(/채팅 전송처럼/);
    expect(help).not.toMatch(/두 곳입니다/);
  });
});

/* 🔴 훅 순서 — **닫힘 → 열림** 을 실제로 겪게 한다.
 *
 * `showIf` 를 넣으면서 `shownFields` 의 `useMemo` 를 `if (!open) return null` **아래**에
 * 뒀었다. 그러면 닫힌 렌더는 훅 11개, 열린 렌더는 12개라 리액트가
 * "Rendered more hooks than during the previous render." 로 **트리를 통째로 버린다** —
 * 관리자 화면의 '추가'·'수정'을 누르는 순간 화면이 죽는다.
 *
 * 이 파일의 다른 테스트가 못 잡은 이유는 전부 `open` 인 채로만 렌더하기 때문이다.
 * 실제 앱은 **마운트해 두고 열고 닫는다.** 그 차이가 이 결함의 전부였다.
 */
describe("모달을 열고 닫아도 훅 순서가 유지된다", () => {
  it("닫힌 상태로 마운트한 뒤 열어도 죽지 않는다", async () => {
    const fields = [
      { name: "scope_type", label: "범위", type: "select",
        options: [{ value: "org", label: "전체" }, { value: "user", label: "사용자" }] },
      { name: "user_id", label: "사용자 ID", showIf: (v) => v.scope_type === "user" },
    ];
    const { rerender } = render(
      wrap(<FormModal open={false} title="시험" fields={fields} onSubmit={vi.fn()} onClose={vi.fn()} />),
    );
    rerender(
      wrap(<FormModal open title="시험" fields={fields} onSubmit={vi.fn()} onClose={vi.fn()} />),
    );
    // 훅 순서가 깨지면 리액트가 트리를 버려서 제목조차 안 나온다.
    expect(await screen.findByText("시험")).toBeInTheDocument();
  });
});
