import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import {
  Badge, Button, Callout, ConfirmProvider, DataTable, EmptyState, ErrorState,
  FormField, Modal, PageHeader, StatCard, ToastProvider, statusKind, statusText,
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

  it("danger는 error 색으로, ghost는 텍스트 버튼으로 간다", () => {
    ui(<><Button variant="danger">삭제</Button><Button variant="ghost">취소</Button></>);
    expect(screen.getByRole("button", { name: "삭제" })).toHaveClass("MuiButton-containedError");
    expect(screen.getByRole("button", { name: "취소" })).toHaveClass("MuiButton-text");
  });
});

describe("심각도를 색만으로 전하지 않는다 (WCAG 1.4.1)", () => {
  it("Callout은 아이콘이 아니라 텍스트 라벨로 톤을 알린다", () => {
    ui(<Callout tone="danger">연결이 끊어졌습니다</Callout>);
    expect(screen.getByText("오류")).toBeInTheDocument();
    expect(screen.getByText("연결이 끊어졌습니다")).toBeInTheDocument();
  });

  it("StatCard는 위험/주의를 글자로도 표시한다", () => {
    ui(<StatCard value={3} label="지연" kind="danger" />);
    expect(screen.getByText("위험")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("누를 수 있는 StatCard만 버튼이 되고 눌림 상태를 알린다", async () => {
    const onClick = vi.fn();
    ui(<StatCard value={1} label="열린 티켓" onClick={onClick} active />);
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
    expect(screen.getByRole("link", { name: "로그인 화면으로" })).toHaveAttribute("href", "/login");
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
