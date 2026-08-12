import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import "@testing-library/jest-dom/vitest";

/* 문서 상세 계약 테스트.
 *
 * 이 화면의 핵심은 **장애 격리**다. 메타는 로컬 캐시, 본문 블록은 실시간 Notion이라 본문만
 * 따로 실패할 수 있다. 그때 화면 전체가 오류로 무너지거나, 반대로 아무 말 없이 빈 여백만
 * 남으면 사용자는 "문서가 삭제됐나?"라고 오해한다 — 제목·메타·원본 링크는 그대로 두고
 * 본문 자리에만 이유를 적어야 한다.
 *
 * DocBody/safeExternal은 티켓 상세(Ticket.jsx)도 함께 쓰는 공용 렌더러라 시그니처가 계약이다.
 */

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({
  api: (...args) => apiMock(...args),
  setCsrf: () => {},
}));

import { TeamDoc, DocBody, safeExternal } from "./TeamDoc.jsx";
import { ConfirmProvider, ToastProvider } from "../ui/kit.jsx";
import { ThemeModeProvider } from "../ui/ThemeModeProvider.jsx";

function wrap(node, path = "/team-docs/d1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/team-docs/:id" element={node} />
                <Route path="*" element={node} />
              </Routes>
            </MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </ThemeModeProvider>
    </QueryClientProvider>
  );
}

const DOC = {
  id: "d1", title: "네트워크 설계서", document_type: "설계서", status: "활성",
  work_field: "인프라", tech_tags: ["Nginx"], projects: ["사내망 개편"],
  author_names: ["김운영"], owner: "플랫폼 운영팀", priority: "높음",
  last_edited: "2026-08-01T01:00:00", original_url: "https://notion.so/abc",
  is_favorite: false,
};

beforeEach(() => {
  apiMock.mockReset();
});

describe("페이지에 h1이 하나뿐이다 (SEM-03 재검증)", () => {
  it("PageHeader의 h1과 문서 제목의 h1이 중복되지 않는다", async () => {
    apiMock.mockResolvedValue({ document: DOC, blocks: [] });
    wrap(<TeamDoc />);
    await screen.findByText("네트워크 설계서");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("본문이 없거나 실패해도 메타는 남는다", () => {
  it("blocks가 비어 있으면 제목·메타는 그대로 두고 본문 자리에만 안내를 넣는다", async () => {
    apiMock.mockResolvedValue({ document: DOC, blocks: [] });
    wrap(<TeamDoc />);

    expect(await screen.findByRole("heading", { name: "네트워크 설계서" })).toBeInTheDocument();
    expect(screen.getByText("본문 내용이 없습니다. 원본 문서를 확인해 주세요.")).toBeInTheDocument();
    // 메타 레일은 살아 있어야 한다 — 본문이 없다고 문서 정보까지 사라지면 안 된다.
    expect(screen.getByText("업무 분야")).toBeInTheDocument();
    expect(screen.getByText("인프라")).toBeInTheDocument();
    // 원본 링크(장애 시 유일한 탈출구)도 남는다.
    expect(screen.getByRole("button", { name: "원본 열기" })).toBeInTheDocument();
  });

  it("blocks가 아예 null이어도 렌더가 깨지지 않는다", async () => {
    apiMock.mockResolvedValue({ document: { ...DOC, original_url: null, url: null, source_url: null } });
    wrap(<TeamDoc />);

    expect(await screen.findByRole("heading", { name: "네트워크 설계서" })).toBeInTheDocument();
    expect(screen.getByText("본문 내용이 없습니다. 원본 문서를 확인해 주세요.")).toBeInTheDocument();
    // 안전하지 않은/없는 원본 URL이면 '원본 열기' 버튼 자체를 내지 않는다.
    expect(screen.queryByRole("button", { name: "원본 열기" })).toBeNull();
  });

  it("blocks_error가 오면 원인을 적어 주고 원본으로 유도한다", async () => {
    apiMock.mockResolvedValue({ document: DOC, blocks: null, blocks_error: "Notion 응답 시간 초과" });
    wrap(<TeamDoc />);

    expect(await screen.findByRole("heading", { name: "네트워크 설계서" })).toBeInTheDocument();
    expect(screen.getByText(/Notion 응답 시간 초과/)).toBeInTheDocument();
    // 본문만 실패했을 뿐이므로 메타 레일(소유자 등)은 계속 보인다.
    expect(screen.getByText("플랫폼 운영팀")).toBeInTheDocument();
  });
});

describe("DocBody 공용 렌더러(티켓 상세와 공유)", () => {
  it("연속한 글머리/번호는 하나의 목록으로 묶는다", () => {
    const { container } = render(
      <DocBody blocks={[
        { kind: "paragraph", text: "머리말" },
        { kind: "bulleted", text: "첫째" },
        { kind: "bulleted", text: "둘째" },
        { kind: "numbered", text: "하나" },
        { kind: "numbered", text: "둘" },
      ]} />
    );
    // bare <li>가 흩어지면 번호가 문서 전체 카운터를 공유해 잘못 매겨진다.
    expect(container.querySelectorAll("ul")).toHaveLength(1);
    expect(container.querySelectorAll("ol")).toHaveLength(1);
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    expect(container.querySelectorAll("ol > li")).toHaveLength(2);
  });

  // user_team-doc-detail 재확인 — 본문 안 URL이 본문과 같은 색·굵기의 평문이라 클릭할 수
  // 없었다. 팀 채팅 말풍선이 이미 쓰는 linkifyText(chat/links.jsx)를 재사용해 고쳤다 —
  // 허용 도메인(Notion)은 실제 링크로, 그 외는 복사 버튼 폴백으로(임의 외부 링크를
  // 한 클릭으로 열게 하지 않는 기존 보안 판단은 그대로 유지).
  it("본문 문단 안 Notion URL이 실제 링크가 된다", () => {
    render(
      <DocBody blocks={[
        { kind: "paragraph", text: "회의록은 https://www.notion.so/team/meeting-abc123 에서 확인하세요." },
      ]} />
    );
    const link = screen.getByRole("link", { name: /notion\.so\/team\/meeting-abc123/ });
    expect(link).toHaveAttribute("href", "https://www.notion.so/team/meeting-abc123");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("허용 도메인이 아닌 외부 URL은 실제 링크 대신 복사 버튼으로 뜬다(임의 외부 링크 미허용)", () => {
    render(
      <DocBody blocks={[
        { kind: "paragraph", text: "접속 주소: https://internal.example.com/vpn 입니다." },
      ]} />
    );
    expect(screen.queryByRole("link", { name: /internal\.example\.com/ })).toBeNull();
    // 이 버튼의 접근성 이름은 Tooltip 안내문("외부 링크는...")이다 — URL 자체는 눈에
    // 보이는 자식 텍스트일 뿐 이름이 아니다.
    const copyBtn = screen.getByRole("button", { name: "외부 링크는 열 수 없습니다, 눌러서 주소를 복사합니다." });
    expect(copyBtn).toHaveTextContent("https://internal.example.com/vpn");
  });

  it("코드 블록 안의 URL은 링크로 바뀌지 않는다(원문 그대로)", () => {
    const { container } = render(
      <DocBody blocks={[
        { kind: "code", text: "curl https://www.notion.so/api/x" },
      ]} />
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("pre")).toHaveTextContent("curl https://www.notion.so/api/x");
  });

  it("목록 항목 안 URL도 링크가 된다(문단뿐 아니라 모든 텍스트 자리)", () => {
    render(
      <DocBody blocks={[
        { kind: "bulleted", text: "원본: https://www.notion.so/team/source-1" },
      ]} />
    );
    expect(screen.getByRole("link", { name: /notion\.so\/team\/source-1/ })).toBeInTheDocument();
  });
});

describe("문서 댓글 (사용자 지적 #9)", () => {
  /* 화면이 실제로 타래를 걸고 있는지 본다. 서버만 만들고 화면에 안 붙이면
     "댓글 기능이 있다"는 말이 사용자에게는 거짓이다. */
  const COMMENTS = [
    { id: "c1", author_user_id: "u1", author_name: "김운영", body: "이 설계 근거가 궁금합니다.",
      deleted: false, deleted_at: null, created_at: "2026-08-01T01:00:00",
      updated_at: "2026-08-01T01:00:00", can_edit: true, can_delete: true },
  ];

  const routed = (comments) => (path) => {
    if (path.indexOf("/comments") >= 0) return Promise.resolve({ ok: true, comments });
    return Promise.resolve({ document: DOC, blocks: [] });
  };

  it("문서 상세에 댓글 타래를 건다", async () => {
    apiMock.mockImplementation(routed(COMMENTS));
    wrap(<TeamDoc />);

    expect(await screen.findByText("이 설계 근거가 궁금합니다.")).toBeInTheDocument();
    // 문서 댓글은 문서 주소로 간다 — 티켓 주소를 복사해 오면 여기서 잡힌다.
    expect(apiMock).toHaveBeenCalledWith("/api/team-docs/d1/comments");
  });

  it("삭제된 댓글은 사라지지 않고 툼스톤으로 남는다", async () => {
    apiMock.mockImplementation(routed([
      { ...COMMENTS[0], body: "", deleted: true, deleted_at: "2026-08-01T03:00:00",
        can_edit: false, can_delete: false },
    ]));
    wrap(<TeamDoc />);

    expect(await screen.findByText(/삭제된 댓글입니다/)).toBeInTheDocument();
    expect(screen.queryByText("이 설계 근거가 궁금합니다.")).toBeNull();
  });

  it("등록하면 서버가 준 목록을 그대로 반영한다(클라가 목록을 기워 맞추지 않는다)", async () => {
    const user = userEvent.setup();
    apiMock.mockImplementation((path, opts) => {
      if (opts && opts.method === "POST") {
        expect(path).toBe("/api/team-docs/d1/comments");
        return Promise.resolve({ ok: true, comment_id: "c9", comments: [
          ...COMMENTS,
          { id: "c9", author_user_id: "u2", author_name: "나", body: "새 댓글",
            deleted: false, deleted_at: null, created_at: "2026-08-01T04:00:00",
            updated_at: "2026-08-01T04:00:00", can_edit: true, can_delete: true },
        ] });
      }
      return routed(COMMENTS)(path);
    });

    wrap(<TeamDoc />);
    await screen.findByText("이 설계 근거가 궁금합니다.");
    const box = within(screen.getByRole("region", { name: "댓글" }));
    await user.type(box.getByLabelText("댓글 입력"), "새 댓글");
    await user.click(box.getByRole("button", { name: "댓글 등록" }));

    expect(await screen.findByText("새 댓글")).toBeInTheDocument();
  });
});

describe("레이아웃 — 댓글은 메타 레일에", () => {
  const routed = (comments) => (path) => {
    if (path.indexOf("/comments") >= 0) return Promise.resolve({ ok: true, comments });
    return Promise.resolve({ document: DOC, blocks: [] });
  };

  it("댓글은 본문 카드가 아니라 메타 레일(우측 컬럼)에 렌더된다", async () => {
    apiMock.mockImplementation(routed([]));
    const { container } = wrap(<TeamDoc />);

    await screen.findByRole("heading", { name: "네트워크 설계서" });
    const main = container.querySelector('[data-testid="doc-detail-main"]');
    const rail = container.querySelector('[data-testid="doc-detail-rail"]');
    expect(main).toBeInTheDocument();
    expect(rail).toBeInTheDocument();

    const commentsRegion = await screen.findByRole("region", { name: "댓글" });
    // 댓글은 본문 카드가 아니라 메타 레일 안에 있어야 한다.
    expect(main.contains(commentsRegion)).toBe(false);
    expect(rail.contains(commentsRegion)).toBe(true);

    // 레일 안에서도 메타(업무 분야 등)가 댓글보다 먼저 나온다.
    const metaLabel = within(rail).getByText("업무 분야");
    expect(metaLabel.compareDocumentPosition(commentsRegion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // 좁은 화면에서 한 열로 접힐 때도 본문이 댓글보다 먼저 나와야 한다.
    expect(main.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("열람 제한 토글(SEC-10)", () => {
  it("운영자가 아니면 제한 버튼 자체가 없다", async () => {
    apiMock.mockResolvedValue({ document: { ...DOC, can_restrict: false, restricted: false }, blocks: [] });
    wrap(<TeamDoc />);
    await screen.findByRole("heading", { name: "네트워크 설계서" });
    expect(screen.queryByRole("button", { name: "열람 제한" })).toBeNull();
  });

  it("제한된 문서는 배지·안내와 함께 '제한 해제' 버튼을 보여준다", async () => {
    apiMock.mockResolvedValue({ document: { ...DOC, can_restrict: true, restricted: true }, blocks: [] });
    wrap(<TeamDoc />);
    await screen.findByRole("heading", { name: "네트워크 설계서" });
    expect(screen.getByText("🔒 열람 제한")).toBeInTheDocument();
    expect(screen.getByText(/운영자와 작성자 본인만 볼 수 있고/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🔒 제한 해제" })).toBeInTheDocument();
  });

  it("운영자가 제한 버튼을 누르면 확인 뒤 restrict API를 부르고 화면을 새로고침한다", async () => {
    const user = userEvent.setup();
    let restricted = false;
    apiMock.mockImplementation((path, opts) => {
      if (path.indexOf("/restrict") >= 0) {
        expect(path).toBe("/api/team-docs/d1/restrict?on=true");
        restricted = true;
        return Promise.resolve({ ok: true, restricted: true });
      }
      return Promise.resolve({ document: { ...DOC, can_restrict: true, restricted }, blocks: [] });
    });
    wrap(<TeamDoc />);
    await screen.findByRole("heading", { name: "네트워크 설계서" });

    await user.click(screen.getByRole("button", { name: "열람 제한" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "제한" }));

    await screen.findByRole("button", { name: "🔒 제한 해제" });
  });
});

describe("safeExternal", () => {
  it("http(s)만 통과시킨다", () => {
    expect(safeExternal("https://notion.so/a")).toBe("https://notion.so/a");
    expect(safeExternal("http://intra/a")).toBe("http://intra/a");
    expect(safeExternal("javascript:alert(1)")).toBeNull();
    expect(safeExternal(null)).toBeNull();
    expect(safeExternal(123)).toBeNull();
  });
});
