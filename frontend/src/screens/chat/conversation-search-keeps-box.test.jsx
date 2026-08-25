import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

/* 검색 중에는 결과가 0건이어도 **검색 상자가 남는다** (S21).
 *
 * 이 상자는 `convItems.length > 0` 일 때만 그려졌다. `convItems` 는 서버가 이미 걸러 온
 * 결과라, 조건이 하나도 안 맞는 순간 상자가 자기를 지웠다 — 한 글자를 잘못 친 사람은
 * 그 글자를 지울 칸을 잃는다. 조건을 좁힌 사람이 넓히는 길은 그 조건을 적은 자리여야 한다.
 */

vi.mock("../../ui/kit.jsx", async (importOriginal) => await importOriginal());

import { ConversationSidebar } from "./ConversationSidebar.jsx";

function renderSidebar(props) {
  return render(
    <ConversationSidebar
      convs={{ isLoading: false, isError: false, refetch: () => {} }}
      convItems={[]}
      cid={null}
      setCid={() => {}}
      convFilter=""
      setConvFilter={() => {}}
      showArchived={false}
      setShowArchived={() => {}}
      sideOpen
      setSideOpen={() => {}}
      clearDraft={() => {}}
      setComposingNew={() => {}}
      textareaRef={{ current: null }}
      hasMoreConvs={false}
      loadMoreConvs={() => {}}
      listIsDrawer={false}
      closeSideDrawer={() => {}}
      confirm={async () => true}
      renameConv={{ mutate: () => {} }}
      archiveConv={{ mutate: () => {}, mutateAsync: async () => {} }}
      deleteConv={{ mutate: () => {} }}
      {...props}
    />,
  );
}

beforeEach(() => { vi.clearAllMocks(); });

describe("대화 목록 검색 상자", () => {
  it("검색어가 있으면 결과가 0건이어도 상자가 남는다", () => {
    renderSidebar({ convItems: [], convFilter: "존재하지않는대화zz" });
    expect(screen.getByLabelText("대화 목록 검색")).toBeInTheDocument();
  });

  it("대화도 검색어도 없으면 상자를 그리지 않는다", () => {
    renderSidebar({ convItems: [], convFilter: "" });
    expect(screen.queryByLabelText("대화 목록 검색")).not.toBeInTheDocument();
  });

  it("좁힌 사람이 그 자리에서 다시 넓힐 수 있다", async () => {
    const user = userEvent.setup();
    const setConvFilter = vi.fn();
    renderSidebar({ convItems: [], convFilter: "zz", setConvFilter });
    await user.type(screen.getByLabelText("대화 목록 검색"), "{Backspace}");
    expect(setConvFilter).toHaveBeenCalled();
  });
});
