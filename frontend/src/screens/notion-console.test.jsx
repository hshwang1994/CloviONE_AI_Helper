import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/* Notion 관리 화면 (9-4).
 *
 * 여기서 보는 것은 **화면이 진실을 말하는가** 다.
 *
 *  1. 토큰을 되돌려 그리지 않는다.
 *  2. 못 쓰는 서버에서 되는 척하지 않는다(입력란 대신 무엇을 해야 하는지 보여 준다).
 *  3. 연결 테스트 결과의 원인을 구분해 보여 준다.
 *  4. 화면을 여는 것만으로 노션을 부르지 않는다.
 *
 * ⚠️ **값이 달라지는 표본**을 쓴다. 서로 다른 응답으로 두 번 그려서 화면이 응답을 읽는지
 * 상수를 그리는지 가른다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));
vi.mock("../app/auth.jsx", () => ({
  useAuth: () => ({ data: { role: "system_admin", id: "u-1" } }),
}));

import { NotionConsole, resultLabel, resultKind } from "./NotionConsole.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function overview(patch) {
  return {
    apply_note: "저장하면 화면과 API 조회에는 곧바로 반영됩니다.",
    databases: [
      {
        key: "notion_tasks_database_id",
        label: "작업 데이터베이스",
        value: "aaaa",
        source: "settings",
        configured: true,
        creatable: true,
        token_ref: "notion_report_token",
        used_for: "티켓 목록이 이 데이터베이스를 읽습니다.",
        when_unset: "티켓 목록이 비어 있게 됩니다.",
      },
      {
        key: "notion_documents_database_id",
        label: "문서 데이터베이스",
        value: "",
        source: "env",
        configured: false,
        creatable: true,
        token_ref: "notion_docs_token",
        used_for: "문서 목록이 이 데이터베이스를 읽습니다.",
        when_unset: "팀 공간 문서 목록이 비어 있게 됩니다.",
      },
    ],
    token: {
      items: [
        { field: "notion_report_token_ref", ref: "notion_report_token", label: "작업과 티켓용 토큰", configured: true },
        { field: "notion_docs_token_ref", ref: "notion_docs_token", label: "문서용 토큰", configured: false },
      ],
      writable: true,
      directory: "/etc/clovirone-web-assistant/secrets",
      note: "토큰 값은 저장한 뒤 다시 보여 주지 않습니다.",
      manual_instruction: null,
    },
    sprint: {
      portal_window: "포털의 이번 주는 작업 데이터베이스의 마감일로 계산합니다.",
      sprint_database_id: "",
      source: "env",
      linked: false,
      finding: "팀의 노션 스프린트 데이터베이스가 연결돼 있지 않습니다.",
      next_step: "스프린트 데이터베이스 id 를 넣고 연결 테스트를 눌러 보세요.",
    },
    ...patch,
  };
}

function renderConsole() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter>
              <NotionConsole />
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
  it("원인마다 다른 말을 쓴다", () => {
    // 셋이 같은 말로 뭉개지면 화면은 "실패" 한 마디만 하게 된다.
    const labels = [
      resultLabel("token_invalid"),
      resultLabel("database_not_found"),
      resultLabel("no_permission"),
    ];
    expect(new Set(labels).size).toBe(3);
  });

  it("성공만 정상 색을 쓴다", () => {
    expect(resultKind("ok")).toBe("ok");
    expect(resultKind("database_not_found")).not.toBe("ok");
    // 모르는 어휘가 와도 성공처럼 보이지 않는다.
    expect(resultKind("something-new")).not.toBe("ok");
  });
});

describe("화면", () => {
  it("여는 것만으로 노션을 부르지 않는다", async () => {
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());
    // 읽기 하나뿐이다. 연결 테스트는 사람이 눌러야 나간다.
    expect(apiMock.mock.calls.map((c) => c[0])).toEqual(["/api/admin/notion"]);
  });

  it("설정한 것과 안 한 것을 구분해 말한다", async () => {
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    const docs = screen.getByTestId("notion-db-notion_documents_database_id");
    // 안 채운 항목은 "비면 무슨 일이 벌어지는가" 를 말한다.
    expect(within(docs).getByText(/팀 공간 문서 목록이 비어 있게 됩니다/)).toBeInTheDocument();
    const tasks = screen.getByTestId("notion-db-notion_tasks_database_id");
    expect(within(tasks).queryByText(/비어 있게 됩니다/)).toBeNull();
    // 언제 반영되는지 화면이 말해야 한다.
    expect(screen.getByText(/곧바로 반영됩니다/)).toBeInTheDocument();
  });

  it("토큰 값을 되돌려 그리지 않는다", async () => {
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업과 티켓용 토큰")).toBeInTheDocument());

    const row = screen.getByTestId("notion-token-notion_report_token_ref");
    expect(within(row).getByText("설정됨")).toBeInTheDocument();
    // 입력란은 눌러야 나오고, 나와도 비어 있다(기존 값을 채워 넣지 않는다).
    expect(screen.queryByLabelText("새 토큰")).toBeNull();
    await userEvent.click(within(row).getByRole("button", { name: "교체" }));
    expect(screen.getByLabelText("새 토큰")).toHaveValue("");
  });

  it("쓸 수 없는 서버에서는 입력란 대신 무엇을 할지 보여 준다", async () => {
    // ⚠️ 가장 나쁜 실패는 못 쓰는 서버에서 저장 버튼을 그려 주는 것이다.
    apiMock.mockResolvedValue(
      overview({
        token: {
          ...overview().token,
          writable: false,
          manual_instruction:
            "이 서버의 웹 프로세스는 시크릿 디렉터리에 쓸 수 없습니다. /etc/clovirone-web-assistant/secrets 안에 파일을 만드세요.",
        },
      })
    );
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업과 티켓용 토큰")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: "교체" })).toBeNull();
    expect(screen.queryByRole("button", { name: "입력" })).toBeNull();
    expect(screen.getByText(/쓸 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByText(/secrets 안에 파일을 만드세요/)).toBeInTheDocument();
  });

  it("연결 테스트 결과의 원인을 구분해 보여 준다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/notion" && (!opts || !opts.method)) {
        return Promise.resolve(overview());
      }
      if (path === "/api/admin/notion/test") {
        return Promise.resolve({
          ok: false,
          tokens: [
            { field: "notion_report_token_ref", label: "작업과 티켓용 토큰", result: "ok", message: "연결에 성공했습니다.", integration_name: "포털 통합" },
            { field: "notion_docs_token_ref", label: "문서용 토큰", result: "token_missing", message: "서버에 토큰 파일이 없습니다." },
          ],
          databases: [
            { key: "notion_tasks_database_id", label: "작업 데이터베이스", result: "database_not_found", message: "데이터베이스를 찾지 못했습니다. 통합에 공유하지 않았습니다." },
            { key: "notion_documents_database_id", label: "문서 데이터베이스", result: "unset", message: "아직 설정하지 않았습니다." },
          ],
        });
      }
      return Promise.resolve({});
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "연결 테스트" }));
    const result = await screen.findByTestId("notion-test-result");

    // 토큰은 통하는데 데이터베이스를 못 찾는다 - 그 둘이 화면에서 갈라져 보여야 한다.
    expect(within(result).getByText(/작업과 티켓용 토큰: 정상/)).toBeInTheDocument();
    expect(within(result).getByText(/문서용 토큰: 토큰 없음/)).toBeInTheDocument();
    expect(within(result).getByText(/작업 데이터베이스: 찾지 못함/)).toBeInTheDocument();
    // 무엇을 해야 하는지가 문장에 들어 있어야 실행 가능한 안내가 된다.
    expect(within(result).getByText(/공유하지 않았습니다/)).toBeInTheDocument();
  });

  // SYS-11: 상태(설정됐는가)와 출처(어디서 왔는가)는 서로 다른 사실이다 — 같은 초록 칩으로
  // 섞으면 "서버 환경변수"가 건강 판정처럼 읽힌다.
  it("설정 여부 칩과 출처 칩을 따로 그린다", async () => {
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    const tasks = screen.getByTestId("notion-db-notion_tasks_database_id");
    expect(within(tasks).getByText("설정됨")).toBeInTheDocument();
    expect(within(tasks).getByText("화면에서 설정함")).toBeInTheDocument();

    const docs = screen.getByTestId("notion-db-notion_documents_database_id");
    expect(within(docs).getByText("설정 안 함")).toBeInTheDocument();
    // 설정 안 된 항목은 출처를 말할 게 없다 - 출처 칩 자체가 없어야 한다.
    expect(within(docs).queryByText("서버 환경변수")).toBeNull();
  });

  // SYS-10: 스프린트 DB 미설정 경고를 행 하나와 진단 카드 둘이서 각자 다른 문장으로
  // 두 번 말하면 안 된다 - 행은 짧은 이정표만, 설명은 진단 카드에만.
  it("스프린트 데이터베이스 미설정 경고를 행에서 반복하지 않는다", async () => {
    apiMock.mockResolvedValue(
      overview({
        databases: [
          {
            key: "notion_sprint_database_id",
            label: "스프린트 데이터베이스",
            value: "",
            source: "env",
            configured: false,
            creatable: false,
            token_ref: "notion_report_token",
            used_for: "진단에만 씁니다.",
            when_unset: "포털과 팀이 서로 다른 것을 스프린트라고 부르는지 확인할 수 없습니다.",
          },
        ],
      }),
    );
    renderConsole();
    await waitFor(() => expect(screen.getByText("스프린트 데이터베이스")).toBeInTheDocument());

    const row = screen.getByTestId("notion-db-notion_sprint_database_id");
    expect(within(row).queryByText(/포털과 팀이 서로 다른 것을 스프린트라고 부르는지/)).toBeNull();
    expect(within(row).getByText(/스프린트 진단.*확인하세요/)).toBeInTheDocument();
    // 아래 진단 카드가 그 유일한 설명 자리다.
    expect(screen.getByText(/연결돼 있지 않습니다/)).toBeInTheDocument();
  });

  // SYS-10: 진단 카드의 "연결 테스트를 눌러 보세요" 언급이 실제로 그 버튼을 가리키는
  // 클릭 가능한 링크여야 한다 - 그냥 프로즈 텍스트가 아니라.
  it("스프린트 진단의 안내가 실제 연결 테스트 버튼으로 스크롤+포커스한다", async () => {
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    const link = screen.getByRole("link", { name: "연결 테스트 버튼으로 이동" });
    const button = screen.getByRole("button", { name: "연결 테스트" });
    // jsdom은 scrollIntoView를 구현하지 않는다 - 직접 스텁한 뒤 스파이를 건다.
    button.scrollIntoView = vi.fn();
    const scrollSpy = vi.spyOn(button, "scrollIntoView");
    const focusSpy = vi.spyOn(button, "focus");

    await userEvent.click(link);
    expect(scrollSpy).toHaveBeenCalled();
    expect(focusSpy).toHaveBeenCalled();
  });

  it("스프린트 진단이 응답을 읽는다", async () => {
    // 연결 안 된 세계
    apiMock.mockResolvedValue(overview());
    const first = renderConsole();
    await waitFor(() =>
      expect(screen.getByText(/연결돼 있지 않습니다/)).toBeInTheDocument()
    );
    first.unmount();

    // 연결된 세계 - 같은 자리가 다른 문장을 그려야 한다(상수가 아니다).
    apiMock.mockResolvedValue(
      overview({
        sprint: {
          portal_window: "포털의 이번 주는 작업 데이터베이스의 마감일로 계산합니다.",
          sprint_database_id: "eeee",
          source: "settings",
          linked: true,
          finding: "스프린트 데이터베이스 id 가 설정돼 있습니다.",
          next_step: "포털의 이번 주를 노션 스프린트에 맞추려면 별도 작업이 필요합니다.",
        },
      })
    );
    renderConsole();
    await waitFor(() =>
      expect(screen.getByText(/설정돼 있습니다/)).toBeInTheDocument()
    );
    expect(screen.queryByText(/연결돼 있지 않습니다/)).toBeNull();
  });

  it("이미 설정된 데이터베이스에는 추가 버튼을 그리지 않는다", async () => {
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    const tasks = screen.getByTestId("notion-db-notion_tasks_database_id");
    expect(within(tasks).queryByRole("button", { name: "새로 추가" })).toBeNull();
    const docs = screen.getByTestId("notion-db-notion_documents_database_id");
    expect(within(docs).getByRole("button", { name: "새로 추가" })).toBeInTheDocument();
  });

  it("설정 안 됐지만 추가할 수도 없는 데이터베이스(스프린트류)는 이유를 말한다 - 버튼이 조용히 없는 게 아니다", async () => {
    // 사용자 지적: "노션관리에서... 새로운 DB 를 만들어주는 기능도있음?? ... 왜 다사라짐?"
    // 실측: 스프린트 DB 는 creatable:false(포털이 안 읽어 만들어 줘도 아무도 안 쓴다, 의도된
    // 설계, app/notion_console/service.py:74)라 버튼이 없는 게 맞다 - 하지만 화면은 그 이유를
    // 한 마디도 안 하고 그냥 버튼을 지워서, 안 만들어 준 건지 고장인지 사용자가 구별할 수 없었다.
    apiMock.mockResolvedValue(
      overview({
        databases: [
          {
            key: "notion_sprint_database_id",
            label: "스프린트 데이터베이스",
            value: "",
            source: "env",
            configured: false,
            creatable: false,
            token_ref: "notion_report_token",
            used_for: "진단에만 씁니다.",
            when_unset: "포털과 팀이 서로 다른 것을 스프린트라고 부르는지 확인할 수 없습니다.",
          },
        ],
      }),
    );
    renderConsole();
    await waitFor(() => expect(screen.getByText("스프린트 데이터베이스")).toBeInTheDocument());

    const row = screen.getByTestId("notion-db-notion_sprint_database_id");
    expect(within(row).queryByRole("button", { name: "새로 추가" })).toBeNull();
    expect(within(row).getByText(/화면에서 자동으로 추가할 수 없습니다/)).toBeInTheDocument();
  });

  it("새로 추가는 스타일 없는 브라우저 팝업(window.prompt) 대신 테마 다이얼로그로 부모 페이지 id 를 받는다", async () => {
    // 예전에는 window.prompt() 로 부모 페이지 id 를 받고, 바로 다음 줄에서 앱의 confirm() 을
    // 썼다 - 스타일 없는 네이티브 팝업과 테마 다이얼로그가 한 흐름에 섞여 튀어 보였다.
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("page-123");
    apiMock.mockResolvedValue(overview());
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    const docs = screen.getByTestId("notion-db-notion_documents_database_id");
    await userEvent.click(within(docs).getByRole("button", { name: "새로 추가" }));

    // 네이티브 팝업은 절대 불리지 않는다.
    expect(promptSpy).not.toHaveBeenCalled();
    // 대신 화면 안에 테마 다이얼로그(라벨이 붙은 입력)가 뜬다.
    expect(await screen.findByLabelText(/부모 페이지 id/)).toBeInTheDocument();

    promptSpy.mockRestore();
  });

  it("부모 페이지 id 를 넣고 확인하면 추가 요청을 보낸다", async () => {
    apiMock.mockImplementation((path, opts) => {
      if (path === "/api/admin/notion" && (!opts || !opts.method)) {
        return Promise.resolve(overview());
      }
      if (path === "/api/admin/notion/databases") {
        return Promise.resolve({ created: true, message: "만들었습니다." });
      }
      return Promise.resolve({});
    });
    renderConsole();
    await waitFor(() => expect(screen.getByText("작업 데이터베이스")).toBeInTheDocument());

    const docs = screen.getByTestId("notion-db-notion_documents_database_id");
    await userEvent.click(within(docs).getByRole("button", { name: "새로 추가" }));

    const input = await screen.findByLabelText(/부모 페이지 id/);
    await userEvent.type(input, "page-123");
    await userEvent.click(screen.getByRole("button", { name: "계속" }));

    // 정말 만드는지 다시 한번 테마 확인 대화상자로 묻는다(되돌릴 수 없다는 경고 포함).
    const confirmDialog = await screen.findByText(/되돌리려면 노션에서 직접 지워야 합니다/);
    expect(confirmDialog).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => {
      const call = apiMock.mock.calls.find((c) => c[0] === "/api/admin/notion/databases");
      expect(call).toBeTruthy();
      expect(call[1].body).toEqual({
        key: "notion_documents_database_id",
        parent_page_id: "page-123",
        title: "문서 데이터베이스",
        confirm: true,
      });
    });
  });
});
