import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

import {
  ActionFooter, Button, Callout, ConfirmProvider, CountChip, DataTable, DotLabel, ErrorState,
  FormFieldCell, FIELD_ROWS, ModalFooter, ModalHeader, Segmented, ToastProvider, useConfirm,
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

  it("조건 줄은 조건이 있을 때만 서고 「조건 N개, 결과 M건」으로 시작한다", () => {
    const { container, rerender } = ui(<FilterConditionLine total={21} chips={[]} />);
    expect(container.querySelector("[data-condition-line]")).toBeNull();
    rerender(
      <ThemeModeProvider><ToastProvider><ConfirmProvider>
        <FilterConditionLine total={21} chips={[{ key: "s", label: "상태 계획", onDelete: () => {} }]} onClearAll={() => {}} />
      </ConfirmProvider></ToastProvider></ThemeModeProvider>,
    );
    expect(screen.getByText("조건 1개, 결과 21건")).toBeInTheDocument();
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

  it("빈 표는 판 안 빈 상태 부품(region)으로 선다 — 문구는 그대로다", () => {
    const { container } = ui(<DataTable columns={[{ key: "t", label: "제목" }]} rows={[]} rowKey={() => "r"} empty="휴지통이 비어 있습니다." />);
    expect(container.querySelector('[data-empty-layout="region"]')).not.toBeNull();
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
