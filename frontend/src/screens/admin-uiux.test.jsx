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
  await userEvent.click(within(cell.closest("tr")).getByRole("button", { name: /상세/ }));
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
    await userEvent.click(within(drawer).getByRole("button", { name: "거절" }));

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

  /* RG-01 — "발행 내용 보기"(document.publish 승인의 GET 조회 액션)가 "서버에 연결할 수
   * 없습니다."로 죽어 있었다. 원인은 DataScreen.jsx의 runAction이 method를 안 가리고
   * body:{}를 실어 보낸 것 — GET에 body를 실으면 fetch 스펙 자체가 TypeError를 던진다
   * (lib/api.js는 method!=="GET"일 때만 body를 JSON.stringify하고, GET이면 원시 객체를
   * 그대로 fetch에 넘긴다). 이 시험은 그 계약을 고정한다: GET 액션은 body 키 자체가 없어야
   * 한다 — 값이 없는 게 아니라 키가 없어야 한다(수정 전에는 항상 body:{} 가 실려 있었다). */
  it("'발행 내용 보기'(GET): body 없이 요청하고, 발행 미리보기를 안내 모달로 보여준다 (RG-01)", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "GET" && String(path).includes("/api/admin/documents/")) {
        expect(opts).not.toHaveProperty("body");
        return Promise.resolve({ generation: { status: "completed", preview: { title: "월간 리포트", body: "본문 내용" } } });
      }
      return Promise.resolve({
        items: [{
          id: "a1", request_type: "document.publish", object_type: "team_doc", object_id: "d-9",
          requested_by: "u-2", requester_name: "홍길동", status: "pending",
          requested_at: "2026-08-01T00:00:00Z", expires_at: "2026-08-04T00:00:00Z",
          due_at: null, overdue: false, can_decide: true,
          request_payload: { generation_id: "gen-1" },
        }],
        total: 1, page: 1, page_size: 20,
      });
    });
    renderScreen("approvals");
    const drawer = await openRow("홍길동");
    await userEvent.click(within(drawer).getByRole("button", { name: "발행 내용 보기" }));

    const dlg = await screen.findByRole("dialog", { name: "발행 내용 보기" }, WAIT);
    expect(dlg).toHaveTextContent("월간 리포트");
    expect(dlg).toHaveTextContent("본문 내용");
  });

  it("조직 '비활성화': 확인 문구가 로그인이 끊긴다는 사실과 인원수를 말한다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{
        id: "o1", slug: "goodmit", name: "굿밋", status: "active",
        department_count: 4, user_count: 37,
        created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
      }],
      total: 1,
    }));
    renderScreen("organizations");
    const drawer = await openRow("굿밋");
    await userEvent.click(within(drawer).getByRole("button", { name: "비활성화" }));

    const dlg = await confirmDialog();
    // 비활성화는 _revoke_org_sessions 로 전원을 즉시 내보내고 재로그인까지 막는다.
    // '기존 사용자와 부서는 그대로 남습니다'만 말하면 아무 일도 없는 것처럼 읽힌다.
    expect(dlg).toHaveTextContent("37");
    expect(dlg).toHaveTextContent(/로그아웃/);
    expect(dlg).toHaveTextContent(/다시 로그인할 수 없게/);
    // 거절과 달리 이건 되돌릴 수 있다 — 되돌릴 수 있다는 사실도 함께 말해야 과잉 공포가 없다.
    expect(dlg).toHaveTextContent(/되돌릴 수 있습니다/);
  });

  it("이미 확인을 받고 있던 액션은 그대로 남아 있다(있던 것을 되돌리지 않는다)", () => {
    const confirmOf = (key, label) =>
      (REGISTRY[key].actions || []).find((a) => a.label === label && a.confirm);
    expect(confirmOf("prompts", "보관")).toBeTruthy();
    expect(confirmOf("policies", "보관")).toBeTruthy();
    expect(confirmOf("feature-flags", "비활성화")).toBeTruthy();
  });

  /* PA-RC-0023: 비활성 부서의 상세는 '수정'(DataScreen의 canEdit 분기, 항상 primary)과
   * '활성화'(activeToggle)가 같은 footer에 함께 뜬다 — 둘 다 primary였던 것을 '활성화'만
   * default로 내렸다(actions.js). 화면당 contained는 정확히 하나여야 한다는 규범을
   * 값으로 고정한다 — 이 실측(색 클래스 대조)이 없으면 나중에 누가 실수로 primary를
   * 되돌려도 아무 시험도 못 잡는다. */
  it("비활성 부서 상세: '수정'만 primary고 '활성화'는 아니다(화면당 primary 1개)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({
      items: [{
        id: "d1", name: "휴면 부서", org_name: "굿밋", org_id: "o1",
        active: false, user_count: 0, child_department_count: 0,
        created_at: "2026-01-01T00:00:00Z",
      }],
      total: 1,
    }));
    renderScreen("departments");
    const drawer = await openRow("휴면 부서");

    const colorClass = (el) =>
      [...el.classList].find((c) => /^MuiButton-(outlined|contained|text)[A-Z]/.test(c));

    const edit = within(drawer).getByRole("button", { name: "수정" });
    const activate = within(drawer).getByRole("button", { name: "활성화" });
    expect(colorClass(edit)).toMatch(/^MuiButton-contained/);
    expect(colorClass(activate)).not.toMatch(/^MuiButton-contained/);

    // 서술이 아니라 실제 렌더에서 채운 버튼이 하나인지 직접 센다.
    const filled = within(drawer).getAllByRole("button").filter((b) => colorClass(b) === "MuiButton-containedPrimary");
    expect(filled).toHaveLength(1);
  });
});

/* ── 2. 거르는 조건은 서버로 간다(못 가면 이름을 대고 밝힌다) ───────────── */

describe("필터가 어디서 걸리는가", () => {
  it("Notion 연결 '출처'는 서버 요청에 실려 나간다(페이지 안에서만 거르지 않는다)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }));
    renderScreen("notion-mapping");
    await findText("표시할 사용자가 없습니다");

    await userEvent.click(screen.getByRole("combobox", { name: /출처/ }));
    await userEvent.click(await screen.findByRole("option", { name: "수동 지정" }, WAIT));
    await waitFor(() =>
      expect(apiMock.mock.calls.some(([p]) => String(p).includes("source=manual"))).toBe(true), WAIT);
  });

  it("paginated 화면에서 페이지 안에서만 도는 필터는 경고가 그 필터 이름을 지목한다", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }));
    renderScreen("documents");
    // 백엔드 list_generations 는 status 만 받는다 — 모드는 구조적으로 현재 페이지까지가 한계다.
    // 한계가 있는 것 자체보다, 그것을 말하지 않는 것이 결함이다.
    expect(await findText(/‘모드’ 필터는 지금 보고 있는 페이지에만 적용됩니다/)).toBeInTheDocument();
  });

  it("clientFilter 를 쓰는 화면은 documents 를 빼면 전부 paginated 가 아니다", () => {
    // paginated + clientFilter 는 '다른 페이지의 일치 항목이 사라지는' 조합이다.
    // documents 만 예외로 남고(서버가 mode 를 안 받는다) 그 화면은 위 경고를 띄운다.
    const offenders = Object.values(REGISTRY)
      .filter((c) => c.paginated && (c.filters || []).some((f) => f.clientFilter))
      .map((c) => c.key);
    expect(offenders).toEqual(["documents"]);
  });

  it("스케줄과 조직도는 결함이 아니었다 — 그 상태를 못박는다", () => {
    // 스케줄: 백엔드가 파라미터를 안 받지만 페이지네이션도 없다 → 받아 온 것이 곧 전부다.
    expect(REGISTRY.schedules.paginated).toBeFalsy();
    expect((REGISTRY.schedules.filters || []).length).toBeGreaterThan(0);
    // 조직도: '사용' 필터는 처음부터 서버 필터였다(GET /departments/tree 가 active 를 받는다).
    const active = (REGISTRY["org-tree"].filters || []).find((f) => f.key === "active");
    expect(active).toBeTruthy();
    expect(active.clientFilter).toBeFalsy();
  });
});

/* ── 3. 필터가 하나도 없던 화면 ─────────────────────────────────────────── */

describe("좁혀 볼 수단", () => {
  it("전수조사가 지목한 화면에 좁힐 수단이 생겼다", () => {
    ["organizations", "backup", "ai-quotas", "restore-drills"].forEach((key) => {
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

  it("조직 '상태' 필터를 골라도 요청은 그대로다(서버가 안 받는 파라미터를 지어내지 않는다)", async () => {
    apiMock.mockImplementation(() => Promise.resolve({ items: [], total: 0 }));
    renderScreen("organizations");
    await findText("추가된 조직이 없습니다");
    const before = apiMock.mock.calls.length;
    await userEvent.click(screen.getByRole("combobox", { name: /상태/ }));
    await userEvent.click(await screen.findByRole("option", { name: "미사용" }, WAIT));
    // clientFilter 는 같은 데이터를 다시 받지 않는다(queryKey 에 안 들어간다).
    await waitFor(() => expect(screen.getByRole("combobox", { name: /상태/ })).toHaveTextContent("미사용"), WAIT);
    expect(apiMock.mock.calls.length).toBe(before);
    expect(apiMock.mock.calls.every(([p]) => !String(p).includes("status="))).toBe(true);
  });
});

/* ── 4. '비우면 …' 문구가 실제 동작과 맞는가 ───────────────────────────── */

describe("‘비우면’ 문구와 실제 동작", () => {
  const fieldHelp = (cfg, form, name) => {
    const fields = typeof cfg[form].fields === "function" ? cfg[form].fields("system_admin") : cfg[form].fields;
    const f = fields.find((x) => x.name === name);
    return f ? (f.help || "") : null;
  };

  it("프롬프트 러너 ID: 비워도 지워지지 않는다고 정직하게 말한다", () => {
    // 백엔드 PATCH 가 `if payload.runner_id is not None:` 가드라, FormModal 이 보내는 null 을
    // '안 보냄'과 구별하지 못하고 통째로 무시한다(app/prompts/router.py). 화면만 해제됐다고 믿었다.
    const help = fieldHelp(REGISTRY.prompts, "edit", "runner_id");
    expect(help).not.toMatch(/비우면 연결 해제/);
    expect(help).toMatch(/비워도 기존 연결은 지워지지 않습니다/);
  });

  it("나머지 여섯 문구는 실제 동작과 맞으므로 그대로 둔다", () => {
    // health_url ×2 — run_health_check 가 `row.health_url or row.base_url` 로 대체한다.
    expect(fieldHelp(REGISTRY.integrations, "create", "health_url")).toContain("비우면 Base URL");
    expect(fieldHelp(REGISTRY.runners, "create", "health_url")).toContain("비우면 Base URL");
    // payload_template — 빈 JSON 은 null 로 오고 백엔드 validator 가 {} 로 받는다.
    expect(fieldHelp(REGISTRY.schedules, "create", "payload_template")).toContain("비우면 빈 값으로 실행됩니다");
    // 상위 부서 — select 는 빈 값을 null 로 보내고 validate_parent 가 None 을 '최상위'로 읽는다.
    const dept = REGISTRY.departments.create.fields.find((f) => f.name === "parent_id");
    expect(dept.help).toContain("비우면 최상위 부서가 됩니다");
    // 공지 노출 기간 — is_visible 이 starts_at/ends_at 이 None 이면 그 경계를 아예 보지 않는다.
    expect(fieldHelp(REGISTRY.announcements, "create", "starts_at")).toContain("비우면 즉시 노출됩니다");
    expect(fieldHelp(REGISTRY.announcements, "create", "ends_at")).toContain("비우면");
  });
});

/* ── 5. prompt-usage 열 ─────────────────────────────────────────────────── */

describe("프롬프트 사용 통계 열", () => {
  it("열은 일곱이고, 좁은 화면에서는 잘리는 게 아니라 카드로 쌓인다", () => {
    // 전수조사 메모는 '아홉 열이라 좁은 화면에서 잘린다'고 했지만 둘 다 사실이 아니다.
    // 열은 일곱이고, 900px 아래에서는 DataTable 이 표 대신 카드 목록을 그린다(kit.jsx).
    // 그래서 여기서 열을 접으면 이미 잘 보이던 값을 없애는 셈이 된다.
    expect(REGISTRY["prompt-usage"].columns).toHaveLength(7);
  });
});
