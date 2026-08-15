import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { personField } from "./registry/shared.js";
import { REGISTRY } from "./registry.js";

/* 관리자 상세 패널의 식별자 표기 (E-4 "UUID 노출 30여 곳").
 *
 * 두 방향을 **함께** 지킨다. 한쪽만 보면 매번 반대쪽이 깨진다.
 *
 *   ① 사람 자리는 이름을 앞에 세운다 — `9f2c…-…` 를 보고 누구인지 알 수 없었다.
 *   ② 그렇다고 id 를 지우지 않는다 — 지원팀이 물어보는 값이고, 다른 화면의 폼이
 *      "이 화면에서 ID를 확인해 입력하세요" 라고 문자로 지시한다. 지우면 그 폼을 채울
 *      방법이 사라진다.
 */

const UUID = "9f2c1d4e-0000-4aaa-9bbb-1c2d3e4f5a6b";

function renderField(spec, row) {
  return render(<div>{spec.render(row)}</div>);
}

describe("personField", () => {
  it("이름이 있으면 이름을 앞에 세운다", () => {
    const spec = personField("owner_user_id", "소유자", "owner_name", "owner_email");
    renderField(spec, { owner_user_id: UUID, owner_name: "김운영", owner_email: "op@goodmit.co.kr" });
    expect(screen.getByText("김운영")).toBeInTheDocument();
  });

  it("이름을 보여 주면서도 id 를 지우지 않는다", () => {
    const spec = personField("owner_user_id", "소유자", "owner_name", "owner_email");
    const { container } = renderField(spec, {
      owner_user_id: UUID, owner_name: "김운영", owner_email: "op@goodmit.co.kr",
    });
    // 동명이인일 때 id 가 유일한 구분자다. 그리고 감사 로그 필터에 붙여 넣는 값이다.
    expect(container.textContent).toContain(UUID);
  });

  it("서버가 이름을 안 주면 id 라도 보여 준다 — 침묵하지 않는다", () => {
    const spec = personField("owner_user_id", "소유자", "owner_name", "owner_email");
    const { container } = renderField(spec, { owner_user_id: UUID });
    expect(container.textContent).toContain(UUID);
  });

  it("사람이 아예 없는 실행은 그렇다고 말한다 — 없는 사람을 지어내지 않는다", () => {
    const spec = personField("created_by", "실행한 사람", "created_by_name", "created_by_email");
    renderField(spec, { created_by: null });
    expect(screen.getByText(/자동 실행/)).toBeInTheDocument();
  });
});

describe("사람 자리에 남은 원시 UUID", () => {
  it("스케줄 소유자와 백업 실행자는 이름으로 바뀌었다", () => {
    const owner = REGISTRY.schedules.detailFields.find((f) => f.key === "owner_user_id");
    const creator = REGISTRY.backup.detailFields.find((f) => f.key === "created_by");
    // render 가 없으면 DataScreen 이 원시 값을 String() 으로 그대로 그린다 = UUID 노출.
    expect(typeof owner.render).toBe("function");
    expect(typeof creator.render).toBe("function");
  });

  it("승인 요청자도 상세에서 이름으로 읽힌다", () => {
    // 상세는 **결재하기 직전에 보는 화면**이다. 거기서 누구인지 못 읽으면 목록으로 돌아가야 한다.
    const requester = REGISTRY.approvals.detailFields.find((f) => f.key === "requested_by");
    expect(typeof requester.render).toBe("function");
    const { container } = renderField(requester, {
      requested_by: UUID, requester_name: "박승인", requester_email: "ap@goodmit.co.kr",
    });
    expect(container.textContent).toContain("박승인");
  });
});

describe("RG-07 — 서버가 이름을 이미 주는데 화면만 raw UUID를 그리던 곳", () => {
  it("문서 생성 목록의 요청자가 이름으로 읽힌다", () => {
    const requester = REGISTRY.documents.columns.find((f) => f.key === "requested_by");
    expect(requester, "documents 목록에 requested_by 열이 없다").toBeTruthy();
    expect(typeof requester.render).toBe("function");
    const { container } = renderField(requester, {
      requested_by: UUID, requested_by_name: "정요청", requested_by_email: "rq@goodmit.co.kr",
    });
    expect(container.textContent).toContain("정요청");
  });

  it("워크플로 버전 기록의 변경자가 이름으로 읽힌다(연동·러너는 서버가 이름을 안 줘서 그대로 둔다)", () => {
    const versionsOf = (key) => {
      const action = REGISTRY[key].actions.find((a) => a.label === "버전 기록");
      return action.subList.columns.find((c) => c.key === "created_by");
    };
    const workflowCreator = versionsOf("workflows");
    expect(typeof workflowCreator.render, "워크플로 버전 기록의 변경자에 render가 없다").toBe("function");
    const { container } = renderField(workflowCreator, {
      created_by: UUID, created_by_name: "최변경", created_by_email: "ch@goodmit.co.kr",
    });
    expect(container.textContent).toContain("최변경");

    // 대조군 — 서버가 정말 이름을 안 주는 두 화면은 raw id 그대로다(위 render 없음이 곧 그 뜻).
    expect(versionsOf("integrations").render).toBeUndefined();
    expect(versionsOf("runners").render).toBeUndefined();
  });
});

describe("VIS-11/DS-23 — 화면 간 참조 ID 링크가 브라우저 기본 스타일로 새고 있었다", () => {
  // DS-23이 columnHelpers.jsx의 공용 헬퍼(linkCol 등)는 이미 MUI Link로 고쳤지만, registry
  // 화면 자신의 render에서 손으로 React.createElement("a", ...)를 쓰던 13곳(automation.js·
  // authoring.js·integrations.js)은 그 수정이 안 닿았다 — 대상 이름보다 raw ID가 브라우저
  // 기본 파란/보라 밑줄로 더 강조되는 것이 VIS-11이 지목한 증상이었다. 여기서는 그중 대표로
  // 템플릿 상세의 prompt_id/policy_id 딥링크가 실제로 MUI Link(밑줄은 hover 시에만, 새 탭
  // 안 열림 — 앱 안 이동이므로 target="_blank" 는 오히려 잘못된 동작이다)로 렌더되는지 확인한다.
  it("템플릿 상세의 prompt_id 링크가 MUI Link로 렌더된다(밑줄 hover, 새 탭 아님)", () => {
    const field = REGISTRY.templates.detailFields.find((f) => f.key === "prompt_id");
    expect(typeof field.render).toBe("function");
    renderField(field, { prompt_id: "pr-123" });
    const link = screen.getByRole("link", { name: "pr-123" });
    expect(link).toHaveAttribute("href", "#/prompts?id=pr-123");
    expect(link).not.toHaveAttribute("target");
    expect(link.className).toMatch(/MuiLink/);
  });

  it("템플릿 상세의 policy_id 링크도 같다", () => {
    const field = REGISTRY.templates.detailFields.find((f) => f.key === "policy_id");
    renderField(field, { policy_id: "pol-9" });
    const link = screen.getByRole("link", { name: "pol-9" });
    expect(link).toHaveAttribute("href", "#/policies?id=pol-9");
    expect(link.className).toMatch(/MuiLink/);
  });
});

describe("일부러 남긴 식별자", () => {
  it("작업 큐의 요청자는 id 로 남는다 — 서버가 이름을 일부러 안 싣는다", () => {
    // app/jobs/router.py `_job_view` 가 요청자 이메일/이름을 응답에서 뺀다(큐 화면이
    // 대화 내용 열람의 우회로가 되지 않게). 여기에 이름을 그리려면 그 원칙부터 다시 정해야 한다.
    const requester = REGISTRY.jobs.detailFields.find((f) => f.key === "user_id");
    expect(requester).toBeTruthy();
    expect(requester.render).toBeUndefined();
    // 라벨이 '요청자' 로만 끝나면 사람 이름 자리로 읽힌다 — 계정 ID 라고 분명히 말한다.
    expect(requester.label).toContain("ID");
  });

  it("감사 로그의 문의 번호와 기록 ID 는 그대로 남는다 — 지원팀이 물어보는 값이다", () => {
    const keys = REGISTRY.audit.detailFields.map((f) => f.key);
    expect(keys).toContain("request_id");
    expect(keys).toContain("id");
  });
});
