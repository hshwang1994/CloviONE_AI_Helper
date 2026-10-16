/* qa-contract-change: 프롬프트 화면이 기능 단위가 되어(D-541) 확인을 받는 동작이 「보관」에서 「초안 버리기 · 기본 제공으로 되돌리기」로 바뀌었고, 프롬프트 사용 통계 탭의 열 수 단언은 기능 목록의 열 수로 옮겼다. 위험 동작이 확인을 받는다는 성질은 그대로다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
/* qa-contract-change: 조직·부서·조직도가 registry 를 떠나 조직 콘솔(screens/org/)의 선택 반응형 상세 판으로 재구성됐다 — 조직 비활성화 confirm·부서 primary·조직 clientFilter·org-tree 필터 메타 단언을 org-console-actions.test.jsx 로 이관하거나 표와 함께 걷었다. */
/* qa-contract-change: S11 이 n8n·러너 서브시스템을 걷어내면서 이 파일이 고정하던 화면 셋이 사라졌다 — 문서 발행 승인 액션(document.publish), 문서 생성 화면의 clientFilter 경고, 프롬프트의 러너 ID 필드. 단언이 줄어든 만큼이 정확히 그 셋이고, 남은 단언은 한 글자도 안 약해졌다(기대값·형태 그대로). «documents 만 예외» 였던 단언은 «예외가 하나도 없다» 로 **더 세졌다**. */
/* 관리 콘솔 28화면 전수조사(9-1) — 확인·필터·문구가 실제 동작과 맞는가.
 *
 * 이 파일이 지키는 것은 세 가지다.
 *   1) 되돌릴 수 없는 일에는 확인이 **실제로 뜬다**(설정에 문구만 적혀 있는 것과 다르다 —
 *      DataScreen 이 폼 액션을 먼저 열어 버리면 confirm 은 죽은 코드가 된다).
 *   2) 거르는 조건은 서버로 가거나, 못 가면 화면이 그 한계를 **이름을 대고** 말한다.
 *   3) '비우면 …' 같은 약속은 백엔드가 실제로 그렇게 동작할 때만 남는다.
 *
 * 참고: 전수조사 메모가 지목한 것 중 실제로 결함이던 것은 일부다. 이미 맞던 것(프롬프트·정책
 * '보관' 확인, 기능 플래그 '끄기' 확인, 스케줄 필터, 조직도 '사용' 필터)도 여기서 함께 못박는다
 * — 없는 결함을 만들지 않는 것만큼, 있던 것을 되돌리지 않는 것도 이 파일의 일이다.
 */
import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "actor-1" } }),
}));

import { DataScreen } from "./DataScreen.jsx";
import { REGISTRY } from "./registry.js";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";
import { clickAction, hasAction } from "../test-helpers/actions.js";

function renderScreen(key) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <DataScreen config={REGISTRY[key]} />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>,
  );
}

/* MUI 화면 하나를 jsdom에서 그리는 데 1초 가까이 걸린다 — 파일 전체를 이어서 돌리면 기본
 * findBy 대기(1s)가 먼저 끝나 '못 찾았다'가 된다(화면 결함이 아니라 러너가 느린 것이다).
 * 대기 상한을 넉넉히 잡아, 실패했을 때 그 실패가 진짜 결함이라는 뜻이 되게 한다. */
const WAIT = { timeout: 8000 };
const findText = (text) => screen.findByText(text, {}, WAIT);

// 행 하나를 찾아 상세 드로어를 연다(표 모드 기준 — jsdom 기본 폭에서는 카드가 아니라 표다).
async function openRow(text) {
  const cell = await findText(text);
  await userEvent.click(cell.closest("tr"));
  return screen.findByRole("dialog", {}, WAIT);
}

const confirmDialog = () => screen.findByRole("dialog", { name: "확인" }, WAIT);

/* DataScreen 은 지금 걸린 필터를 주소(해시)에 적어 둔다 — 링크로 화면을 공유하기 위해서다.
 * 테스트를 이어서 돌리면 앞 화면이 남긴 해시(예: 승인의 status=pending)를 다음 화면이 자기
 * 필터로 읽어 들여, 아무 상관 없는 화면이 '검색 결과가 없습니다'가 된다(saved-views.test.jsx
 * 가 같은 이유로 해시를 초기화한다). 각 테스트를 빈 주소에서 시작시킨다. */
beforeEach(() => {
  apiMock.mockReset();
  window.location.hash = "";
});
afterEach(() => { window.location.hash = ""; });

/* ── 1. 위험한 일에는 확인을 받는다 ─────────────────────────────────────── */

describe("위험 액션 확인", () => {
  it("danger 로 칠한 액션은 예외 없이 confirm 을 갖는다", () => {
    const missing = [];
    Object.values(REGISTRY).forEach((cfg) => {
      [...(cfg.actions || []), ...(cfg.headerActions || [])].forEach((a) => {
        if (a.variant === "danger" && !a.confirm) missing.push(cfg.key + " / " + a.label);
      });
    });
    // 규칙이 화면마다 갈리면 '이 화면만 안 물어본다'가 태어난다. 한 줄도 예외를 두지 않는다.
    expect(missing).toEqual([]);
  });

  it("승인 '거절': 확인이 폼보다 먼저 뜨고, 확인 전에는 거절 요청이 나가지 않는다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") return Promise.resolve({ approval: { id: "a1", status: "rejected" } });
      return Promise.resolve({
        items: [{
          id: "a1", request_type: "user.role_change", object_type: "user", object_id: "u-9",
          requested_by: "u-2", requester_name: "홍길동", status: "pending",
          requested_at: "2026-08-01T00:00:00Z", expires_at: "2026-08-04T00:00:00Z",
          due_at: null, overdue: false, can_decide: true, request_payload: { role: "admin" },
        }],
        total: 1, page: 1, page_size: 20,
      });
    });
    renderScreen("approvals");
    const drawer = await openRow("홍길동");
    await clickAction(userEvent, drawer, "거절");

    // 확인이 먼저. 이 시점에 폼도, 거절 요청도 있어서는 안 된다.
    const dlg = await confirmDialog();
    expect(dlg).toHaveTextContent(/되돌릴 수 없습니다/);
    expect(apiMock.mock.calls.some(([p]) => String(p).includes("/reject"))).toBe(false);
    expect(screen.queryByLabelText(/거절 사유/)).not.toBeInTheDocument();

    await userEvent.click(within(dlg).getByRole("button", { name: "거절" }));

    // 확인을 지나야 사유 폼이 열리고, 그 폼을 제출해야 비로소 요청이 나간다.
    const form = await screen.findByLabelText(/거절 사유/, {}, WAIT);
    expect(apiMock.mock.calls.some(([p]) => String(p).includes("/reject"))).toBe(false);
    await userEvent.type(form, "권한이 과합니다");
    await userEvent.click(within(form.closest("[role=dialog]")).getByRole("button", { name: /저장|거절/ }));
    await waitFor(() =>
      expect(apiMock.mock.calls.some(([p]) => String(p).includes("/api/admin/approvals/a1/reject"))).toBe(true), WAIT);
  });

  it("승인/거절 버튼은 role이 아니라 서버가 준 can_decide로 켜진다 (FN-11 위임 지원)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{
        id: "a1", request_type: "user.role_change", object_type: "user", object_id: "u-9",
        requested_by: "u-2", requester_name: "홍길동", status: "pending",
        requested_at: "2026-08-01T00:00:00Z", expires_at: "2026-08-04T00:00:00Z",
        due_at: null, overdue: false, can_decide: false, request_payload: { role: "admin" },
      }],
      total: 1, page: 1, page_size: 20,
    }));
    renderScreen("approvals");
    const drawer = await openRow("홍길동");
    // 이 화면을 그린 mock role은 system_admin(WRITE_ROLES 안)이지만 can_decide:false라
    // 버튼이 없어야 한다 — role만 보고 켜던 예전 방식으로 되돌아가면 이 시험이 깨진다.
    expect(within(drawer).queryByRole("button", { name: "승인" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "거절" })).not.toBeInTheDocument();
  });


  it("이미 확인을 받고 있던 액션은 그대로 남아 있다(있던 것을 되돌리지 않는다)", () => {
    const confirmOf = (key, label) =>
      (REGISTRY[key].actions || []).find((a) => a.label === label && a.confirm);
    // 프롬프트는 기능 단위가 됐다(D-541) - 지시문을 쓰지 않게 되는 두 동작(초안 버리기 · 기본 제공으로 되돌리기)이 확인을 받는다.
    expect(confirmOf("prompts", "초안 버리기")).toBeTruthy();
    expect(confirmOf("prompts", "기본 제공으로 되돌리기")).toBeTruthy();
    expect(confirmOf("policies", "보관")).toBeTruthy();
    expect(confirmOf("feature-flags", "비활성화")).toBeTruthy();
  });

  it("공지 배너 '중요도'는 서버 요청에 실려 나간다(페이지 안에서만 거르지 않는다)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }));
    renderScreen("announcements");
    await findText("등록된 공지 배너가 없습니다.");

    await userEvent.click(screen.getByRole("combobox", { name: /중요도/ }));
    await userEvent.click(await screen.findByRole("option", { name: "긴급" }, WAIT));
    await waitFor(() =>
      expect(apiMock.mock.calls.some(([p]) => String(p).includes("level=critical"))).toBe(true), WAIT);
  });


  it("clientFilter 를 쓰는 화면 중 paginated 는 하나도 없다", () => {
    // paginated + clientFilter 는 '다른 페이지의 일치 항목이 사라지는' 조합이다. 유일한
    // 예외였던 documents(서버가 mode 를 안 받았다)는 S11 이 그 화면과 함께 걷어냈다.
    const offenders = Object.values(REGISTRY)
      .filter((c) => c.paginated && (c.filters || []).some((f) => f.clientFilter))
      .map((c) => c.key);
    expect(offenders).toEqual([]);
  });

  it("스케줄과 조직도는 결함이 아니었다 — 그 상태를 못박는다", () => {
    // 스케줄: 백엔드가 파라미터를 안 받지만 페이지네이션도 없다 → 받아 온 것이 곧 전부다.
    expect(REGISTRY.schedules.paginated).toBeFalsy();
    expect((REGISTRY.schedules.filters || []).length).toBeGreaterThan(0);
    // (조직도의 '사용' 필터는 콘솔 재구성 후 org-console.test.jsx 가 서버 질의로 직접 확인한다.)
  });
});

/* ── 3. 필터가 하나도 없던 화면 ─────────────────────────────────────────── */

describe("좁혀 볼 수단", () => {
  it("전수조사가 지목한 화면에 좁힐 수단이 생겼다", () => {
    ["backup", "ai-quotas", "restore-drills"].forEach((key) => {
      expect((REGISTRY[key].filters || []).length, key + " 필터").toBeGreaterThan(0);
      // 필터를 붙였으면 검색도 대상 필드를 못박아야 한다 — 기본 검색은 JSON.stringify(row) 전체를
      // 훑어 화면에 보이지 않는 UUID·ISO 시각·불리언까지 매칭한다.
      expect(REGISTRY[key].searchFields, key + " searchFields").toBeTruthy();
    });
  });

  it("서버가 잘라 주는 목록은 그 상한을 화면이 말한다", () => {
    // 백업 50건, 리허설 20건(app/backups/router.py). 안 밝히면 '없다'와 '안 왔다'가 같아 보인다.
    expect(REGISTRY.backup.help).toContain("50건");
    expect(REGISTRY["restore-drills"].help).toContain("20건");
  });

  it("권한 매트릭스에는 일부러 필터를 두지 않는다", () => {
    // 표가 authz.py 의 열 줄 그대로이고 페이지네이션도 없다. '영역' 옵션을 여기 적는 순간
    // 규칙이 두 벌이 된다(columnsFrom 이 역할을 서버에서 받아 오는 이유와 같다).
    expect(REGISTRY.rbac.filters).toBeUndefined();
    expect(REGISTRY.rbac.searchFields).toBeTruthy();
  });

});

/* ── 4. '비우면 …' 문구가 실제 동작과 맞는가 ───────────────────────────── */

describe("‘비우면’ 문구와 실제 동작", () => {
  const fieldHelp = (cfg, form, name) => {
    const fields = typeof cfg[form].fields === "function" ? cfg[form].fields("system_admin") : cfg[form].fields;
    const f = fields.find((x) => x.name === name);
    return f ? (f.help || "") : null;
  };


  it("나머지 네 문구는 실제 동작과 맞으므로 그대로 둔다", () => {
    // (연동의 health_url 문구가 여기 있었다 — 그 화면을 걷으면서 함께 없어졌다.)
    // payload_template — 빈 JSON 은 null 로 오고 백엔드 validator 가 {} 로 받는다.
    expect(fieldHelp(REGISTRY.schedules, "create", "payload_template")).toContain("비우면 빈 값으로 실행됩니다");
    // (상위 부서의 '비우면 최상위' 문구는 조직 콘솔의 모달로 옮겨 갔다 — screens/org/orgModals.jsx,
    //  동작 검증은 org-modals.test.jsx 의 「비우면 최상위(null)로 나간다」가 잇는다.)
    // 공지 노출 기간 — is_visible 이 starts_at/ends_at 이 None 이면 그 경계를 아예 보지 않는다.
    expect(fieldHelp(REGISTRY.announcements, "create", "starts_at")).toContain("비우면 즉시 노출됩니다");
    expect(fieldHelp(REGISTRY.announcements, "create", "ends_at")).toContain("비우면");
  });
});

/* ── 5. prompt-usage 열 ─────────────────────────────────────────────────── */

describe("프롬프트 기능 목록 열", () => {
  it("좁은 화면에서는 잘리는 게 아니라 카드로 쌓인다", () => {
    // 900px 아래에서는 DataTable 이 표 대신 카드 목록을 그린다(kit.jsx) — 그래서 여기서
    // 열을 접으면 이미 잘 보이던 값을 없애는 셈이 된다. 프롬프트 사용 통계 탭이 기능 목록이 되며(D-541)
    // 기능 상태 · 초안 열이 더해져 일곱이다.
    expect(REGISTRY["prompt-usage"]).toBeUndefined();
    expect(REGISTRY.prompts.columns).toHaveLength(7);
  });
});
