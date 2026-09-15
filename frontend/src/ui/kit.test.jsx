import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import {
  Badge, Button, Callout, ConfirmProvider, DataTable, EmptyState, ErrorState,
  Card, FlatBadgeSurface, FormField, Modal, OverflowMenu, PageHeader, SURFACE_EDGE_WIDTH, SURFACE_TONES, Section, Segmented, Surface,
  ToastProvider, statusKind, statusText, useConfirm,
} from "./kit.jsx";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";
import { StatusKpiTile } from "./StatusKpi.jsx";

/* qa-contract-change: 판독 줄(MetricStrip)이 핸드오프 RULES §6(「판독 줄은 쓰지 않는다」)에 따라 걷히고 측정값 타일(StatusKpiTile)이 그 자리를 이어, 판독 칸이 지키던 세 계약(신호를 색만으로 말하지 않는다 · 누를 수 있는 칸만 버튼이고 눌림을 알린다 · 선택은 면이 아니라 선이 말한다)을 타일로 옮긴다. */

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
    // Workflow Status 여섯 (D-349). 저장값 「진행」의 표시 이름은 「진행 중」이다.
    expect(statusText("진행")).toBe("진행 중");
    expect(statusKind("진행")).toBe("info");
    // 상태값에는 빨강이 없다 — 빨강은 차단 신호가 쓴다.
    expect(statusKind("보류")).toBe("purple");
    expect(statusKind("취소")).toBe("teal");
    expect(statusKind("계획")).toBe("indigo");
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
  /* 🔴 이 계약이 **옮겨 갔다**(값이 약해진 것이 아니다).
   *
   * 예전에는 톤의 이름(안내 · 성공 · 주의 · 오류)이 상자의 **제목 줄**로 섰다. 그 한 줄이
   * 두 가지를 망쳤다: 한 줄짜리 안내의 높이가 두 배가 됐고, 제목 자리를 일반 낱말이
   * 차지해 진짜 제목을 넣을 곳이 사라졌다. 색 외 단서는 그대로 있어야 하므로 그것을
   * **아이콘의 접근 이름**으로 옮긴다 — 모양 넷이 이미 서로 다르고(동그라미 i · 체크 ·
   * 삼각형 · 동그라미 느낌표), 낭독기는 그 이름을 읽는다. 아래 셋을 함께 잰다:
   * 접근 이름이 있는가 · 화면 글자로는 안 서는가 · `title` 을 주면 그 자리가 열리는가. */
  it("Callout은 아이콘의 접근 이름으로 톤을 알리고 화면에는 그 낱말을 안 적는다", () => {
    const { unmount } = ui(<Callout tone="danger">연결이 끊어졌습니다</Callout>);
    expect(screen.getByLabelText("오류")).toBeInTheDocument();
    expect(screen.getByText("연결이 끊어졌습니다")).toBeInTheDocument();
    expect(screen.queryByText("오류")).toBeNull();
    unmount();

    ui(<Callout tone="warn">저장하지 못했습니다</Callout>);
    expect(screen.getByLabelText("주의")).toBeInTheDocument();
    expect(screen.queryByText("주의")).toBeNull();
  });

  it("Callout의 제목 자리는 호출부가 줄 때만 선다", () => {
    const { container, unmount } = ui(<Callout tone="warn">본문</Callout>);
    // 제목이 없으면 글 칸의 자식은 본문 하나뿐이다(톤 낱말이 위에 앉지 않는다).
    const bodyOnly = container.querySelector(".k-callout > div");
    expect(bodyOnly.children).toHaveLength(1);
    unmount();

    ui(<Callout tone="warn" title="이 회차는 닫혔습니다">본문</Callout>);
    expect(screen.getByText("이 회차는 닫혔습니다")).toBeInTheDocument();
    expect(screen.getByText("본문")).toBeInTheDocument();
  });

  /* 하나의 박스, 아이콘만 다르다 — 확정된 메시지 박스 규약.
   *
   * 예전에는 톤마다 앞머리 실선(2px)과 바탕(`*.bg`)이 달라 같은 목적의 상자가 화면마다
   * 네 가지 무게로 나타났다. 「무게가 같아졌다」는 눈으로만 확인할 수 있는 사실이 아니다 —
   * 네 톤의 계산된 면과 테두리가 실제로 한 값인지 잰다. */
  describe("메시지 박스 — 넷이 같은 상자다", () => {
    const TONES = ["info", "success", "warn", "danger"];

    it("네 톤의 면·테두리·모서리가 한 값이다", () => {
      const seen = TONES.map((tone) => {
        const { container, unmount } = ui(<Callout tone={tone}>본문</Callout>);
        const box = container.querySelector(".k-callout");
        const s = getComputedStyle(box);
        const got = {
          bg: s.backgroundColor,
          border: `${s.borderTopWidth} ${s.borderTopStyle} ${s.borderTopColor}`,
          radius: s.borderTopLeftRadius,
          // 앞머리 컬러 바가 남아 있으면 이 값이 톤마다 갈린다.
          rail: `${s.borderInlineStartWidth} ${s.borderInlineStartColor}`,
        };
        unmount();
        return got;
      });
      for (const key of ["bg", "border", "radius", "rail"]) {
        expect(new Set(seen.map((v) => v[key])).size, key).toBe(1);
      }
      // 그리고 그 테두리는 실제로 그려진다(0px 이 넷 다 같은 것으로 통과하지 않게).
      expect(seen[0].border).toMatch(/^1px solid /);
    });

    it("오류만 alert 이고 나머지는 status 다", () => {
      const { unmount } = ui(<Callout tone="danger">끊겼습니다</Callout>);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      unmount();
      for (const tone of ["info", "success", "warn"]) {
        const r = ui(<Callout tone={tone}>알립니다</Callout>);
        expect(screen.getByRole("status"), tone).toBeInTheDocument();
        r.unmount();
      }
    });

    it("목록 안에 놓이면 호출부가 role 을 정한다 — 그래야 목록이 안 깨진다", () => {
      ui(<Callout tone="warn" role="listitem">알림 하나</Callout>);
      expect(screen.getByRole("listitem")).toBeInTheDocument();
      expect(screen.queryByRole("status")).toBeNull();
    });

    it("동작은 글의 오른쪽 칸에 선다 — 상자가 대개 한 줄이기 때문이다", () => {
      const { container } = ui(
        <Callout tone="warn" action={<button type="button">닫기</button>}>알림 하나</Callout>,
      );
      const box = container.querySelector(".k-callout");
      expect(getComputedStyle(box).gridTemplateColumns).toBe("auto minmax(0,1fr) auto");
      // 동작이 없으면 그 칸 자체가 없다 — 빈 트랙이 글 폭을 먹지 않는다.
      const plain = ui(<Callout tone="warn">알림 하나</Callout>);
      expect(getComputedStyle(plain.container.querySelector(".k-callout")).gridTemplateColumns)
        .toBe("auto minmax(0,1fr)");
    });
  });

  /* 아래 둘은 StatCard(카드 한 장 = 지표 하나)가 지키던 계약이다. 그 컴포넌트는 판독 줄(MetricStrip)로,
     판독 줄은 측정값 타일(`StatusKpiTile`)로 이어졌고 계약은 그대로 옮겨 왔다. */
  it("측정값 타일은 신호를 색만으로 말하지 않는다 — 낱말이 늘 함께 서고 점은 거든다", () => {
    const { container } = ui(<StatusKpiTile label="지연" value={3} kind="danger" />);
    expect(screen.getByText("지연")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    // 점은 뜻을 나르지 않는 장식이라 낭독에서 빠진다 — 뜻은 낱말이 나른다.
    const dot = container.querySelector("[data-status-dot]");
    expect(dot).toHaveAttribute("aria-hidden", "true");
    expect(dot.textContent).toBe("");
  });

  it("누를 수 있는 측정값 타일만 버튼이 되고 눌림 상태를 알린다", async () => {
    const onClick = vi.fn();
    ui(
      <>
        <StatusKpiTile label="열린 티켓" value={1} onClick={onClick} selected />
        <StatusKpiTile label="완료" value={9} />
      </>,
    );
    // 누를 수 없는 타일은 버튼이 아니다 — 버튼은 하나뿐이어야 한다.
    const card = screen.getByRole("button");
    expect(card).toHaveAttribute("aria-pressed", "true");
    expect(card).toHaveAccessibleName("열린 티켓 1");
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

  /* 429 — 예전에는 「불러오지 못했습니다」+ 살아 있는 「다시 시도」였다. 그 버튼을 누를
   * 때마다 제한이 유지된다(사용자가 스스로 rate limit 을 강화하는 루프) — 429 는 대기
   * 시간을 말하고, 그 시간 동안 버튼을 잠가야 한다. */
  it("🔴 429는 대기 시간을 말하고 그동안 재시도를 잠근다", () => {
    vi.useFakeTimers();
    try {
      const onRetry = vi.fn();
      ui(<ErrorState error={{ status: 429, message: "요청이 너무 잦습니다.", retryAfterSeconds: 8 }} onRetry={onRetry} />);
      expect(screen.getByRole("heading", { name: "요청이 너무 잦습니다" })).toBeInTheDocument();
      expect(screen.getByText("약 8초 뒤에 다시 시도할 수 있습니다.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "다시 시도" })).toBeDisabled();
      act(() => { vi.advanceTimersByTime(8000); });
      expect(screen.getByRole("button", { name: "다시 시도" })).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("대기 시간을 모르는 429(프록시 층)는 바로 다시 시도할 수 있다", async () => {
    const onRetry = vi.fn();
    ui(<ErrorState error={{ status: 429, message: "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요." }} onRetry={onRetry} />);
    expect(screen.getByRole("heading", { name: "요청이 너무 잦습니다" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("AI 사용 상한(긴 429)은 서버 문구를 그대로 보이고 재시도를 주지 않는다", () => {
    ui(
      <ErrorState
        error={{
          status: 429,
          message: "하루 AI 사용 상한(5회)에 도달했습니다. 내일 0시 이후 다시 사용할 수 있습니다.",
          retryAfterSeconds: 86400,
        }}
        onRetry={vi.fn()}
      />
    );
    expect(screen.getByText(/하루 AI 사용 상한/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).toBeNull();
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

  /* 묶음 머리행·발 줄·선택 — 이 셋이 없어서 표 구현이 갈라져 있었다.
   * 내 티켓의 묶음 목록과 개발 리포트의 담당자별 상세가 각자 `<Table>` 을 그렸고, 그래서
   * 정렬·말줄임·열 접기 규칙이 두 벌이 됐다. 줄 하나가 없어서 표가 갈라지느니 표가 그
   * 줄을 갖는다. */
  describe("묶음 머리행 · 발 줄 · 선택", () => {
    const gcols = [
      { key: "name", label: "이름", type: "title" },
      { key: "proj", label: "프로젝트", type: "text" },
    ];
    const grows = [
      { id: 1, name: "가", proj: "클로비" },
      { id: 2, name: "나", proj: "클로비" },
      { id: 3, name: "다", proj: "게이트" },
    ];

    it("묶음이 바뀌는 자리에만 머리행이 서고 건수를 스스로 센다", () => {
      const { container } = ui(
        <DataTable columns={gcols} rows={grows} rowKey={(r) => r.id} groupOf={(r) => r.proj} />,
      );
      const heads = container.querySelectorAll("[data-group-row]");
      expect(heads).toHaveLength(2);
      expect(heads[0].getAttribute("data-group-row")).toBe("클로비");
      expect(heads[1].getAttribute("data-group-row")).toBe("게이트");
      // 건수는 호출부가 안 줘도 표가 센다.
      expect(within(heads[0]).getByText("2건")).toBeInTheDocument();
      expect(within(heads[1]).getByText("1건")).toBeInTheDocument();
      // 스크린 리더가 «아래 행들이 이 이름에 속한다» 로 읽는다.
      const th = heads[0].querySelector("th");
      expect(th.getAttribute("scope")).toBe("colgroup");
      expect(Number(th.getAttribute("colspan"))).toBe(gcols.length);
    });

    it("groupOf 를 안 주면 묶음 머리행이 하나도 없다", () => {
      const { container } = ui(<DataTable columns={gcols} rows={grows} rowKey={(r) => r.id} />);
      expect(container.querySelectorAll("[data-group-row]")).toHaveLength(0);
      expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
    });

    it("발 줄은 몇 건 중 몇 건인지 말하고 일괄 동작을 오른쪽에 둔다", () => {
      ui(
        <DataTable
          columns={gcols} rows={grows} rowKey={(r) => r.id} total={520}
          footer={{ actions: <button type="button">내보내기</button> }}
        />,
      );
      expect(screen.getByText("520건 중 3건을 받았습니다.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "내보내기" })).toBeInTheDocument();
    });

    it("total 을 모르면 발 줄이 숫자를 지어내지 않는다", () => {
      const { container } = ui(<DataTable columns={gcols} rows={grows} rowKey={(r) => r.id} footer />);
      expect(container.querySelector("tfoot")).toBeTruthy();
      expect(container.querySelector("tfoot").textContent).toBe("");
    });

    it("고른 행만 선택 표시를 갖는다", () => {
      const { container } = ui(
        <DataTable columns={gcols} rows={grows} rowKey={(r) => r.id} rowSelected={(r) => r.id === 2} />,
      );
      const sel = container.querySelectorAll("tbody tr.Mui-selected");
      expect(sel).toHaveLength(1);
      expect(sel[0].textContent).toContain("나");
    });

    it("rowSelected 를 안 주면 어떤 행도 선택 표시를 갖지 않는다", () => {
      const { container } = ui(<DataTable columns={gcols} rows={grows} rowKey={(r) => r.id} />);
      expect(container.querySelectorAll("tbody tr.Mui-selected")).toHaveLength(0);
    });
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

    /* 🔴 위 두 시험은 **속성만** 본다. 그래서 이 결함을 3회차 동안 못 잡았다: 열 이름의
       `position` 은 내내 `sticky` 였는데 실브라우저에서는 굴리면 사라졌다(실측 2026-08-26 ·
       홈 「오늘 마감」 12행: 176px 굴렸더니 열 이름이 정확히 176px 위로 사라졌다).
       원인은 표를 감싼 `TableContainer` 다 — 기본이 `overflow-x: auto` 라 **자기가 스크롤
       컨테이너가 되고**, sticky 는 그 상자에 붙는다. 그 상자에는 높이 제한이 없으니 절대
       굴러가지 않고, 결국 열 이름은 바깥 상자와 함께 위로 밀려 나간다.
       그래서 여기서는 «붙을 대상이 바깥에 있는가» 를 본다. */
    it("stickyHeader=true면 표를 감싼 상자가 **스스로 굴러가지 않는다**", () => {
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} stickyHeader />);
      const container = screen.getByRole("table").parentElement;
      expect(container.className).toMatch(/MuiTableContainer-root/);
      // 축 이름을 그대로 적는다 — 줄임 표기(`overflow`)는 jsdom 이 축별 값으로 펴지 않아
      // 「시험은 통과하는데 브라우저는 다르게 읽는다」가 다시 생긴다.
      expect(getComputedStyle(container).overflowX).toBe("visible");
    });

    it("stickyHeader 가 없으면 넓은 표는 그 상자가 가로로 굴린다 — 전역으로 끄지 않는다", () => {
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
      const container = screen.getByRole("table").parentElement;
      expect(getComputedStyle(container).overflowX).toBe("auto");
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

    it("type:status + Badge render 열은 td overflow:hidden 으로 표지를 자르지 않는다", () => {
      ui(
        <DataTable
          columns={[{ key: "status", label: "상태", type: "status", render: (r) => <Badge value={r.status} /> }]}
          rows={[{ id: 1, status: "진행" }]}
          rowKey={(r) => r.id}
        />,
      );
      const td = screen.getByText("진행 중").closest("td");
      expect(getComputedStyle(td).overflow).not.toBe("hidden");
    });

    it("보는 열(상태)은 가로·세로 가운데다", () => {
      ui(
        <DataTable
          columns={[{ key: "status", label: "상태", type: "status", render: (r) => <Badge value={r.status} /> }]}
          rows={[{ id: 1, status: "진행" }]}
          rowKey={(r) => r.id}
        />,
      );
      const td = screen.getByText("진행 중").closest("td");
      expect(td.getAttribute("class")).toContain("MuiTableCell-alignCenter");
      expect(getComputedStyle(td).textAlign).toBe("center");
      expect(getComputedStyle(td).verticalAlign).toBe("middle");
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

  /* 열을 접을지는 **그 표가 받은 칸**이 정한다 (D-380).
   *
   * 예전 규칙은 「뷰포트가 900~1200 이면 `hideNarrow` 열을 전부 뺀다」였고 두 방향으로
   * 틀렸다: 뷰포트는 칸이 아니고(문서 목록의 표는 1920 에서도 칸이 902px 이라 넘쳤다),
   * 전부 아니면 전무였다(90px 모자란다고 열 다섯을 지울 이유가 없다).
   *
   * jsdom 에는 배치가 없어 `clientWidth` 가 언제나 0 이다. 그래서 그 값을 시험이 직접
   * 정해 준다 — 재는 대상이 무엇인지가 이 규칙의 전부이므로, 그것을 흉내내는 것이 곧
   * 규칙을 재는 것이다. */
  describe("좁은 칸에서 접히는 열 (hideNarrow · D-380)", () => {
    const cols = [
      { key: "name", label: "이름", width: "10rem" },
      { key: "extra", label: "부가정보", width: "10rem", hideNarrow: true },
      { key: "more", label: "덤", width: "10rem", hideNarrow: true },
    ];
    const rows = [{ id: 1, name: "홍길동", extra: "부가값", more: "덤값" }];

    let boxWidth = 0;
    let original;
    beforeEach(() => {
      original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
      Object.defineProperty(HTMLElement.prototype, "clientWidth", {
        configurable: true, get() { return boxWidth; },
      });
    });
    afterEach(() => {
      if (original) Object.defineProperty(HTMLElement.prototype, "clientWidth", original);
      else delete HTMLElement.prototype.clientWidth;
      delete window.matchMedia;
    });

    /* 표가 카드로 안 접히게(뷰포트는 넓다) 두고 **칸 폭만** 정한다.
     *
     * 그리고 나서 한 틱을 흘린다 — 시험 설정의 `ResizeObserver` 대역은 관찰을 시작하면
     * 마이크로태스크로 현재 크기를 한 번 알린다(`test-setup.js`). 그것을 안 흘리면 그
     * 알림이 `act` 밖에서 도착해 경고가 난다. 실제 브라우저에서도 같은 순서다. */
    async function draw(px) {
      boxWidth = px;
      window.matchMedia = (query) => ({
        matches: false, media: query,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}, onchange: null,
        dispatchEvent: () => false,
      });
      const r = ui(<DataTable columns={cols} rows={rows} rowKey={(r2) => r2.id} />);
      await act(async () => {});
      return r;
    }

    it("칸이 넉넉하면 전부 보인다", async () => {
      await draw(600);   // 바닥 30rem = 480px
      expect(screen.getByRole("columnheader", { name: "부가정보" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "덤" })).toBeInTheDocument();
      expect(screen.queryByText(/열을 숨겼습니다/)).toBeNull();
    });

    it("🔴 모자란 만큼만 접는다 — 한 열이면 한 열이다", async () => {
      await draw(400);   // 30rem 은 안 들어가고 20rem 은 들어간다
      // 뒤에 적은 열부터 접힌다.
      expect(screen.queryByRole("columnheader", { name: "덤" })).toBeNull();
      expect(screen.getByRole("columnheader", { name: "부가정보" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "이름" })).toBeInTheDocument();
    });

    it("더 좁으면 더 접는다 — 접을 수 있는 열까지만", async () => {
      await draw(200);
      expect(screen.queryByRole("columnheader", { name: "덤" })).toBeNull();
      expect(screen.queryByRole("columnheader", { name: "부가정보" })).toBeNull();
      // `hideNarrow` 가 아닌 열은 안 접는다 — 그 표가 무엇인지 말하는 열이다.
      expect(screen.getByRole("columnheader", { name: "이름" })).toBeInTheDocument();
    });

    // PA-RC-0037 acceptance (4): 조용히 사라지면 사용자는 그 값을 못 봤다는 사실조차 모른다.
    it("접은 열이 무엇인지 표가 말한다 — 표에 적힌 순서로", async () => {
      await draw(200);
      expect(screen.getByText(/부가정보, 덤 열을 숨겼습니다/)).toBeInTheDocument();
    });

    it("접을 수 있는 열이 없으면 좁아도 안내를 안 보여준다 — REGRESSION 없음", async () => {
      boxWidth = 100;
      window.matchMedia = (q) => ({
        matches: false, media: q,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}, onchange: null,
        dispatchEvent: () => false,
      });
      ui(<DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />);
      await act(async () => {});
      expect(screen.queryByText(/열을 숨겼습니다/)).toBeNull();
    });

    it("카드 뷰에서는 폭 제약이 없으니 접힌 열도 다시 보인다", async () => {
      boxWidth = 100;
      window.matchMedia = (query) => ({
        matches: query.includes("899.95"), media: query,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}, onchange: null,
        dispatchEvent: () => false,
      });
      ui(<DataTable columns={cols} rows={rows} rowKey={(r) => r.id} />);
      await act(async () => {});
      expect(screen.getByText("부가정보")).toBeInTheDocument();
      expect(screen.getByText("덤값")).toBeInTheDocument();
    });

    it("아직 못 쟀으면(칸 폭 0) 아무 것도 안 접는다 — 열이 사라졌다 돌아오지 않는다", async () => {
      await draw(0);
      expect(screen.getByRole("columnheader", { name: "덤" })).toBeInTheDocument();
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

    it("helpTone이 주어지면 Callout 아이콘의 접근 이름이 그걸 따른다(기본은 '안내')", () => {
      const { unmount } = ui(<PageHeader title="테스트" help="일반 안내" />);
      expect(screen.getByLabelText("안내")).toBeInTheDocument();
      // 톤 이름이 **화면 글자로는** 서지 않는다 — 제목 자리는 화면이 쓸 자리다.
      expect(screen.queryByText("안내")).toBeNull();
      unmount();
      ui(<PageHeader title="테스트" help="위험한 안내" helpTone="warn" />);
      expect(screen.getByLabelText("주의")).toBeInTheDocument();
      expect(screen.queryByText("주의")).toBeNull();
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

/* 선택 신호는 면이 아니라 **선**이 말한다 (W4 → 핸드오프 계획 B-6).
 * `background.inset` 은 판 위에서는 함몰면이지만 캔버스 위에서는 더 밝고 대비가 1.055:1 이라
 * 신호가 뒤집히면서 사라진다. 판독 줄의 레일이 그 계약을 지켰고, 그 줄을 이은 측정값 타일은 판 면을 그대로 두고
 * **테두리 색**으로 지금 고른 타일을 말한다. */
describe("측정값 타일의 선택 신호", () => {
  it("지금 목록을 거르는 타일은 테두리가 달라지고, 두께와 면은 고르지 않은 타일과 같다", () => {
    ui(
      <>
        <StatusKpiTile label="열림" value={3} onClick={() => {}} selected />
        <StatusKpiTile label="완료" value={9} onClick={() => {}} selected={false} />
      </>,
    );
    const [onEl, offEl] = screen.getAllByRole("button");
    const on = getComputedStyle(onEl);
    const off = getComputedStyle(offEl);
    expect(on.borderTopStyle).toBe("solid");
    expect(on.borderTopWidth).toBe(off.borderTopWidth);   // 고를 때 타일 크기가 튀지 않는다
    expect(on.borderTopColor, "고른 타일의 테두리가 고르지 않은 타일과 같다").not.toBe(off.borderTopColor);
    /* **면은 신호를 지지 않는다.** 활성 칸이 면을 칠하면 두 어휘가 같은 것을 두 번 말한다 — 그걸 여기서 막는다. */
    expect(on.backgroundColor, `고른 타일 면 ${on.backgroundColor}`).toBe(off.backgroundColor);
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

/* D-452 · D-456 · D-457 — 머리 제목, 절차 안내 부품, 상세 키/값 줄. */
import { DetailGrid, DetailRow, GuidanceBlock } from "./kit.jsx";

describe("PageHeader — 제목은 언제나 title 이다 (D-452)", () => {
  it("옛 tab prop 을 넘겨도 h1 은 title 이고 탭 라벨은 제목에 안 들어간다", () => {
    ui(<PageHeader area="자동화와 연동" title="실행 일정" tab="목록" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("실행 일정");
    expect(screen.queryByText(/목록/)).toBeNull();
  });
});

describe("GuidanceBlock — 준비물·절차·기대 결과 (D-456)", () => {
  it("셋을 라벨과 함께 그린다", () => {
    ui(<GuidanceBlock prerequisite="계정이 있어야 합니다." steps={["하나", "둘"]} expected="목록에 나타납니다." />);
    expect(screen.getByText("필요한 것")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("기대 결과")).toBeInTheDocument();
  });

  it("셋 다 비면 아무것도 그리지 않는다 — 반례", () => {
    const { container } = ui(<GuidanceBlock steps={[]} />);
    expect(container.querySelector("[data-guidance]")).toBeNull();
  });
});

describe("DetailRow — 상세의 키/값 줄 (D-457)", () => {
  it("라벨과 값을 한 줄로 그리고 격자가 줄을 담는다", () => {
    const { container } = ui(
      <DetailGrid>
        <DetailRow label="이메일">a@b.c</DetailRow>
        <DetailRow label="역할" dense>admin</DetailRow>
      </DetailGrid>,
    );
    expect(container.querySelector("[data-detail-grid]")).not.toBeNull();
    expect(container.querySelectorAll("[data-detail-row]")).toHaveLength(2);
    expect(screen.getByText("이메일")).toBeInTheDocument();
    expect(screen.getByText("a@b.c")).toBeInTheDocument();
  });
});

/* 세그먼티드 — 밑줄 탭이 하던 일을 **면**으로 한다.
 *
 * 밑줄 탭은 칸이 넷쯤 되면 어디까지가 이 묶음인지 경계가 사라진다. 세그먼티드는 묶음
 * 자체가 면이라 경계가 언제나 보이고 고른 칸만 그 면 위로 한 겹 올라온다. 이 시험이 재는
 * 것은 그 두 겹이 실제로 다른 면인가, 그리고 **탭이었던 것이 여전히 탭인가**다. */
/* 표와 목록 안에서는 배지 대신 **점 + 낱말**이다 (확정 규약 §9).
 *
 * danger 가 자동으로 옅은 면을 얻는 규칙은 목록 **밖**(카드 머리·상세)에서 조치를 눈에
 * 띄게 하려는 것이다. 그것이 목록 안으로 들어오면 같은 줄에서 어휘가 둘로 갈린다 —
 * 「지연 18일」만 붉은 칩이고 옆의 「검증」·「계획」은 점 + 낱말이었다. */
describe("배지 — 면을 갖는가는 «자리» 가 정한다", () => {
  const faceOf = (el) => getComputedStyle(el.closest(".k-badge")).backgroundColor;
  const NO_FACE = ["transparent", "rgba(0, 0, 0, 0)"];
  const hasFace = (el) => !NO_FACE.includes(faceOf(el));

  it("danger 는 목록 밖에서 옅은 면을 갖는다 — 조치가 눈에 띄어야 하는 자리다", () => {
    const { container } = ui(<Badge value="지연" kind="danger" />);
    expect(hasFace(container.querySelector(".k-badge"))).toBe(true);
  });

  /* 🔴 이 규칙이 새던 자리가 여기다. 「표 안에서는 배지 대신 점 + 낱말」은 오래 있던
     규약인데, 그것을 지키는 일이 **호출부 106곳의 기억**에 맡겨져 있었다. AI 도우미의
     「지연 N일」이 그렇게 샜고 개발 리포트의 「지연」 열도 같은 자리였다. 지금은 그릇이
     선언하므로, 새 열이나 새 줄을 더하는 사람이 이 규약을 몰라도 지켜진다. */
  it("표 안에서는 아무 prop 없이도 면이 없다 — 그릇이 선언한다", () => {
    const { container } = ui(
      <DataTable
        columns={[{ key: "s", label: "상태", type: "status", render: (r) => <Badge value={r.s} kind="danger" /> }]}
        rows={[{ id: 1, s: "지연" }]}
        rowKey={(r) => r.id}
      />,
    );
    const badge = container.querySelector("tbody .k-badge");
    expect(badge).toBeInTheDocument();
    expect(hasFace(badge)).toBe(false);
  });

  it("목록도 같다 — 손으로 만든 목록은 FlatBadgeSurface 로 그 자리를 말한다", () => {
    const { container } = ui(
      <FlatBadgeSurface><Badge value="지연" kind="danger" /></FlatBadgeSurface>,
    );
    expect(hasFace(container.querySelector(".k-badge"))).toBe(false);
  });

  it("같은 줄의 danger 와 그 밖의 상태가 **같은 모양**이 된다", () => {
    const { container } = ui(
      <FlatBadgeSurface>
        <Badge value="지연" kind="danger" />
        <Badge value="검증" />
      </FlatBadgeSurface>,
    );
    const [lead, status] = Array.from(container.querySelectorAll(".k-badge"));
    expect(faceOf(lead)).toBe(faceOf(status));
    // 색은 잃지 않는다 — 면 대신 점과 글자가 나른다.
    expect(getComputedStyle(lead).color).not.toBe(getComputedStyle(status).color);
    expect(lead.querySelector("span[aria-hidden]")).toBeInTheDocument();
  });

  it("호출부가 자리를 이긴다 — 목록 안에서도 strong 을 적으면 면을 갖는다", () => {
    const { container } = ui(
      <FlatBadgeSurface><Badge value="검증" emphasis="strong" /></FlatBadgeSurface>,
    );
    expect(hasFace(container.querySelector(".k-badge"))).toBe(true);
  });

  it("반대 방향도 된다 — 목록 밖에서 plain 을 적으면 면이 사라진다", () => {
    const { container } = ui(<Badge value="지연" kind="danger" emphasis="plain" />);
    expect(hasFace(container.querySelector(".k-badge"))).toBe(false);
  });

  it("면이 없어도 낱말은 남는다 — 색만으로 심각도를 말하지 않는다", () => {
    ui(<FlatBadgeSurface><Badge value="지연" kind="danger" /></FlatBadgeSurface>);
    expect(screen.getByText("지연")).toBeInTheDocument();
  });
});

describe("세그먼티드", () => {
  const OPTS = [
    { value: "a", label: "오늘 요약" },
    { value: "b", label: "이번 주 요약" },
    { value: "c", label: "담당자 지정 필요", count: 3 },
  ];

  it("탭 역할과 aria-selected 를 그대로 갖는다 — 바뀐 것은 겉모습뿐이다", () => {
    ui(<Segmented ariaLabel="보기" value="b" onChange={() => {}} options={OPTS} />);
    expect(screen.getByRole("tablist", { name: "보기" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: "이번 주 요약" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "오늘 요약" })).toHaveAttribute("aria-selected", "false");
  });

  it("고른 칸만 판면으로 올라온다 — 나머지는 컨테이너 면 그대로다", () => {
    const { container } = ui(<Segmented ariaLabel="보기" value="a" onChange={() => {}} options={OPTS} />);
    const box = container.querySelector(".k-segmented");
    const [on, off] = screen.getAllByRole("tab");
    const bg = (el) => getComputedStyle(el).backgroundColor;
    // 컨테이너와 고른 칸이 **다른 면**이라야 한 겹 올라온 것으로 읽힌다.
    expect(bg(on)).not.toBe(bg(box));
    expect(["transparent", "rgba(0, 0, 0, 0)"]).toContain(bg(off));
    // 그림자도 고른 칸에만 있다.
    expect(getComputedStyle(on).boxShadow).not.toBe("none");
    expect(getComputedStyle(off).boxShadow).toBe("none");
  });

  it("안쪽 버튼 높이는 컨테이너에서 여백 둘을 뺀 값이다 — 새 숫자를 만들지 않는다", () => {
    ui(<Segmented ariaLabel="보기" value="a" onChange={() => {}} options={OPTS} />);
    // CONTROL.button(34) − 3px × 2 = 28px = 1.75rem
    expect(getComputedStyle(screen.getAllByRole("tab")[0]).height).toBe("1.75rem");
  });

  it("누르면 그 값을 돌려준다", async () => {
    const onChange = vi.fn();
    ui(<Segmented ariaLabel="보기" value="a" onChange={onChange} options={OPTS} />);
    await userEvent.click(screen.getByRole("tab", { name: /담당자 지정 필요/ }));
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("건수를 주면 라벨 옆에 함께 선다", () => {
    ui(<Segmented ariaLabel="보기" value="a" onChange={() => {}} options={OPTS} />);
    expect(screen.getByRole("tab", { name: "담당자 지정 필요 3" })).toBeInTheDocument();
  });

  it("보기가 없으면 빈 그릇을 안 그린다", () => {
    const { container } = ui(<Segmented ariaLabel="보기" value="a" onChange={() => {}} options={[]} />);
    expect(container.querySelector(".k-segmented")).toBeNull();
  });
});
