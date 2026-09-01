import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";

/* 목록 끝 줄의 계약.
 *
 * 자동 로딩은 **폭주하기 쉽다** — 센티넬이 계속 보이는 상태(다음 묶음이 전부 걸러졌거나
 * 컨테이너가 숨겨졌거나)에서 가드가 없으면 요청이 끝없이 나간다. 그리고 그 폭주는 화면에
 * 아무 표시도 안 남긴다. 여기서 재는 것 대부분이 그 가드들이다. */

import { ListFooter } from "./InfiniteScroll.jsx";
import { createClovirTheme } from "./theme.js";

function renderFooter(props) {
  return render(
    <ThemeProvider theme={createClovirTheme()}>
      <ListFooter total={184} loaded={100} hasNext isFetchingNext={false} onMore={() => {}} {...props} />
    </ThemeProvider>,
  );
}

const intersect = async () => { await act(async () => { globalThis.__intersect(); }); };

describe("ListFooter — 받은 건수와 「더 보기」", () => {
  it("몇 건 중 몇 건을 받았는지 말한다", () => {
    renderFooter({});
    expect(screen.getByText("184건 중 100건을 받았습니다.")).toBeInTheDocument();
  });

  it("전체를 모르는 목록은 받은 건수만 말한다 — 없는 숫자를 지어내지 않는다", () => {
    renderFooter({ total: null, loaded: 40 });
    expect(screen.getByText("40건을 받았습니다.")).toBeInTheDocument();
  });

  it("단추로도 받을 수 있다 — 키보드·스크린리더는 무한 스크롤에 닿을 수 없다", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore });
    await userEvent.click(screen.getByRole("button", { name: "더 보기" }));
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("더 받을 것이 없으면 단추가 없다", () => {
    renderFooter({ hasNext: false, total: 100, loaded: 100 });
    expect(screen.queryByRole("button", { name: "더 보기" })).toBeNull();
  });

  /* 실브라우저에서 잡은 결함이다. MUI 의 sx 는 `width`/`height` 의 1 이하 숫자를 **백분율**로
     옮기므로 `width: 1` 은 1px 이 아니라 `100%` 다 — 보이지 않는 센티넬이 바닥 줄 폭을 915px
     먹어 건수 문구와 단추가 오른쪽으로 밀리고 단추 글자가 두 줄로 접혔다. 유닛 시험이
     「센티넬이 있다」만 보고 **얼마나 큰가**를 안 보면 이 부류는 영원히 안 잡힌다. */
  it("센티넬은 자리를 안 먹는다 — 보이지 않는 칸이 바닥 줄을 밀면 안 된다", () => {
    const { container } = renderFooter({});
    const sentinel = container.querySelector('[data-list-footer] [aria-hidden="true"]');
    expect(sentinel).not.toBeNull();
    const style = window.getComputedStyle(sentinel);
    expect(style.width).toBe("1px");
    expect(style.height).toBe("1px");
    expect(style.flex).toBe("0 0 auto");
  });
});

describe("ListFooter — 자동 로딩과 그 가드들", () => {
  it("센티넬이 보이면 다음 묶음을 부른다", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore });
    await intersect();
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("받는 중에는 다시 안 부른다 — IO 는 한 콜백에 여러 entry 를 준다", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore, isFetchingNext: true });
    await intersect();
    expect(onMore).not.toHaveBeenCalled();
  });

  it("더 받을 것이 없으면 센티넬 자체를 안 그린다 — 끝난 목록에 남기면 계속 교차 상태다", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore, hasNext: false, total: 100, loaded: 100 });
    await intersect();
    expect(onMore).not.toHaveBeenCalled();
  });
});
describe("ListFooter — 폭주를 막는 가드 둘", () => {
  it("받았는데 건수가 안 늘면 자동을 끈다 — 단추는 남는다", async () => {
    /* 다음 묶음이 통째로 걸러졌거나 컨테이너가 숨겨져 센티넬이 계속 보이는 상태.
       가드가 없으면 요청이 끝없이 나가고, 화면에는 아무 표시도 안 남는다. */
    const onMore = vi.fn();
    const { rerender } = render(
      <ThemeProvider theme={createClovirTheme()}>
        <ListFooter total={184} loaded={100} hasNext isFetchingNext={false} onMore={onMore} />
      </ThemeProvider>,
    );
    await intersect();
    expect(onMore).toHaveBeenCalledTimes(1);

    const view = (fetching, loaded) => (
      <ThemeProvider theme={createClovirTheme()}>
        <ListFooter total={184} loaded={loaded} hasNext isFetchingNext={fetching} onMore={onMore} />
      </ThemeProvider>
    );
    await act(async () => { rerender(view(true, 100)); });
    await act(async () => { rerender(view(false, 100)); });   // 받았는데 안 늘었다

    await intersect();
    expect(onMore).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "더 보기" })).toBeInTheDocument();
  });

  it("autoMaxRows 를 넘으면 자동이 멎고 조건을 좁히라고 말한다 — 단추로는 계속 받는다", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore, loaded: 300, total: 1148, autoMaxRows: 300 });
    await intersect();
    expect(onMore).not.toHaveBeenCalled();
    expect(screen.getByText(/조건을 좁히면 더 빨리 찾습니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "더 보기" }));
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("상한 아래에서는 그대로 자동이다", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore, loaded: 100, total: 1148, autoMaxRows: 300 });
    await intersect();
    expect(onMore).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/조건을 좁히면/)).toBeNull();
  });

  it("autoMaxRows=0 이면 자동이 아예 없다 — 봉투가 offset 을 안 받는 목록의 문서화된 예외", async () => {
    const onMore = vi.fn();
    renderFooter({ onMore, loaded: 100, total: 500, autoMaxRows: 0 });
    await intersect();
    expect(onMore).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "더 보기" })).toBeInTheDocument();
  });
});

describe("ListFooter — IntersectionObserver 가 없는 환경", () => {
  it("조용히 단추만 남는다 — 그 단추가 있어야 하는 이유와 같은 이유로 성립한다", async () => {
    const saved = globalThis.IntersectionObserver;
    delete globalThis.IntersectionObserver;
    try {
      const onMore = vi.fn();
      renderFooter({ onMore });
      expect(screen.getByRole("button", { name: "더 보기" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "더 보기" }));
      expect(onMore).toHaveBeenCalledTimes(1);
    } finally {
      globalThis.IntersectionObserver = saved;
    }
  });
});