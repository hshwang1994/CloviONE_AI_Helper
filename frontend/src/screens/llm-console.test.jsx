import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* AI(LLM) 관리 화면 (9-5).
 *
 * 여기서 보는 것은 **화면이 진실을 말하는가** 다.
 *
 *  1. 설정만 보고 초록불을 그리지 않는다(로그인 안 된 서버에서도 설정은 멀쩡히 맞다).
 *  2. 큐에 맡긴 확인이 아직 안 끝났으면 결과가 없다고 말한다.
 *  3. 미로그인을 다른 실패와 구분해 보여 준다.
 *  4. 사용 여부는 세 상태다. 끄기와 안 정하기를 합치면 환경변수로 켜 둔 설치가 꺼진다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { LlmConsole, jobLabel, testKind } from "./LlmConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function overview(patch) {
  return {
    config: {
      enabled: false,
      backend: "cli",
      executable: "claude",
      model: "sonnet",
      timeout_seconds: 120,
      max_concurrency: 1,
    },
    limits: {
      min_timeout_seconds: 5,
      max_timeout_seconds: 600,
      max_concurrency: 4,
      test_timeout_seconds: 60,
    },
    sources: {},
    editable_keys: [],
    login: {
      backend: "cli",
      title: "서버에서 서비스 계정으로 로그인해야 합니다",
      steps: ["서버에 접속합니다.", "claude 명령을 실행합니다."],
      note: "관리자 계정으로 로그인하면 안 됩니다. 워커는 서비스 계정으로 돌기 때문입니다.",
    },
    apply_note: "저장하면 곧바로 반영됩니다.",
    test_mode_note: "연결 테스트는 작업 큐에 맡깁니다.",
    verified: false,
    verified_note: "이 화면은 설정값만 보여 줍니다. 실제로 통하는지는 연결 테스트를 눌러야 압니다.",
    ...patch,
  };
}

const EMPTY_SETTINGS = { settings: {} };

function mockApi({ view, test, job }) {
  apiMock.mockImplementation((path, opts) => {
    if (path === "/api/admin/llm" && (!opts || !opts.method)) return Promise.resolve(view);
    if (path === "/api/admin/settings" && (!opts || !opts.method)) {
      return Promise.resolve(EMPTY_SETTINGS);
    }
    if (path === "/api/admin/llm/test" && opts && opts.method === "POST") {
      return Promise.resolve(test || { job_id: "job-1", status: "queued", note: "n", timeout_seconds: 60 });
    }
    if (path.startsWith("/api/admin/llm/test/")) return Promise.resolve(job);
    return Promise.resolve({});
  });
}

function renderConsole() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <LlmConsole />
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiMock.mockReset();
});

describe("결과 어휘", () => {
  it("아직 안 끝난 상태를 완료라고 부르지 않는다", () => {
    expect(jobLabel("queued")).not.toContain("완료");
    expect(jobLabel("running")).not.toContain("완료");
    expect(jobLabel("succeeded")).toContain("완료");
  });

  it("성공만 정상 색을 쓴다", () => {
    expect(testKind("ok")).toBe("ok");
    expect(testKind("not_logged_in")).not.toBe("ok");
    expect(testKind("busy")).not.toBe("ok");
    // 모르는 어휘가 와도 성공처럼 보이지 않는다.
    expect(testKind("brand-new-status")).not.toBe("ok");
  });
});

describe("화면", () => {
  it("설정이 맞아도 통한다고 말하지 않는다", async () => {
    mockApi({ view: overview({ config: { ...overview().config, enabled: true } }) });
    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    expect(screen.getByText("활성")).toBeInTheDocument();
    // 🔴 활성 상태라는 것과 통한다는 것은 다른 사실이다.
    expect(screen.getByText("확인 안 함")).toBeInTheDocument();
    expect(screen.getByText(/연결 테스트를 눌러야/)).toBeInTheDocument();
  });

  it("UA-28: 백엔드 값이 잘못되면 '꺼짐' 배지만이 아니라 진짜 원인을 따로 말한다", async () => {
    mockApi({
      view: overview({
        config: { ...overview().config, enabled: false, backend: "clii" },
        backend_invalid: true,
      }),
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("비활성")).toBeInTheDocument());

    expect(screen.getByText(/백엔드 값\("clii"\)이 올바르지 않아/)).toBeInTheDocument();
  });

  it("백엔드 값이 정상이면(단지 꺼져 있을 뿐이면) 그 경고를 안 보여준다", async () => {
    mockApi({ view: overview({ backend_invalid: false }) });
    renderConsole();
    await waitFor(() => expect(screen.getByText("비활성")).toBeInTheDocument());

    expect(screen.queryByText(/올바르지 않아/)).toBeNull();
  });

  it("지금 적용 중인 값을 응답에서 읽는다", async () => {
    // 값이 달라지는 표본: 두 응답으로 두 번 그려 화면이 상수를 그리지 않음을 보인다.
    mockApi({ view: overview() });
    const first = renderConsole();
    await waitFor(() => expect(screen.getByText("모델: sonnet")).toBeInTheDocument());
    expect(screen.getByText("동시 실행 수: 1")).toBeInTheDocument();
    first.unmount();

    mockApi({
      view: overview({
        config: { enabled: true, backend: "api", executable: "/opt/bin/claude", model: "opus", timeout_seconds: 45, max_concurrency: 3 },
      }),
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("모델: opus")).toBeInTheDocument());
    expect(screen.getByText("동시 실행 수: 3")).toBeInTheDocument();
    expect(screen.getByText("실행 파일: /opt/bin/claude")).toBeInTheDocument();
  });

  it("아직 저장한 적 없는 값에는 어디서 왔는지를 붙인다", async () => {
    // "저장했는데 왜 안 바뀌지" 의 답이 화면 안에 있어야 한다.
    mockApi({ view: overview({ sources: { llm_model: "env", llm_backend: "settings" } }) });
    renderConsole();
    await waitFor(() => expect(screen.getByText(/모델: sonnet/)).toBeInTheDocument());

    expect(screen.getByText(/모델: sonnet \(서버 환경변수 또는 기본값\)/)).toBeInTheDocument();
    // 화면에서 저장한 값에는 안 붙는다(전부에 붙으면 아무 뜻이 없다).
    expect(screen.getByText("백엔드: cli")).toBeInTheDocument();
  });

  it("SYS-07: '사용 여부'·'백엔드' 상자는 안 고른 상태에서도 빈 상자가 아니라 라벨을 보여준다", async () => {
    // value=""는 MUI가 "아직 안 고름"으로 보고 라벨을 안 그리는 게 기본값이다
    // (SelectProps displayEmpty:true 가 없으면 여기서 실패한다) — 빈 상자만 보면
    // "서버 값을 따름"(정상)과 "안 불러와짐"(오류)을 구분할 수 없었다.
    mockApi({ view: overview() });
    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    expect(screen.getByLabelText("사용 여부")).toHaveTextContent("서버 환경변수를 따름");
    expect(screen.getByLabelText("백엔드")).toHaveTextContent("서버 환경변수를 따름");
  });

  it("사용 여부에 '환경변수를 따름' 이 따로 있다", async () => {
    // 끄기와 안 정하기를 합치면 환경변수로 켜 둔 설치가 이 화면을 처음 여는 순간 꺼진다.
    mockApi({ view: overview() });
    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    await userEvent.click(screen.getByLabelText("사용 여부"));
    const options = await screen.findAllByRole("option");
    const labels = options.map((o) => o.textContent);
    expect(labels).toContain("서버 환경변수를 따름");
    expect(labels).toContain("활성화");
    expect(labels).toContain("비활성화");
  });

  it("큐에 있는 동안 결과를 지어내지 않는다", async () => {
    mockApi({
      view: overview(),
      job: { job_id: "job-1", status: "queued", pending: true, result: null },
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "연결 테스트" }));
    const box = await screen.findByTestId("llm-test-result");
    expect(box).toHaveTextContent("차례를 기다리는 중");
    expect(box).toHaveTextContent("아직 결과가 없습니다");
  });

  it("미로그인을 다른 실패와 구분해 보여 준다", async () => {
    mockApi({
      view: overview(),
      job: {
        job_id: "job-1",
        status: "failed",
        pending: false,
        result: {
          status: "not_logged_in",
          message: "명령줄 도구는 찾았지만 로그인되어 있지 않습니다. 서버에서 서비스 계정으로 로그인해야 합니다.",
        },
      },
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "연결 테스트" }));
    const box = await screen.findByTestId("llm-test-result");
    expect(box).toHaveTextContent("로그인되어 있지 않습니다");
    // 무엇을 해야 하는지가 문장에 들어 있어야 실행 가능한 안내가 된다.
    expect(box).toHaveTextContent("서비스 계정");
  });

  it("로그인 안내가 응답을 읽는다", async () => {
    mockApi({ view: overview() });
    const first = renderConsole();
    await waitFor(() =>
      expect(screen.getByText("서버에서 서비스 계정으로 로그인해야 합니다")).toBeInTheDocument()
    );
    expect(screen.getByText(/관리자 계정으로 로그인하면 안 됩니다/)).toBeInTheDocument();
    first.unmount();

    mockApi({
      view: overview({
        login: {
          backend: "api",
          title: "API 키로 인증합니다",
          steps: ["Anthropic 콘솔에서 API 키를 발급합니다."],
          note: "허용 목록에 없으면 호출 자체가 막힙니다.",
        },
      }),
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("API 키로 인증합니다")).toBeInTheDocument());
    expect(screen.queryByText(/관리자 계정으로 로그인하면 안 됩니다/)).toBeNull();
  });
});

// 사용자 지적: "AI관리 페이지... 쓸때없이 페이지만 너비만 차지하고 실제 설정하는거는
// 한줄로 돼있고" — 필드 여섯 개가 폭 제한 없는 Box에 세로로 하나씩 쌓여, 넓은 화면에서
// 각 줄 오른쪽이 통째로 비었다. 반응형 그리드(SETTINGS_GRID)로 옮겨 여러 필드가 폭을
// 나눠 쓰게 한다.
describe("설정 필드는 그리드로 폭을 나눠 쓴다", () => {
  it("여섯 필드가 한 grid 컨테이너 안에 있다(세로로 홀로 쌓이지 않는다)", async () => {
    mockApi({ view: overview() });
    renderConsole();
    const grid = await screen.findByTestId("llm-settings-grid");
    expect(window.getComputedStyle(grid).display).toBe("grid");
    // 사용 여부/백엔드/실행 파일/모델/제한 시간/동시 실행 수 — 여섯 개.
    expect(grid.children.length).toBe(6);
  });
});

/* 회귀: 저장 버튼이 바뀐 필드 수만큼 하나의 useMutation을 동시에(forEach + mutate) 호출하던
 * 예전 코드는 필드 하나가 성공하면 그 onSuccess가 setDraft(null)을 불러 아직 응답을 기다리던
 * (혹은 나중에 실패하는) 다른 필드의 미저장 값까지 통째로 지웠다. 지금은 필드를 순서대로
 * 저장하고, 실패한 필드만 초안에 남긴다.
 */
describe("저장 — 필드를 순서대로 저장하고, 실패한 필드만 초안에 남긴다", () => {
  it("여러 필드를 저장할 때 하나가 실패해도 성공한 필드 때문에 실패한 필드의 편집 값이 사라지지 않는다", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/llm" && (!opts || !opts.method)) return Promise.resolve(overview());
      if (path === "/api/admin/settings" && (!opts || !opts.method)) {
        return Promise.resolve({ settings: { llm_backend: { value: "cli" }, llm_model: { value: "sonnet" } } });
      }
      if (path === "/api/admin/settings/llm_backend" && opts && opts.method === "PUT") return Promise.resolve({});
      if (path === "/api/admin/settings/llm_model" && opts && opts.method === "PUT") {
        return Promise.reject(new Error("모델을 저장하지 못했습니다."));
      }
      return Promise.resolve({});
    });

    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    const modelInput = screen.getByLabelText("모델");
    await user.clear(modelInput);
    await user.type(modelInput, "opus");

    await user.click(screen.getByLabelText("백엔드"));
    await user.click(await screen.findByRole("option", { name: "Anthropic API" }));

    await user.click(screen.getByRole("button", { name: "저장" }));

    // 실패 1건을 하나로 모은 요약 토스트만 뜬다 — 필드마다 중복으로 뜨던 예전 성공/실패 토스트의 회귀 확인.
    expect(await screen.findByText("1개 항목을 저장하지 못했습니다. 나머지 값은 초안에 그대로 남아 있습니다. 다시 시도해 주세요.")).toBeInTheDocument();

    // 실패한 필드(모델)의 편집 값은 사라지지 않는다 — 성공한 다른 필드(백엔드)의 onSuccess가
    // 초안 전체를 지워버리던 예전 버그의 핵심 회귀 확인.
    expect(screen.getByLabelText("모델")).toHaveValue("opus");

    // 두 PUT이 모두 나갔다(성공한 필드도, 실패한 필드도 각각 시도된다).
    expect(apiMock.mock.calls.some((c) => c[0] === "/api/admin/settings/llm_backend" && c[1] && c[1].method === "PUT")).toBe(true);
    expect(apiMock.mock.calls.some((c) => c[0] === "/api/admin/settings/llm_model" && c[1] && c[1].method === "PUT")).toBe(true);
  });

  it("모두 성공하면 성공 토스트가 한 번만 뜨고 초안이 비워진다(저장 버튼이 다시 비활성화된다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/llm" && (!opts || !opts.method)) return Promise.resolve(overview());
      if (path === "/api/admin/settings" && (!opts || !opts.method)) {
        return Promise.resolve({ settings: { llm_backend: { value: "cli" }, llm_model: { value: "sonnet" } } });
      }
      if (opts && opts.method === "PUT") return Promise.resolve({});
      return Promise.resolve({});
    });

    renderConsole();
    await waitFor(() => expect(screen.getByText("지금 적용 중인 값")).toBeInTheDocument());

    const modelInput = screen.getByLabelText("모델");
    await user.clear(modelInput);
    await user.type(modelInput, "opus");
    await user.click(screen.getByLabelText("백엔드"));
    await user.click(await screen.findByRole("option", { name: "Anthropic API" }));

    await user.click(screen.getByRole("button", { name: "저장" }));

    const toasts = await screen.findAllByText(/^저장했습니다\./);
    expect(toasts).toHaveLength(1);
    await waitFor(() => expect(screen.getByRole("button", { name: "저장" })).toBeDisabled());
  });
});
