import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import {
  ActionFooter, Button, Callout, Card, ConfirmProvider, CountChip, DataTable, DotLabel, EmptyState, ErrorState,
  FormFieldCell, FIELD_ROWS, Modal, ModalFooter, ModalHeader, Segmented, ToastProvider, useConfirm,
} from "./kit.jsx";
import { FilterConditionLine, FilterSurface, FilterToggle, ToolbarRow } from "./FilterBar.jsx";
import { EntityCombobox, FilterSelect, PickerOption, SearchBox, mineFirst } from "./filters.jsx";
import { StatusSummaryCard } from "./StatusKpi.jsx";
import { TicketFace } from "./TicketFace.jsx";
import { SIGNALS } from "../lib/ticketSignals.js";
import { CONTROL, FONT_SIZE, remPx } from "./theme.js";
import { ThemeModeProvider } from "./ThemeModeProvider.jsx";

/* 핸드오프(design_handoff_clovirassist_ui) A 단계가 정본으로 세운 부품 계약.
 *
 * 부품마다 **이 부품이 없던 때 무엇이 틀렸는가**를 단언으로 적는다. 여기 있는 것은 전부 화면이
 * 부르는 공통 부품이다 — 화면 시험이 아니라 부품 시험이라, 이 파일이 초록이면 그 부품을 쓰는
 * 자리 전부가 같은 계약을 받는다(소비처 목록은 `docs/ui-renewal/COMPONENT_LEDGER.md`).
 *
 * qa-contract-change: 빈 표가 판 안 빈 상태 부품(region)이 아니라 머리 아래 한 줄 띠(band)로 선다(D-530 — 판을 흰 면으로 채우지 않는다).
 * 문구 단언은 그대로 두고, 띠가 표의 줄이며 머리가 서 있고 그림이 없다는 단언을 더한다.
 */

function ui(node) {
  return render(
    <ThemeModeProvider>
      <ToastProvider>
        <ConfirmProvider>{node}</ConfirmProvider>
      </ToastProvider>
    </ThemeModeProvider>,
  );
}

describe("Button — 이름 · 줄바꿈 · 폭", () => {
  it("핸드오프 어휘 secondary 는 default 와 **같은 버튼**이다(테두리 규칙까지)", () => {
    ui(<><Button variant="secondary">보조 A</Button><Button>보조 B</Button></>);
    const a = screen.getByRole("button", { name: "보조 A" });
    const b = screen.getByRole("button", { name: "보조 B" });
    expect(a.className).toContain("MuiButton-outlined");
    expect(getComputedStyle(a).borderColor).toBe(getComputedStyle(b).borderColor);
  });

  it("라벨은 한 줄이고 버튼은 flex 줄에서 줄어들지 않는다", () => {
    ui(<Button>아주 긴 동작 이름의 버튼</Button>);
    const st = getComputedStyle(screen.getByRole("button"));
    expect(st.whiteSpace).toBe("nowrap");
    expect(st.flexShrink).toBe("0");
  });

  it("`truncate` 를 켠 자리만 말줄임되고 전체 라벨을 title 로 든다", () => {
    ui(<Button size="sm" truncate>좁은 칸의 긴 라벨</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toHaveAttribute("title", "좁은 칸의 긴 라벨");
    expect(getComputedStyle(btn).flexShrink).toBe("1");
    const label = btn.querySelector("span.MuiBox-root");
    expect(getComputedStyle(label).textOverflow).toBe("ellipsis");
  });
});

describe("Segmented — 34 · 키보드", () => {
  const OPTS = [{ value: "a", label: "전체" }, { value: "b", label: "최근" }, { value: "c", label: "즐겨찾기" }];

  it("바깥 선은 안쪽 그림자라 높이에 더해지지 않는다(34 = 28 + 3 × 2)", () => {
    const { container } = ui(<Segmented ariaLabel="보기" value="a" onChange={() => {}} options={OPTS} />);
    const st = getComputedStyle(container.querySelector(".k-segmented"));
    expect(st.borderTopWidth === "0px" || st.borderTopWidth === "").toBe(true);
    expect(st.boxShadow).toContain("inset");
    expect(st.paddingTop).toBe("3px");
  });

  it("탭 순서에 한 번만 서고 화살표 · Home · End 로 옮기면 그 칸이 선택된다", async () => {
    function Harness() {
      const [v, setV] = React.useState("a");
      return <Segmented ariaLabel="보기" value={v} onChange={setV} options={OPTS} />;
    }
    ui(<Harness />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
    tabs[0].focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "최근" })).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "최근" }));
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "즐겨찾기" })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "전체" })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "즐겨찾기" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("모달 머리와 발 · ActionFooter", () => {
  it("모달 제목은 판 제목 단계(1.0625rem / 700)다", () => {
    ui(<ModalHeader title="회차 추가" onClose={() => {}} />);
    const st = getComputedStyle(screen.getByText("회차 추가").closest("h2"));
    expect(st.fontSize).toBe(FONT_SIZE.cardTitle);
    expect(st.fontWeight).toBe("700");
  });

  it("발은 함몰면 + 위 선의 주인이 하나이고 취소는 흰 면(default)이다", () => {
    const { container } = ui(<ModalFooter onCancel={() => {}} onSubmit={() => {}} submitLabel="저장" />);
    const footers = container.querySelectorAll("[data-action-footer]");
    expect(footers).toHaveLength(1);
    expect(footers[0].getAttribute("data-action-footer")).toBe("modal");
    const cancel = screen.getByRole("button", { name: "취소" });
    expect(cancel.className).toContain("MuiButton-outlined");
    expect(cancel.className).not.toContain("MuiButton-text");
  });

  it("발 안의 발은 맨 줄로 선다 — 면 · 선 · 여백의 주인이 둘이 되지 않는다", () => {
    const { container } = ui(
      <ActionFooter placement="card"><ActionFooter><Button>안쪽</Button></ActionFooter></ActionFooter>,
    );
    expect(container.querySelectorAll("[data-action-footer]")).toHaveLength(1);
  });

  it("판 발이 마지막 줄인 판은 세로 흐름이고 본문 상자가 남는 높이를 먹는다 — 짝 격자에서 늘어난 판의 발이 바닥에 선다", () => {
    const { container } = ui(
      <>
        <Card data-testid="footed">
          <p>본문 한 줄</p>
          <p>본문 두 줄</p>
          <ActionFooter placement="card"><Button variant="primary">저장</Button></ActionFooter>
        </Card>
        <Card data-testid="plain"><p>발 없는 판</p></Card>
      </>,
    );
    const footed = screen.getByTestId("footed");
    expect(getComputedStyle(footed).display).toBe("flex");
    expect(getComputedStyle(footed).flexDirection).toBe("column");
    const body = footed.querySelector(":scope > [data-card-body]");
    expect(body).not.toBeNull();
    expect(getComputedStyle(body).flexGrow).toBe("1");
    expect(body.querySelectorAll("p")).toHaveLength(2);
    // 발은 본문 상자 밖, 판의 직계 마지막 줄이다 — 판 여백을 거스르는 음수 여백이 판 기준으로 선다.
    expect(footed.lastElementChild.getAttribute("data-action-footer")).toBe("card");
    // 발이 없는 판은 예전 그대로다(흐름 · 상자 없음).
    const plain = screen.getByTestId("plain");
    expect(getComputedStyle(plain).display).not.toBe("flex");
    expect(plain.querySelector("[data-card-body]")).toBeNull();
    expect(container.querySelectorAll("[data-card-body]")).toHaveLength(1);
  });

  it("되돌릴 수 없는 확인은 제목 앞에 주의 표지를 달고 **취소**가 기본 포커스다", async () => {
    function Trigger() {
      const confirm = useConfirm();
      return <Button onClick={() => confirm("지울까요?", { danger: true, confirmLabel: "지우기" })}>열기</Button>;
    }
    ui(<Trigger />);
    await userEvent.click(screen.getByRole("button", { name: "열기" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("img", { name: "주의" })).toBeInTheDocument();
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "취소" }));
    // 표지는 머리 줄에 서되 대화상자의 **이름**에는 섞이지 않는다 — 이름은 제목 글자 그대로다.
    expect(screen.getByRole("dialog", { name: "확인" })).toBe(dialog);
  });
});

describe("모달의 초점 (P-134)", () => {
  it("스스로 열린 모달은 판이 아니라 몸이 초점을 받고, 몸에는 초점 고리가 없다", () => {
    ui(<Modal open title="결과 발표" onClose={() => {}}><p>당첨을 축하합니다.</p></Modal>);
    const dialog = screen.getByRole("dialog");
    const body = dialog.querySelector(".MuiDialogContent-root");
    expect(document.activeElement).toBe(body);
    expect(body.getAttribute("tabindex")).toBe("-1");
    const cls = [...body.classList].find((c) => c.startsWith("css-"));
    const rules = [...document.styleSheets].flatMap((sh) => [...sh.cssRules].map((r) => r.cssText));
    expect(rules.some((t) => t.startsWith(`.${cls}:focus-visible`) && /outline:\s*none/.test(t)), "몸의 초점 고리를 지우지 않았다").toBe(true);
  });

  it("안의 칸이 이미 초점을 받았으면 몸이 가로채지 않는다", () => {
    ui(<Modal open title="이름 바꾸기" onClose={() => {}}><input aria-label="새 이름" autoFocus /></Modal>);
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "새 이름" }));
  });
});

describe("값 표시 — DotLabel · CountChip", () => {
  it("점은 aria-hidden 이고 낱말은 한 줄 말줄임 + title 이다", () => {
    const { container } = ui(<DotLabel label="회의록" tone="info" />);
    const root = container.querySelector("[data-dot-label]");
    expect(root.querySelector("[data-status-dot]")).toHaveAttribute("aria-hidden", "true");
    expect(root).toHaveAttribute("title", "회의록");
    expect(getComputedStyle(root).whiteSpace).toBe("nowrap");
  });

  it("건수 칩은 내용과 무관하게 한 높이(20)이고 compact 는 18 이다", () => {
    const { container } = ui(<><CountChip value={3} /><CountChip value="12,345건" /><CountChip value={4} compact /></>);
    const chips = [...container.querySelectorAll("[data-count-chip]")];
    expect(getComputedStyle(chips[0]).height).toBe(remPx(20));
    expect(getComputedStyle(chips[1]).height).toBe(remPx(20));
    expect(chips[2].getAttribute("data-count-chip")).toBe("compact");
    expect(getComputedStyle(chips[2]).height).toBe(remPx(18));
  });
});

describe("필터 바 — 줄 칸 · 토글 · 조건 줄", () => {
  it("필터 바 안의 셀렉트는 이름이 칸 안 접두로 서고 노치 라벨이 없다 — 접근 이름은 그대로다", () => {
    const { container } = ui(
      <FilterSurface>
        <ToolbarRow>
          <FilterSelect label="우선순위" value="" onChange={() => {}} options={["높음", "낮음"]} />
        </ToolbarRow>
      </FilterSurface>,
    );
    expect(screen.getByRole("combobox", { name: "우선순위" })).toBeInTheDocument();
    expect(container.querySelector("label.MuiInputLabel-root")).toBeNull();
    expect(screen.getByText("우선순위")).toBeInTheDocument();
    expect(screen.getByText("전체")).toBeInTheDocument();
  });

  it("🔴 빈 값 낱말이 이름으로 시작하면 칸 안에서 이름을 두 번 읽지 않는다 — 메뉴 글자는 그대로다", async () => {
    const user = userEvent.setup();
    const { container } = ui(
      <FilterSurface>
        <ToolbarRow>
          <FilterSelect label="역할" value="" onChange={() => {}} options={["관리자"]} allLabel="역할: 전체" />
          <FilterSelect label="분류" value="" onChange={() => {}} options={["회의록"]} allLabel="분류 전체" />
        </ToolbarRow>
      </FilterSurface>,
    );
    const role = screen.getByRole("combobox", { name: "역할" });
    // `/users` 에서 「역할 역할: 전체」로 같은 낱말이 두 번 섰다(handoff-a 긴 데이터 캡처).
    expect(role.textContent).toBe("역할전체");
    expect(screen.getByRole("combobox", { name: "분류" }).textContent).toBe("분류전체");
    expect(container.textContent).not.toContain("역할: 전체");
    await user.click(role);
    expect(await screen.findByRole("option", { name: "역할: 전체" })).toBeInTheDocument();
  });

  it("필터 바 밖(폼)의 셀렉트는 예전 모양 그대로다", () => {
    const { container } = ui(<FilterSelect label="우선순위" value="" onChange={() => {}} options={["높음"]} layout="form" />);
    expect(container.querySelector("label.MuiInputLabel-root")).not.toBeNull();
  });

  it("필터 바 안의 검색형 칸도 접두 이름과 같은 접근 이름을 갖는다", () => {
    ui(
      <FilterSurface>
        <ToolbarRow>
          <EntityCombobox label="프로젝트" value="" onChange={() => {}} options={[{ value: "p", label: "포털 개편" }]} />
          <SearchBox value="" onSearch={() => {}} placeholder="검색" ariaLabel="티켓 검색" />
        </ToolbarRow>
      </FilterSurface>,
    );
    expect(screen.getByRole("combobox", { name: "프로젝트" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "티켓 검색" })).toBeInTheDocument();
  });

  it("검색 슬롯 규칙은 줄의 **직계** 검색 칸에만 걸린다", () => {
    const { container } = ui(<ToolbarRow><SearchBox value="" onSearch={() => {}} ariaLabel="검색" /></ToolbarRow>);
    const row = container.querySelector("[data-search-slot]");
    const search = row.querySelector(":scope > [data-filter-kind=search]");
    expect(search).not.toBeNull();
  });

  it("토글은 34 버튼이고 좁히기는 aria-pressed, 패널은 aria-expanded 로 말한다", () => {
    ui(<>
      <FilterToggle pressed onClick={() => {}}>내 티켓만</FilterToggle>
      <FilterToggle expanded={false} onClick={() => {}}>상세 필터</FilterToggle>
    </>);
    const mine = screen.getByRole("button", { name: "내 티켓만" });
    const adv = screen.getByRole("button", { name: "상세 필터" });
    expect(mine).toHaveAttribute("aria-pressed", "true");
    expect(mine).not.toHaveAttribute("aria-expanded");
    expect(adv).toHaveAttribute("aria-expanded", "false");
    expect(adv).not.toHaveAttribute("aria-pressed");
    expect(mine.className).toContain("MuiButton-sizeMedium");
  });

  it("조건 줄은 조건이 있을 때만 서고 「조건 N개에 맞는 결과가 M건입니다.」로 시작한다", () => {
    const { container, rerender } = ui(<FilterConditionLine total={21} chips={[]} />);
    expect(container.querySelector("[data-condition-line]")).toBeNull();
    rerender(
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <FilterConditionLine total={21} chips={[{ key: "s", label: "상태 계획", onDelete: () => {} }]} onClearAll={() => {}} />
      </ConfirmProvider></ToastProvider></ThemeModeProvider>,
    );
    expect(screen.getByText("조건 1개에 맞는 결과가 21건입니다.")).toBeInTheDocument();
    expect(getComputedStyle(container.querySelector("[data-condition-line]")).borderTopWidth).toBe("1px");
  });
});

describe("검색 팝오버 항목 — PickerOption", () => {
  it("항목은 32 한 줄이고 고른 항목에만 체크가 보인다", () => {
    const { container } = ui(
      <ul>
        <PickerOption liProps={{ key: "a" }} label="김정미" secondary="플랫폼개발팀" selected />
        <PickerOption liProps={{ key: "b" }} label="박도윤" secondary="인프라운영팀" selected={false} />
      </ul>,
    );
    const rows = [...container.querySelectorAll("[data-picker-option]")];
    expect(getComputedStyle(rows[0]).minHeight).toBe(remPx(CONTROL.menuItem));
    const checks = rows.map((r) => getComputedStyle(r.querySelector("svg")).visibility);
    expect(checks).toEqual(["visible", "hidden"]);
    expect(rows[0]).toHaveAttribute("title", "김정미, 플랫폼개발팀");
  });

  it("내 계정이 맨 위로 온다 — 나머지 순서는 그대로다", () => {
    const opts = [{ value: "a" }, { value: "me" }, { value: "b" }];
    expect(mineFirst(opts, "me").map((o) => o.value)).toEqual(["me", "a", "b"]);
    expect(mineFirst(opts, "").map((o) => o.value)).toEqual(["a", "me", "b"]);
  });
});

describe("상태 요약 — 값 하나 갈래", () => {
  it("부분도 신호도 없으면 큰 숫자 하나만 선다(비율 바 없음)", () => {
    const { container } = ui(<StatusSummaryCard ariaLabel="안 읽음" title="알림" total="12" totalLabel="안 읽음" />);
    expect(container.querySelector("[data-summary-single]")).not.toBeNull();
    expect(container.querySelector("[data-ratio-bar]")).toBeNull();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});

describe("표 · 폼 · 오류 · 메시지 박스", () => {
  it("rowHeight=tall 의 행 바닥은 76 이다(고정 높이가 아니다)", () => {
    const { container } = ui(
      <DataTable columns={[{ key: "t", label: "제목", type: "title" }]} rows={[{ t: "가" }]} rowKey={() => "r"} rowHeight="tall" />,
    );
    const td = container.querySelector("tbody td");
    expect(getComputedStyle(td).height).toBe(remPx(CONTROL.tableRowTall));
  });

  it("빈 표는 머리 아래 한 줄 띠로 선다 — 문구는 그대로다(D-530)", () => {
    const { container } = ui(<DataTable columns={[{ key: "t", label: "제목" }]} rows={[]} rowKey={() => "r"} empty="휴지통이 비어 있습니다." />);
    const band = container.querySelector('[data-empty-layout="band"]');
    expect(band).not.toBeNull();
    // 띠는 표의 줄이고 머리가 그 위에 서 있다 — 판을 흰 면으로 채우는 빈 상태(region)가 아니다.
    expect(band.closest("tr[data-empty-band]")).not.toBeNull();
    expect(screen.getByRole("columnheader", { name: "제목" })).toBeInTheDocument();
    expect(container.querySelector('[data-empty-layout="region"]')).toBeNull();
    expect(band.querySelector("img")).toBeNull();
    expect(screen.getByText("휴지통이 비어 있습니다.")).toBeInTheDocument();
  });

  it("폼 칸은 라벨 20 · 필드 36 · 도움말 auto 트랙이고 오류가 도움말 자리를 쓴다", () => {
    const { container } = ui(
      <FormFieldCell label="예상 WD" htmlFor="wd" help="숫자로 씁니다." error="1 이상을 넣어 주세요.">
        <input id="wd" />
      </FormFieldCell>,
    );
    const cell = container.querySelector("[data-form-field]");
    expect(getComputedStyle(cell).gridTemplateRows).toBe(FIELD_ROWS);
    expect(screen.getByRole("alert")).toHaveTextContent("1 이상을 넣어 주세요.");
    expect(screen.queryByText("숫자로 씁니다.")).toBeNull();
  });

  it("모르는 size 의 오류 상태는 개발 모드에서 멈춘다", () => {
    const quiet = console.error;
    console.error = () => {};
    try {
      expect(() => render(<ErrorState error={new Error("x")} size="sm" />)).toThrow(/모르는 size/);
    } finally {
      console.error = quiet;
    }
  });

  it("판 안 오류의 다시 시도는 인라인 30 이고 채운 버튼이 아니다", () => {
    ui(<ErrorState layout="region" error={Object.assign(new Error("실패"), { status: 503 })} onRetry={() => {}} />);
    const retry = screen.getByRole("button", { name: "다시 시도" });
    expect(retry.className).toContain("MuiButton-sizeSmall");
    expect(retry.className).not.toContain("MuiButton-contained");
  });

  it("inline 메시지 박스는 톤 이름 낱말을 그리지 않는다 — 아이콘의 접근 이름이 말한다", () => {
    ui(<Callout tone="warn" variant="inline">문장 안의 안내입니다.</Callout>);
    // 아이콘의 SVG `<title>` 은 낭독용 이름이라 화면 글자가 아니다 — 그것만 뺀다.
    expect(screen.queryByText("주의", { ignore: "title, script, style" })).toBeNull();
    expect(screen.getByRole("img", { name: "주의" })).toBeInTheDocument();
  });
});

describe("칸반 카드 — 점과 낱말 · 발 실선", () => {
  it("우선순위와 신호가 점과 낱말이고 면 배지가 없다", () => {
    const { container } = ui(
      <TicketFace
        card={{ key: "A-1", title: "제목", project: "포털", due: "2026-09-01", priority: "urgent", assignees: [] }}
        signals={[SIGNALS.overdue]}
      />,
    );
    expect(container.querySelector(".k-badge")).toBeNull();
    expect(container.querySelectorAll("[data-dot-label]").length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector('[data-signal="overdue"]')).not.toBeNull();
    const card = container.querySelector('[data-card-kind="ticket"]');
    expect(card).not.toBeNull();
    const footer = [...card.querySelectorAll("div")].find((d) => getComputedStyle(d).borderTopWidth === "1px");
    expect(footer, "마감 · WD · 담당자 발 위에 실선이 없다").toBeTruthy();
  });
});

/* 다크 모드의 클로비 바탕 (핸드오프 README 다크 모드 절 · RULES §13 · 계획 F).
 * 빈 상태 · 오류 상태 그림은 밝은 바탕을 기준으로 그린 자산이라 다크에서는 함몰면 위에 놓는다. 치수는 두 모드가
 * 같아야 하므로 면 · 모서리 · 안쪽 선(그림자)만 칠하고 여백은 그대로다. 라이트와 그림 없는 빈 상태는 칠하지 않는다. */
describe("다크 모드 — 빈 상태 · 오류 상태 그림의 바탕", () => {
  /* 테마 모드는 `<html data-theme>` 가 정하고 공급자가 그 속성을 지켜본다 — 렌더 전에 세우고, 시험이 끝난 뒤에 걷는다
     (렌더 중에 걷으면 공급자가 라이트로 되돌린다). */
  const inMode = (mode, node) => {
    document.documentElement.setAttribute("data-theme", mode);
    return ui(node);
  };
  afterEach(() => { document.documentElement.removeAttribute("data-theme"); });

  it("다크에서 그림이 서는 빈 상태는 함몰면 · 모서리 6 · 안쪽 선이고, 여백은 라이트와 같다", () => {
    const dark = inMode("dark", <EmptyState title="아직 티켓이 없습니다" art="tickets" />);
    const darkBox = dark.container.querySelector(".k-empty");
    const darkStyle = getComputedStyle(darkBox);
    expect(darkStyle.backgroundColor).toBe("rgb(28, 33, 54)");
    expect(darkStyle.borderRadius).toBe("6px");
    expect(darkStyle.boxShadow).toContain("inset");
    const darkPad = [darkStyle.paddingTop, darkStyle.paddingLeft];
    dark.unmount();

    const light = inMode("light", <EmptyState title="아직 티켓이 없습니다" art="tickets" />);
    const lightStyle = getComputedStyle(light.container.querySelector(".k-empty"));
    expect(lightStyle.backgroundColor).not.toBe("rgb(28, 33, 54)");
    expect(lightStyle.boxShadow === "" || lightStyle.boxShadow === "none").toBe(true);
    expect([lightStyle.paddingTop, lightStyle.paddingLeft]).toEqual(darkPad);
  });

  it("그림 없는 빈 상태(조건 0건)는 다크에서도 바탕을 받지 않는다", () => {
    const { container } = inMode("dark", <EmptyState title="조건에 맞는 항목이 없습니다" />);
    const st = getComputedStyle(container.querySelector(".k-empty"));
    expect(st.backgroundColor).not.toBe("rgb(28, 33, 54)");
    expect(st.boxShadow === "" || st.boxShadow === "none").toBe(true);
  });

  it("다크에서 그림이 서는 오류 상태도 함몰면 위에 놓이고, 좁은 자리(inline)는 칠하지 않는다", () => {
    const region = inMode("dark", <ErrorState error={new Error("연결이 끊겼습니다.")} layout="region" />);
    expect(getComputedStyle(region.container.querySelector(".k-empty")).backgroundColor).toBe("rgb(28, 33, 54)");
    region.unmount();
    const inline = inMode("dark", <ErrorState error={new Error("연결이 끊겼습니다.")} layout="inline" />);
    expect(getComputedStyle(inline.container.querySelector(".k-empty")).backgroundColor).not.toBe("rgb(28, 33, 54)");
  });
});
