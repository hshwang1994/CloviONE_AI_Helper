import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import {
  Badge, Button, Callout, ConfirmProvider, DataTable, EmptyState, ErrorState,
  Card, FormField, MetricStrip, Modal, OverflowMenu, PageHeader, SURFACE_EDGE_WIDTH, SURFACE_TONES, Section, Surface,
  ToastProvider, statusKind, statusText, useConfirm,
} from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 키트를 MUI로 갈아끼우면서 계약이 유지되는지 보는 테스트.
 *
 * 화면 21개가 전부 이 키트를 쓰기 때문에, 여기서 prop 의미가 조용히 바뀌면 앱 전체가
 * 조금씩 틀어진다. 특히 지키려는 것들:
 *   - 상태 어휘(한국어 표시·톤)는 그대로다 — 배지/필터/카드가 같은 말을 써야 한다.
 *   - 심각도를 색만으로 전하지 않는다(WCAG 1.4.1). 텍스트 단서가 남아 있어야 한다.
 *   - 오류 상태별로 '다음에 할 수 있는 행동'이 다르다(401은 로그인, 403/404는 홈, 5xx는 재시도).
 *   - 로딩·빈 화면·오류 전환이 스크린리더에 낭독된다.
 */

function ui(node) {
  return render(
    <ThemeModeProvider>
      <ToastProvider>
        <ConfirmProvider>{node}</ConfirmProvider>
      </ToastProvider>
    </ThemeModeProvider>
  );
}

describe("상태 어휘", () => {
  it("원본값을 한국어로 옮기고 톤을 붙인다", () => {
    expect(statusText("succeeded")).toBe("완료");
    expect(statusText("unmapped")).toBe("미연결");
    expect(statusKind("unmapped")).toBe("warn");   // 회색(중립)이 아니라 실행 가능한 주의 상태다
    expect(statusKind("maintenance")).toBe("warn"); // 점검이 정상(up)보다 안전해 보이면 안 된다
    expect(statusText("이슈")).toBe("이슈");
    expect(statusKind("이슈")).toBe("danger");
  });

  it("매핑에 없는 값도 원시 식별자로 새지 않는다", () => {
    expect(statusText("in_review")).toBe("In Review");
    expect(statusText("")).toBe("알 수 없음");   // 빈 배지는 스크린리더가 읽을 게 없다
    expect(statusText(true)).toBe("예");
  });

  it("Badge는 한국어 라벨을 그린다", () => {
    ui(<Badge value="failed" />);
    expect(screen.getByText("실패")).toBeInTheDocument();
  });
});

describe("Button", () => {
  it("기존 variant/size 어휘를 MUI로 옮겨도 버튼 역할과 라벨은 그대로다", async () => {
    const onClick = vi.fn();
    ui(<Button variant="primary" size="sm" onClick={onClick}>저장</Button>);
    const btn = screen.getByRole("button", { name: "저장" });
    expect(btn).toHaveClass("MuiButton-containedPrimary");
    expect(btn).toHaveClass("MuiButton-sizeSmall");
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("size=\"sm\" 과 size=\"small\" 은 같은 작은 버튼이다", () => {
    ui(
      <>
        <Button size="sm">지우기</Button>
        <Button size="small">1:1</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "지우기" })).toHaveClass("MuiButton-sizeSmall");
    expect(screen.getByRole("button", { name: "1:1" })).toHaveClass("MuiButton-sizeSmall");
  });

  it("OverflowMenu 의 sm 과 small 도 같은 작은 아이콘 버튼이다", () => {
    const item = { key: "a", label: "보관", onClick: () => {} };
    ui(
      <>
        <OverflowMenu size="sm" ariaLabel="더 보기 sm" items={[item]} />
        <OverflowMenu size="small" ariaLabel="더 보기 small" items={[item]} />
      </>,
    );
    expect(screen.getByRole("button", { name: "더 보기 sm" })).toHaveClass("MuiIconButton-sizeSmall");
    expect(screen.getByRole("button", { name: "더 보기 small" })).toHaveClass("MuiIconButton-sizeSmall");
  });

  /* W4 재작성 — 예전에는 `danger` 가 `containedError` 임을 단언했다. 그 단언이 고정하던
     상태가 결함이었다(F-W1R-04): 파괴적 동작이 페이지에서 가장 채도 높은 면이 되어 F 패턴
     시작점인 우상단에서 주 행동을 이겼다. 계약을 강도 위계로 다시 쓴다 — 채운 면은 둘뿐이고,
     그중 error 채움은 **확인 대화 안에서만** 나온다. */
  it("파괴적 동작은 외곽선이고, 채운 error 면은 확인 대화의 마지막 버튼뿐이다", () => {
    ui(
      <>
        <Button variant="primary">저장</Button>
        <Button variant="danger">삭제</Button>
        <Button variant="dangerConfirm">삭제합니다</Button>
        <Button variant="ghost">취소</Button>
        <Button>보조</Button>
      </>,
    );
    const at = (name) => screen.getByRole("button", { name });
    expect(at("삭제")).toHaveClass("MuiButton-outlinedError");
    expect(at("삭제"), "본문의 파괴적 동작이 면을 채우면 안 된다").not.toHaveClass("MuiButton-containedError");
    expect(at("삭제합니다")).toHaveClass("MuiButton-containedError");
    expect(at("저장")).toHaveClass("MuiButton-containedPrimary");
    expect(at("취소")).toHaveClass("MuiButton-text");
    expect(at("보조")).toHaveClass("MuiButton-outlined");
    // 화면당 채운 면은 주 행동 하나다 — 같은 줄에 채움이 둘이면 위계가 없다.
    const contained = ["저장", "삭제", "취소", "보조"].filter((n) =>
      /MuiButton-contained/.test(at(n).className));
    expect(contained).toEqual(["저장"]);
  });

  it("확인 대화의 위험 확인 버튼이 실제로 dangerConfirm 강도를 쓴다", async () => {
    function Trigger() {
      const confirm = useConfirm();
      return <Button onClick={() => confirm("지울까요?", { danger: true, confirmLabel: "지우기" })}>열기</Button>;
    }
    ui(<Trigger />);
    await userEvent.click(screen.getByRole("button", { name: "열기" }));
    expect(await screen.findByRole("button", { name: "지우기" })).toHaveClass("MuiButton-containedError");
  });
});

describe("심각도를 색만으로 전하지 않는다 (WCAG 1.4.1)", () => {
  it("Callout은 아이콘이 아니라 텍스트 라벨로 톤을 알린다", () => {
    ui(<Callout tone="danger">연결이 끊어졌습니다</Callout>);
    expect(screen.getByText("오류")).toBeInTheDocument();
    expect(screen.getByText("연결이 끊어졌습니다")).toBeInTheDocument();
  });

  /* 아래 둘은 StatCard(카드 한 장 = 지표 하나)가 지키던 계약이다. 그 컴포넌트는
     MetricStrip 으로 대체됐고, 계약은 그대로 옮겨 왔다. */
  it("판독 칸은 위험/주의를 글자로도 표시한다", () => {
    ui(<MetricStrip ariaLabel="티켓" items={[{ key: "o", value: 3, label: "지연", kind: "danger" }]} />);
    expect(screen.getByText("위험")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("누를 수 있는 판독 칸만 버튼이 되고 눌림 상태를 알린다", async () => {
    const onClick = vi.fn();
    ui(
      <MetricStrip
        ariaLabel="티켓"
        items={[
          { key: "open", value: 1, label: "열린 티켓", onClick, active: true },
          { key: "done", value: 9, label: "완료" },
        ]}
      />,
    );
    // 누를 수 없는 칸은 버튼이 아니다 — 버튼은 하나뿐이어야 한다.
    const card = screen.getByRole("button");
    expect(card).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(card);
    expect(onClick).toHaveBeenCalled();
  });
});

describe("빈 화면 / 오류 상태", () => {
  it("EmptyState는 안내 항목을 모두 그리고 상태 변화를 낭독한다", () => {
    ui(
      <EmptyState
        title="티켓이 없습니다"
        situation="아직 배정된 티켓이 없습니다."
        prerequisite="Notion 계정 연결"
        steps={["새 티켓 만들기", "담당자 지정"]}
        expected="목록에 티켓이 나타납니다."
        art="tickets"
        relatedLink={{ href: "#/unassigned", label: "미할당 티켓" }}
      />
    );
    const region = screen.getByRole("status");
    expect(within(region).getByRole("heading", { name: "티켓이 없습니다" })).toBeInTheDocument();
    expect(screen.getByText("아직 배정된 티켓이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("Notion 계정 연결")).toBeInTheDocument();
    expect(screen.getByText("새 티켓 만들기")).toBeInTheDocument();
    expect(screen.getByText("목록에 티켓이 나타납니다.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "미할당 티켓" })).toBeInTheDocument();
  });

  it("401은 로그인으로, 403은 홈으로 보낸다 — 재시도를 주지 않는다", () => {
    const onRetry = vi.fn();
    const { unmount } = ui(<ErrorState error={{ status: 401, message: "만료" }} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    /* 되돌아올 곳을 싣는다(지시 19) — 예전에는 맨 `/login` 이라 재로그인 뒤 서버가 `/` 로
       떨어뜨렸고, 사용자는 보던 화면을 손으로 다시 찾아가야 했다. */
    const loginLink = screen.getByRole("link", { name: "로그인 화면으로" });
    const href = loginLink.getAttribute("href");
    expect(href.startsWith("/login")).toBe(true);
    expect(new URL(href, "https://example.test").searchParams.get("next")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
    unmount();

    ui(<ErrorState error={{ status: 403, message: "금지" }} onRetry={onRetry} />);
    expect(screen.getByRole("link", { name: "홈으로" })).toBeInTheDocument();
  });

  it("비밀번호 변경 필요(403)는 권한 부족과 다른 안내를 준다", () => {
    ui(<ErrorState error={{ status: 403, message: "비밀번호를 바꿔야 합니다", body: { error: { code: "password_change_required" } } }} />);
    expect(screen.getByRole("heading", { name: "비밀번호 변경이 필요합니다" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "비밀번호 변경하기" })).toHaveAttribute("href", "/change-password");
  });

  it("일시적 오류에만 재시도를 준다", async () => {
    const onRetry = vi.fn();
    ui(<ErrorState error={{ status: 500, message: "서버 오류" }} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalled();
  });

  // DS-14/15 — 팝오버·모달 하위목록처럼 폭이 좁은 맥락에서 전체 페이지 크기 일러스트가 남아
  // 옆의 손으로 맞춘 크기보다 크게 떴다(NotificationBell.jsx 등). size="compact"는 일러스트를
  // 빼고 텍스트/여백을 줄인다 — 내용(제목·안내)은 그대로 낭독돼야 한다.
  it("EmptyState는 size=\"compact\"에서 일러스트를 빼고 내용은 그대로 낭독한다", () => {
    ui(<EmptyState size="compact" title="새 알림이 없습니다" help="여기에 표시됩니다" art="tickets" />);
    const region = screen.getByRole("status");
    expect(within(region).getByRole("heading", { name: "새 알림이 없습니다" })).toBeInTheDocument();
    expect(screen.getByText("여기에 표시됩니다")).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull(); // art는 <img aria-hidden>이라 role은 없지만, 있다면 alt=""로도 쿼리되지 않는다
    expect(region.querySelector("img")).toBeNull();
  });

  it("ErrorState는 size=\"compact\"에서 일러스트를 빼고 재시도 동작은 그대로다", async () => {
    const onRetry = vi.fn();
    ui(<ErrorState size="compact" error={{ status: 500, message: "서버 오류" }} onRetry={onRetry} />);
    const region = screen.getByRole("alert");
    expect(region.querySelector("img")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe("DataTable", () => {
  const columns = [{ key: "name", label: "이름" }, { key: "role", label: "역할" }];
  const rows = [{ id: 1, name: "홍길동", role: "관리자" }];

  // PA-RC-0023: 「상세」 버튼 열을 없앴다(행 클릭+키보드가 같은 일을 하므로 중복이었다,
  // ui/datatable-row-keyboard.test.jsx가 그 도달 경로를 고정한다) — 행마다 다른 이름을
  // 갖는다는 계약은 이제 행 자신의 aria-label에 있다.
  it("행마다 다른 이름(aria-label)을 갖는다", () => {
    const onRow = vi.fn();
    ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} onRow={onRow} />);
    expect(screen.getByRole("row", { name: "상세 보기: 홍길동" })).toBeInTheDocument();
  });

  it("비정상 입력에도 크래시하지 않고 빈 안내로 떨어진다", () => {
    ui(<DataTable columns={undefined} rows={undefined} empty="항목 없음" />);
    expect(screen.getByText("항목 없음")).toBeInTheDocument();
  });

  /* VIS-58: 100행짜리 표가 6,014px까지 늘어나면 스크롤 중 열 제목을 잃는다. stickyHeader는
   * MUI Table에 그대로 위임하고(position:sticky), 이 표는 항상 Card(불투명 배경) 안에
   * 있으므로 스크롤되는 본문 셀이 비쳐 보이지 않게 배경색도 명시로 준다. */
  describe("고정 헤더 (VIS-58)", () => {
    it("stickyHeader가 없으면 기본 동작 그대로다 - MUI sticky 클래스가 안 붙는다", () => {
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
      const headerCell = screen.getByRole("columnheader", { name: "이름" });
      expect(headerCell.className).not.toMatch(/stickyHeader/);
    });

    it("stickyHeader=true면 헤더 셀에 MUI sticky 클래스와 불투명 배경이 붙는다", () => {
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} stickyHeader />);
      const headerCell = screen.getByRole("columnheader", { name: "이름" });
      expect(headerCell.className).toMatch(/stickyHeader/);
      // 배경이 비어 있거나 완전 투명("transparent"/알파 0)이면 스크롤되는 본문 셀이
      // 헤더 뒤로 비쳐 보인다 - 실제로 불투명한 색이 계산됐는지를 본다(빈 문자열은
      // 아무 값에나 "포함"되므로 그것만으로는 이 실패를 못 잡는다).
      const bg = getComputedStyle(headerCell).backgroundColor;
      expect(bg).not.toBe("");
      expect(bg).not.toBe("transparent");
      expect(bg).not.toMatch(/rgba\([^)]*,\s*0\s*\)$/);
    });
  });

  /* VIS-73/RESP-01/RESP-02/HOST-01/HOST-02 — 열 폭이 순수하게 내용에서 파생돼 ① 열이 많으면
   * `overflowWrap:anywhere`가 열을 '한 글자' 폭까지 짜부라뜨리고(폭 1200 근처 vertical_text_collapse)
   * ② 값 하나가 길면 그 셀이 통째로 벌어지는(51px×2,353px) 두 결함이 같은 뿌리였다. `render`가
   * 없는 순수 텍스트 열은 이제 기본이 말줄임(ellipsis)이고, 머리글 셀도 본문과 같은 바닥 폭을 받는다. */
  describe("긴 텍스트 열 보호 (VIS-73/HOST-01/HOST-02)", () => {
    const longValue = "가".repeat(200);
    it("render 없는 텍스트 열은 기본이 말줄임이고 title에 전체 값이 남는다", () => {
      ui(<DataTable columns={[{ key: "name", label: "이름" }]} rows={[{ id: 1, name: longValue }]} rowKey={(r) => r.id} />);
      const cell = screen.getByText(longValue);
      expect(cell).toHaveAttribute("title", longValue);
      expect(cell).toHaveStyle({ textOverflow: "ellipsis", whiteSpace: "nowrap" });
    });

    it("render가 있는 열(배지·버튼 등)은 말줄임을 강제하지 않는다 — 자기 폭을 스스로 관리한다", () => {
      ui(<DataTable columns={[{ key: "status", label: "상태", render: (r) => <span>{r.status}</span> }]}
        rows={[{ id: 1, status: "진행" }]} rowKey={(r) => r.id} />);
      const cell = screen.getByText("진행");
      expect(cell).not.toHaveAttribute("title");
      expect(cell.closest("td")).not.toHaveStyle({ textOverflow: "ellipsis" });
    });

    it("값이 비어 '-'로 표시될 때는 의미 없는 title을 안 붙인다", () => {
      ui(<DataTable columns={[{ key: "name", label: "이름" }]} rows={[{ id: 1, name: null }]} rowKey={(r) => r.id} />);
      const cell = screen.getByText("-");
      expect(cell).not.toHaveAttribute("title");
    });

    it("머리글 셀도 본문과 같은 바닥 폭(4.5rem)을 받는다 — 폭 지정 없는 열의 헤더/본문 비대칭 해소", () => {
      ui(<DataTable columns={[{ key: "name", label: "이름" }]} rows={[{ id: 1, name: "홍길동" }]} rowKey={(r) => r.id} />);
      const header = screen.getByRole("columnheader", { name: "이름" });
      expect(header).toHaveStyle({ minWidth: "4.5rem" });
    });
  });

  /* RESP-01: 900~1200(카드로 접히기 전, 사이드바는 아직 264px)에서 열이 많은 표만 겪는
   * 문제라 c.hideNarrow는 그 구간의 표 렌더링에서만 열을 뺀다 — 카드 뷰(폭 제약 없음)와
   * 넓은 화면(자리 충분)에서는 항상 전체 열이 보인다. */
  describe("hideNarrow 열 (RESP-01)", () => {
    const cols = [
      { key: "name", label: "이름" },
      { key: "extra", label: "부가정보", hideNarrow: true },
    ];
    const rows = [{ id: 1, name: "홍길동", extra: "부가값" }];

    function mockMedia({ card = false, compact = false } = {}) {
      window.matchMedia = (query) => ({
        matches: query.includes("899.95") ? card : query.includes("1199.95") ? compact : false,
        media: query,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}, onchange: null,
        dispatchEvent: () => false,
      });
    }

    afterEach(() => { delete window.matchMedia; });

    it("넓은 화면(둘 다 거짓)에서는 hideNarrow 열도 그대로 보인다", () => {
      mockMedia({ card: false, compact: false });
      ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
      expect(screen.getByRole("columnheader", { name: "부가정보" })).toBeInTheDocument();
    });

    it("900~1200 압축 구간(compact만 참)에서는 hideNarrow 열이 빠진다", () => {
      mockMedia({ card: false, compact: true });
      ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
      expect(screen.queryByRole("columnheader", { name: "부가정보" })).toBeNull();
      // 일반 열은 그대로 남는다 — 표 자체가 카드로 바뀐 게 아니다.
      expect(screen.getByRole("columnheader", { name: "이름" })).toBeInTheDocument();
    });

    it("카드 뷰(card도 참)에서는 폭 제약이 없으니 hideNarrow 열도 다시 보인다", () => {
      mockMedia({ card: true, compact: true });
      ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
      expect(screen.getByText("부가정보")).toBeInTheDocument();
      expect(screen.getByText("부가값")).toBeInTheDocument();
    });

    // PA-RC-0037 acceptance (4): 열이 접힌 경우 그 사실이 화면에 표시돼야 한다 — hideNarrow는
    // PA-RC-0037 이전부터 있었지만(Users.jsx) 예전엔 아무 표시 없이 조용히 사라졌다.
    it("compact 구간에서 열이 숨으면 그 사실과 숨은 열 이름을 알린다", () => {
      mockMedia({ card: false, compact: true });
      ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
      expect(screen.getByText(/부가정보 열을 숨겼습니다/)).toBeInTheDocument();
    });

    it("숨는 열이 없으면(hideNarrow 미지정) compact여도 안내를 안 보여준다 — REGRESSION 없음", () => {
      mockMedia({ card: false, compact: true });
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
      expect(screen.queryByText(/열을 숨겼습니다/)).toBeNull();
    });

    it("넓은 화면에서는 hideNarrow 열이 있어도 안내를 안 보여준다(열이 안 숨었으므로)", () => {
      mockMedia({ card: false, compact: false });
      ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
      expect(screen.queryByText(/열을 숨겼습니다/)).toBeNull();
    });
  });

  /* PA-RC-0029/0037: 행을 식별하는 열(이메일·항목명 등)에 identifier:true만 붙이면 화면마다
   * px를 직접 재지 않아도 최소 폭이 보장된다. 우선순위를 지정하지 않은 기존 화면(이 describe
   * 위의 모든 테스트가 그 예)은 렌더 결과가 바뀌지 않아야 한다 — 그 회귀 방지가 이 테스트의
   * 목적이다(required_tests: "열 우선순위 미지정 화면의 스냅샷 회귀"). */
  describe("identifier 열의 최소 폭 (PA-RC-0029/0037)", () => {
    it("identifier:true면 기본 바닥 폭(4.5rem) 대신 더 넓은 식별자 바닥 폭(12.5rem)을 받는다", () => {
      ui(<DataTable columns={[{ key: "email", label: "이메일", identifier: true }]}
        rows={[{ id: 1, email: "a@b.co" }]} rowKey={(r) => r.id} />);
      const header = screen.getByRole("columnheader", { name: "이메일" });
      expect(header).toHaveStyle({ minWidth: "12.5rem" });
    });

    it("identifier:true여도 c.minWidth를 명시하면 그 값이 이긴다(설정 화면의 항목명처럼 더 좁은 값이 필요할 수 있다)", () => {
      ui(<DataTable columns={[{ key: "label", label: "항목명", identifier: true, minWidth: "10rem" }]}
        rows={[{ id: 1, label: "설정" }]} rowKey={(r) => r.id} />);
      const header = screen.getByRole("columnheader", { name: "항목명" });
      expect(header).toHaveStyle({ minWidth: "10rem" });
    });

    it("identifier를 지정하지 않은 기존 열은 그대로 기본 바닥 폭(4.5rem)이다 — 회귀 없음", () => {
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
      const header = screen.getByRole("columnheader", { name: "이름" });
      expect(header).toHaveStyle({ minWidth: "4.5rem" });
    });
  });
});

describe("Modal", () => {
  it("접근 가능한 이름을 가진 대화상자로 열리고 Esc로 닫힌다", async () => {
    const onClose = vi.fn();
    ui(<Modal open title="사용자 추가" onClose={onClose}>본문</Modal>);
    const dlg = screen.getByRole("dialog");
    expect(dlg).toHaveAccessibleName("사용자 추가");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});

describe("FormField", () => {
  it("현재 값과 맞는 옵션이 없으면 빈 옵션을 앞에 둔다", () => {
    ui(
      <FormField
        field={{ name: "role", label: "역할", type: "select", required: true, options: [{ value: "admin", label: "관리자" }] }}
        value=""
        onChange={() => {}}
      />
    );
    expect(screen.getByLabelText(/역할/)).toBeInTheDocument();
  });

  it("도움말을 입력과 연결해 낭독되게 한다", () => {
    ui(<FormField field={{ name: "email", label: "이메일", type: "email", help: "사내 주소만" }} value="" onChange={() => {}} />);
    expect(screen.getByLabelText(/이메일/)).toHaveAccessibleDescription("사내 주소만");
  });

  // PA-RC-0005 — maxLength는 lib/fieldLimits.js가 백엔드 Pydantic 스키마에서 유도한 값을
  // FormModal이 내려보낸다(kit.test.jsx는 FormField 단위 계약만 본다 — screenKey 조회는
  // field-limits.test.jsx가 본다).
  describe("maxLength (PA-RC-0005)", () => {
    it("주어지면 네이티브 maxLength 속성으로 실제로 렌더한다", () => {
      ui(<FormField field={{ name: "name", label: "이름", type: "text" }} value="" onChange={() => {}} maxLength={120} />);
      expect(screen.getByLabelText(/이름/)).toHaveAttribute("maxlength", "120");
    });

    it("안 주어지면 maxLength 속성을 넣지 않는다(무제한 필드까지 임의로 막지 않는다)", () => {
      ui(<FormField field={{ name: "runner_id", label: "러너 ID", type: "text" }} value="" onChange={() => {}} />);
      expect(screen.getByLabelText(/러너 ID/)).not.toHaveAttribute("maxlength");
    });

    it("긴 텍스트(textarea)는 남은 글자 수를 도움말에 함께 보여준다", () => {
      ui(<FormField field={{ name: "purpose", label: "용도", type: "textarea" }} value="안녕" onChange={() => {}} maxLength={2000} />);
      expect(screen.getByLabelText(/용도/)).toHaveAccessibleDescription("2/2000자");
    });

    it("도움말이 있으면 글자 수를 이어 붙인다(도움말을 지우지 않는다)", () => {
      ui(<FormField field={{ name: "purpose", label: "용도", type: "textarea", help: "선택 입력" }} value="ab" onChange={() => {}} maxLength={10} />);
      expect(screen.getByLabelText(/용도/)).toHaveAccessibleDescription("선택 입력 (2/10자)");
    });

    it("한 줄 text는 글자 수를 따로 보여주지 않는다(네이티브 maxLength로 이미 막힌다)", () => {
      ui(<FormField field={{ name: "name", label: "이름", type: "text" }} value="ab" onChange={() => {}} maxLength={120} />);
      expect(screen.getByLabelText(/이름/)).not.toHaveAccessibleDescription(/\/120자/);
    });

    it("🔴 붙여넣기로 상한을 넘기면 조용히 자르지 않고 토스트로 알린다", async () => {
      const user = userEvent.setup();
      ui(<FormField field={{ name: "purpose", label: "용도", type: "textarea" }} value="" onChange={() => {}} maxLength={5} />);
      const el = screen.getByLabelText(/용도/);
      await user.click(el);
      await user.paste("이 문장은 다섯 글자를 훌쩍 넘는다");
      expect(await screen.findByText(/최대 5자까지만 저장됩니다/)).toBeInTheDocument();
    });

    it("상한을 넘기지 않는 붙여넣기는 토스트를 띄우지 않는다", async () => {
      const user = userEvent.setup();
      ui(<FormField field={{ name: "purpose", label: "용도", type: "textarea" }} value="" onChange={() => {}} maxLength={50} />);
      const el = screen.getByLabelText(/용도/);
      await user.click(el);
      await user.paste("짧은 문장");
      expect(screen.queryByText(/최대.*자까지만 저장됩니다/)).not.toBeInTheDocument();
    });
  });
});

describe("PageHeader", () => {
  it("빵부스러기 뿌리를 바꾸거나 숨길 수 있다", () => {
    const { unmount } = ui(<PageHeader area="사용자" title="사용자 관리" />);
    expect(screen.getByText("관리자 › 사용자")).toBeInTheDocument();
    unmount();
    ui(<PageHeader title="내 티켓" />);
    expect(screen.queryByText(/관리자 ›/)).toBeNull();
  });

  // PA-RC-0022: registry 28개 화면 + Users/Offboarding이 전부 이 자리 하나로 옮겨 온
  // "제목 옆 도움말 토글". 기본 접힘, 내용 보존, 클릭으로 펼침/접힘이 이 컴포넌트 하나의
  // 계약이라 여기서 지키면 소비처 전부가 같이 지켜진다.
  describe("help(제목 옆 도움말 토글, PA-RC-0022)", () => {
    it("help가 없으면 토글 버튼 자체가 없다", () => {
      ui(<PageHeader title="테스트" />);
      expect(screen.queryByRole("button", { name: /도움말/ })).not.toBeInTheDocument();
    });

    it("help가 있으면 기본 접힘이다 — aria-expanded=false", () => {
      ui(<PageHeader title="테스트" help="도움말 내용입니다" />);
      const toggle = screen.getByRole("button", { name: "도움말 보기" });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
    });

    it("눌러 펼치면 aria-expanded가 true로 바뀌고 라벨도 '닫기'로 바뀐다", async () => {
      const user = userEvent.setup();
      ui(<PageHeader title="테스트" help="도움말 내용입니다" />);
      const toggle = screen.getByRole("button", { name: "도움말 보기" });
      await user.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByRole("button", { name: "도움말 닫기" })).toBeInTheDocument();
    });

    it("내용은 문구 그대로 보존된다 — 옮기는 과정에서 한 글자도 안 바뀐다", () => {
      ui(<PageHeader title="테스트" help="원본 그대로여야 하는 문구" />);
      expect(screen.getByText("원본 그대로여야 하는 문구")).toBeInTheDocument();
    });

    it("JSX(문단 여러 개)도 그대로 받는다 — 문자열만 되는 게 아니다(Users/Offboarding 형태)", () => {
      ui(<PageHeader title="테스트" help={<><p>첫 줄</p><p>둘째 줄</p></>} />);
      expect(screen.getByText("첫 줄")).toBeInTheDocument();
      expect(screen.getByText("둘째 줄")).toBeInTheDocument();
    });

    it("helpTone이 주어지면 Callout의 톤 라벨이 그걸 따른다(기본은 '안내')", () => {
      const { unmount } = ui(<PageHeader title="테스트" help="일반 안내" />);
      expect(screen.getByText("안내")).toBeInTheDocument();
      unmount();
      ui(<PageHeader title="테스트" help="위험한 안내" helpTone="warn" />);
      expect(screen.getByText("주의")).toBeInTheDocument();
    });
  });
});

/* 진행 표시가 접근 가능한 이름을 지우지 않는다 (지시 20 · 25).
 *
 * 예전 구현은 라벨을 `visibility: hidden` 으로 감추고 그 자리에 회전 표시를 겹쳤다 —
 * `visibility: hidden` 인 글자는 접근성 트리에서 빠지므로 **누른 순간 버튼의 이름이
 * 사라졌다.** 스크린리더는 "버튼"만 읽는다. 눈으로도 무엇을 눌렀는지가 사라진다. */
describe("버튼 진행 표시", () => {
  it("loading 중에도 라벨이 그대로 읽히고 aria-busy 로 상태를 알린다", () => {
    ui(<Button loading>내보내기</Button>);
    const btn = screen.getByRole("button", { name: "내보내기" });
    expect(btn).toHaveAttribute("aria-busy", "true");
    expect(btn).toBeDisabled();
  });

  it("loading 이 아니면 aria-busy 를 붙이지 않는다", () => {
    ui(<Button>내보내기</Button>);
    const btn = screen.getByRole("button", { name: "내보내기" });
    expect(btn).not.toHaveAttribute("aria-busy");
    expect(btn).not.toBeDisabled();
  });
});

/* ── 면(Surface) 계약 — PLAN «Surface 위계» 를 코드가 지키는가 (W4) ────────────
 *
 * 이 저장소가 지시 82 에서 금지한 것은 규칙이 아니라 반사다: "묶어야 한다 = 흰 네모".
 * 문서로 막으면 다음 화면에서 다시 나오므로 부품이 강제한다. 그 강제가 실제로 도는지를
 * 여기서 본다 — 특히 **판 안의 판**은 자동으로 내려가야 하고, 떠 있는 것 안에서는 깊이가
 * 0 으로 되돌아가야 한다(Context 는 Portal 을 통과하므로 초기화가 없으면 모달 안의 판이
 * 전부 조용히 사라진다). */
describe("Surface — 면 위계", () => {
  it("표가 PLAN 의 일곱 tone 을 전부 담고, 판만 테두리를 갖는다", () => {
    expect(Object.keys(SURFACE_TONES).sort()).toEqual(
      ["brandTint", "inset", "modal", "none", "overlay", "plate", "sunken"].sort(),
    );
    // 테두리를 갖는 것은 판과 떠 있는 것뿐이다 — 오목면·함몰면·brandTint 는 색으로만 말한다.
    const bordered = Object.entries(SURFACE_TONES).filter(([, s]) => s.border).map(([k]) => k);
    expect(bordered.sort()).toEqual(["modal", "overlay", "plate"]);
    // 그림자는 떠 있는 것만 갖는다(D-141, 유지).
    const shadowed = Object.entries(SURFACE_TONES).filter(([, s]) => s.shadow).map(([k]) => k);
    expect(shadowed.sort()).toEqual(["modal", "overlay"]);
    // 아무것도 그리지 않는 자리가 실제로 비어 있다.
    expect(SURFACE_TONES.none).toEqual({});
    // brandTint 만 앞머리 edge 를 갖는다 — AI/Brand 순간의 표지다.
    const edged = Object.entries(SURFACE_TONES).filter(([, s]) => s.edge).map(([k]) => k);
    expect(edged).toEqual(["brandTint"]);
  });

  it("판 안의 판은 자동으로 내려가고, 그 사실이 DOM 에 남는다", () => {
    ui(
      <Card className="outer">
        <Card className="inner">안쪽</Card>
      </Card>,
    );
    const outer = document.querySelector(".outer");
    const inner = document.querySelector(".inner");
    expect(outer).toHaveAttribute("data-surface", "plate");
    expect(inner, "판 안의 판은 판이 아니다").toHaveAttribute("data-surface", "plate>none");
    // 흔적을 남기는 이유: 조용히 고치면 몇 곳이 그랬는지 아무도 모른다.
    expect(inner.className).not.toMatch(/MuiCard|MuiPaper/);
    // 테두리를 지우고 여백만 남기면 없앤 판이 공백으로 되살아난다 — 여백도 함께 사라진다.
    expect(getComputedStyle(inner).padding === "" || getComputedStyle(inner).padding === "0px").toBe(true);
  });

  it("판이 아닌 tone 은 판 안에서도 그대로다", () => {
    ui(
      <Card>
        <Surface tone="inset" className="ins">읽기 전용</Surface>
        <Surface tone="brandTint" className="tint">AI</Surface>
      </Card>,
    );
    expect(document.querySelector(".ins")).toHaveAttribute("data-surface", "inset");
    expect(document.querySelector(".tint")).toHaveAttribute("data-surface", "brandTint");
  });

  it("brandTint 는 앞머리 edge 를 **실제로 그린다** (논리 테두리 3속성)", () => {
    ui(<Surface tone="brandTint" className="tint">AI 도우미</Surface>);
    const s = getComputedStyle(document.querySelector(".tint"));
    expect(s.borderInlineStartStyle).toBe("solid");
    expect(s.borderInlineStartWidth).toBe(`${SURFACE_EDGE_WIDTH}px`);
    // 색이 팔레트 경로 문자열로 새어 나가면 무효 선언이 된다(F-W2R-01 의 두 번째 층).
    expect(s.borderInlineStartColor).toMatch(/^(rgb|#)/);
  });

  it("떠 있는 것 안에서는 깊이가 0 으로 되돌아간다 — 모달 안의 판은 판이다", () => {
    ui(
      <Card>
        <Modal open title="사용자 추가" onClose={() => {}}>
          <Card className="in-modal">모달 안</Card>
        </Modal>
      </Card>,
    );
    expect(document.querySelector(".in-modal")).toHaveAttribute("data-surface", "plate");
  });
});

/* ── W4 · R-11 — 보조가 주를 이기지 않는다 ────────────────────────────────────
 *
 * MUI v7 의 `outlined` + `color="inherit"` 은 테두리를 `currentColor` 로 그린다. 이 앱에서
 * 그것은 `text.primary` 이고 판 위 대비가 17.1:1 이라, 전체 버튼의 44%(109 호출부)를
 * 차지하는 보조 버튼이 채운 주 버튼(5.96:1)보다 **2.9배 강했다.** 눈에 보이는 결함이었고
 * 어떤 시험도 그것을 말하지 않았다. */
describe("버튼 강도 — 보조 테두리", () => {
  const ratio = (a, b) => {
    const lum = (c) => {
      const [r, g, b2] = c.match(/\d+(\.\d+)?/g).slice(0, 3).map((v) => {
        const x = Number(v) / 255;
        return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b2;
    };
    const [la, lb] = [lum(a), lum(b)];
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };

  it("보조 버튼 테두리가 본문 잉크가 아니다 — 비텍스트 3:1 은 넘고 주 행동은 안 이긴다", () => {
    ui(<><Button>보조</Button><Button variant="primary">주</Button></>);
    const border = getComputedStyle(screen.getByRole("button", { name: "보조" })).borderTopColor;
    const plate = "rgb(255, 255, 255)";
    const r = ratio(border, plate);
    expect(r, `보조 테두리 ${border} on plate = ${r.toFixed(2)}`).toBeGreaterThanOrEqual(3);
    // 예전 값(text.primary #161A2C)은 17.1:1 이었다 — 그 자리로 돌아가면 실패한다.
    expect(r, "보조 테두리가 본문 잉크만큼 강하면 위계가 뒤집힌다").toBeLessThan(8);
  });

  /* 위 한 줄을 `default` 에만 걸었더니 `danger` 가 MUI 기본값 `alpha(error.main, 0.5)` 에
   * 남아 판 위 2.48:1 이 됐다 — **되돌릴 수 없는 동작이 그 옆 중립 버튼(4.18:1)보다 흐린
   * 경계를 갖는** 역전이었다. 독립 검수가 배포 PNG 에서 (217,146,142) 를 직접 찍어 잡았다.
   * 두 variant 가 같은 하한을 받는다는 것을 여기서 고정한다. */
  it("파괴적 버튼 테두리도 3:1 을 넘고, 중립 보조보다 약하지 않다", () => {
    ui(<><Button variant="danger">삭제</Button><Button>보조</Button></>);
    const px = (name) => getComputedStyle(screen.getByRole("button", { name })).borderTopColor;
    const plate = "rgb(255, 255, 255)";
    const danger = ratio(px("삭제"), plate);
    expect(danger, `파괴 테두리 ${px("삭제")} on plate = ${danger.toFixed(2)}`).toBeGreaterThanOrEqual(3);
    expect(danger, "파괴적 동작이 중립 보조보다 흐리면 위계가 뒤집힌다")
      .toBeGreaterThanOrEqual(ratio(px("보조"), plate));
  });

  /* 채운 면은 주 행동과 «확인 대화의 마지막 버튼» 둘뿐이다. `danger` 는 외곽선이다. */
  it("danger 는 면을 칠하지 않고 dangerConfirm 만 칠한다", () => {
    ui(<><Button variant="danger">삭제</Button><Button variant="dangerConfirm">확인</Button></>);
    expect(screen.getByRole("button", { name: "삭제" }).className).toMatch(/MuiButton-outlined/);
    expect(screen.getByRole("button", { name: "확인" }).className).toMatch(/MuiButton-contained/);
  });
});

/* 판을 벗긴 뒤 선택 신호가 살아 있는가 (W4).
 * `background.inset` 은 판 위에서는 함몰면이지만 캔버스 위에서는 더 밝고 대비가 1.055:1 이라
 * 신호가 뒤집히면서 사라진다. 그래서 레일이 말한다 — 사이드바와 같은 어휘다(D-184). */
describe("판독 줄의 선택 신호", () => {
  it("지금 목록을 거르는 칸이 레일을 갖고, 나머지는 같은 두께의 투명 레일을 갖는다", () => {
    ui(
      <MetricStrip
        ariaLabel="티켓"
        items={[
          { key: "a", value: 3, label: "열림", onClick: () => {}, active: true },
          { key: "b", value: 9, label: "완료", onClick: () => {} },
        ]}
      />,
    );
    const cells = document.querySelectorAll(".k-readout");
    const on = getComputedStyle(cells[0]);
    const off = getComputedStyle(cells[1]);
    expect(on.borderBlockEndStyle).toBe("solid");
    expect(on.borderBlockEndWidth).toBe(off.borderBlockEndWidth);   // 줄 높이가 튀지 않는다
    // jsdom 은 `transparent` 를 `rgba(0, 0, 0, 0)` 으로 계산해 돌려준다.
    const clear = (v) => v === "transparent" || v === "rgba(0, 0, 0, 0)";
    expect(clear(on.borderBlockEndColor), `활성 레일 색 ${on.borderBlockEndColor}`).toBe(false);
    expect(clear(off.borderBlockEndColor), `비활성 레일 색 ${off.borderBlockEndColor}`).toBe(true);
    /* **면은 신호를 지지 않는다.** 처음에는 위 주석을 적어 두고도 `bgcolor` 를 지우지
     * 않아, 캔버스 위에서 1.055:1 로 보이지 않는 면이 그대로 남아 있었다(독립 검수 실측).
     * 활성 칸이 면을 칠하면 두 어휘가 같은 것을 두 번 말한다 — 그걸 여기서 막는다. */
    expect(clear(on.backgroundColor), `활성 칸 배경 ${on.backgroundColor}`).toBe(true);
  });
});

/* 체크리스트 ⑥ 이 가리키는 자리에 **쓸 것**이 있는가 (W4).
 * 금지만으로는 반사가 안 바뀐다 — 판을 만들지 말라고 하면서 대안을 안 주면 화면은 다시 판을
 * 만든다. `Section` 이 그 대안이고, 판을 갖지 않는다는 것이 이 부품의 전부다. */
describe("Section — 컨테이너 없는 묶음", () => {
  it("판을 갖지 않고 제목과 구획 간격만 소유한다", () => {
    ui(<Section title="최근 문서">본문</Section>);
    const sec = document.querySelector("section[data-surface]");
    expect(sec).toHaveAttribute("data-surface", "none");
    expect(sec.className).not.toMatch(/MuiCard|MuiPaper/);
    const s = getComputedStyle(sec);
    expect(Number.parseFloat(s.borderTopWidth || "0")).toBe(0);
    expect(s.backgroundColor === "" || s.backgroundColor === "rgba(0, 0, 0, 0)").toBe(true);
    expect(sec.textContent).toContain("최근 문서");
    expect(sec.textContent).toContain("본문");
  });

  it("rule 을 주면 제목 아래 실선 하나로 목록을 연다", () => {
    ui(<Section title="상태" rule><div>줄</div></Section>);
    const sec = document.querySelector("section[data-surface]");
    const ruled = [...sec.children].filter((c) => {
      const s = getComputedStyle(c);
      return Number.parseFloat(s.borderTopWidth || "0") > 0;
    });
    expect(ruled.length, "제목 아래 실선이 하나 있어야 한다").toBe(1);
  });

  it("판 안에 놓이면 판을 만들지 않는다 — 애초에 판이 아니다", () => {
    ui(<Card><Section title="안쪽">본문</Section></Card>);
    expect(document.querySelector("section[data-surface]")).toHaveAttribute("data-surface", "none");
  });
});

/* 공유 부품이 `sx` 를 받을 때 **함수 형태를 잃지 않는가** (W4).
 * 객체로만 받아 펼치면 테마를 읽는 sx 가 조용히 사라진다 — 이 저장소가 여러 번 밟은
 * "선언은 있는데 화면에는 없다" 의 한 형태다. 새로 만든 세 부품에서 그것을 고정한다. */
describe("sx 는 객체든 함수든 살아남는다", () => {
  it.each([
    ["Surface", (sx) => <Surface tone="none" className="probe" sx={sx}>x</Surface>],
    ["Card", (sx) => <Card className="probe" sx={sx}>x</Card>],
    ["Section", (sx) => <Section title="t" sx={sx}><span className="probe">x</span></Section>],
  ])("%s — 함수 sx 가 실제로 적용된다", (_name, render) => {
    const { unmount } = ui(render((t) => ({ outlineColor: t.palette.error.main, outlineStyle: "dotted", outlineWidth: "3px" })));
    const el = document.querySelector(".probe");
    const target = el.closest("[data-surface]") || el;
    expect(getComputedStyle(target).outlineWidth, "함수 sx 가 사라졌다").toBe("3px");
    unmount();
  });
});
