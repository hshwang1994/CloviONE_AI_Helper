/* 전문 고르개 셋 — TagPicker · ProjectPicker · UserPicker (§15.3).
 *
 * 이 시험이 고정하는 것:
 *  1. UserPicker 는 아바타 + 이름 + 부서를 그린다(REAUDIT §15.3 «필수 기능»).
 *  2. ProjectPicker 는 이름과 코드로 검색하고 코드를 보조줄로 보여 준다.
 *  3. TagPicker 는 옵션마다 사용 문서 수를 보여 주고, 없는 이름을 치면 "추가" 후보가
 *     생기며, 그것을 고르면 그 이름 그대로 값에 들어간다(새 태그를 서버가 실제로 만드는
 *     것은 문서 저장 시점의 `tags.ensure` — 여기서는 화면이 그 이름을 값에 담는 것만 본다).
 *  4. 세 고르개의 검색은 서버와 같은 접기다(`lib/search.js`) — 공백 · 대소문자 · 전각 표기가 결과를 바꾸지 않는다.
 *     태그의 「추가」 판정만은 검색이 아니라 정체성(서버 `slugify`)이다 — 앞뒤 공백이나 연속 공백만 다른 이름은 같은
 *     태그이고, 「현황 제외」와 「현황제외」처럼 공백이 있고 없고가 다른 이름은 다른 태그다.
 */
import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const apiMock = vi.fn();
vi.mock("../lib/api.js", () => ({ api: (...args) => apiMock(...args), setCsrf: () => {} }));

import { createClovirTheme } from "./theme.js";
import { UserPicker } from "./UserPicker.jsx";
import { ProjectPicker } from "./ProjectPicker.jsx";
import { TagPicker, tagSlug } from "./TagPicker.jsx";

function withProviders(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={createClovirTheme()}>{ui}</ThemeProvider>
    </QueryClientProvider>,
  );
}

const CANDIDATES = [
  { user_id: "u-1", display_name: "김하나", dept: "개발팀", title: "책임", avatar_url: "/a.png" },
  { user_id: "u-2", display_name: "이둘", dept: "운영팀", title: "매니저", avatar_url: null },
];

describe("UserPicker", () => {
  it("아바타·이름·부서가 옵션 줄에 함께 그려진다", async () => {
    const user = userEvent.setup();
    withProviders(
      <UserPicker candidates={CANDIDATES} value={[]} onChange={() => {}} multiple />,
    );
    await user.click(screen.getByLabelText("담당자"));
    const option = await screen.findByRole("option", { name: /김하나/ });
    expect(option.textContent).toMatch(/개발팀/);
    expect(option.querySelector(".k-avatar")).toBeTruthy();
  });

  it("고르면 onChange 가 user_id 배열을 받는다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    withProviders(
      <UserPicker candidates={CANDIDATES} value={[]} onChange={onChange} multiple />,
    );
    await user.click(screen.getByLabelText("담당자"));
    await user.click(await screen.findByRole("option", { name: /이둘/ }));
    expect(onChange).toHaveBeenCalledWith(["u-2"]);
  });

  /* 사람 찾기는 서버 검색과 같은 접기다(`lib/search.js`) — 공백 · 대소문자 · 전각 표기가 달라도 같은 사람이 남고, 목록 줄이
     함께 보여 주는 소속으로도 찾는다. */
  it("이름을 붙여 치든 띄워 치든, 대소문자 · 전각 표기가 달라도 같은 사람이 남는다", async () => {
    const people = [
      ...CANDIDATES,
      { user_id: "u-3", display_name: "Park Woon", dept: "ClovirONE팀", title: "매니저", avatar_url: null },
    ];
    const user = userEvent.setup();
    withProviders(<UserPicker candidates={people} value={[]} onChange={() => {}} multiple />);
    const input = screen.getByLabelText("담당자");
    await user.click(input);
    const shown = async () => (await screen.findAllByRole("option")).map((o) => o.textContent);

    for (const typed of ["김 하나", "김하나", " 김  하나 "]) {
      await user.clear(input);
      await user.type(input, typed);
      const names = await shown();
      expect(names, typed).toHaveLength(1);
      expect(names[0]).toMatch(/김하나/);
    }
    for (const typed of ["parkwoon", "PARK WOON", "ｐａｒｋ ｗｏｏｎ", "clovirone"]) {
      await user.clear(input);
      await user.type(input, typed);
      const names = await shown();
      expect(names, typed).toHaveLength(1);
      expect(names[0]).toMatch(/Park Woon/);
    }
    await user.clear(input);
    await user.type(input, "운영 팀");
    const byDept = await shown();
    expect(byDept).toHaveLength(1);
    expect(byDept[0]).toMatch(/이둘/);
  });
});

describe("ProjectPicker", () => {
  it("이름을 라벨로, 코드를 보조줄로 그린다", async () => {
    apiMock.mockResolvedValue({
      items: [{ id: "p-1", name: "알파 프로젝트", code: "AAAAAA" }],
      total: 1,
    });
    const user = userEvent.setup();
    withProviders(<ProjectPicker value="" onChange={() => {}} />);
    await user.click(screen.getByLabelText("프로젝트"));
    const option = await screen.findByRole("option", { name: /알파 프로젝트/ });
    expect(option.textContent).toMatch(/AAAAAA/);
  });

  /* 코드는 후보의 보조 글자(`secondary`)다. MUI 기본 필터는 이름만 봐서 머리 주석의 「검색(이름·코드)」 중 코드 검색이
     실제로는 동작하지 않았다 — 이제 보조 글자도 칸마다 따로 본다. */
  it("코드로도 찾고, 이름은 공백 · 대소문자를 가리지 않는다", async () => {
    apiMock.mockResolvedValue({
      items: [
        { id: "p-1", name: "알파 프로젝트", code: "AAAAAA" },
        { id: "p-2", name: "베타 프로젝트", code: "BBBBBB" },
        { id: "p-3", name: "ClovirONE 전환", code: "CCCCCC" },
      ],
      total: 3,
    });
    const user = userEvent.setup();
    withProviders(<ProjectPicker value="" onChange={() => {}} />);
    const input = screen.getByLabelText("프로젝트");
    await user.click(input);
    await screen.findByRole("option", { name: /알파 프로젝트/ });
    const shown = async () => (await screen.findAllByRole("option")).map((o) => o.textContent);

    for (const [typed, want] of [
      ["bbbbbb", /베타 프로젝트/],
      ["BBB", /베타 프로젝트/],
      ["베타프로젝트", /베타 프로젝트/],
      [" 알파   프로젝트 ", /알파 프로젝트/],
      ["CLOVIRONE", /ClovirONE 전환/],
      ["ｃｃｃｃｃｃ", /ClovirONE 전환/],
    ]) {
      await user.clear(input);
      await user.type(input, typed);
      const names = await shown();
      expect(names, typed).toHaveLength(1);
      expect(names[0], typed).toMatch(want);
    }
  });
});

describe("TagPicker", () => {
  const TAGS = { items: [
    { id: "t-1", name: "Docker", slug: "docker", document_count: 14 },
    { id: "t-2", name: "Kubernetes", slug: "kubernetes", document_count: 9 },
  ] };

  it("옵션마다 사용 문서 수를 보여 준다", async () => {
    apiMock.mockResolvedValue(TAGS);
    const user = userEvent.setup();
    withProviders(<TagPicker value={[]} onChange={() => {}} />);
    await user.click(screen.getByLabelText("태그"));
    const option = await screen.findByRole("option", { name: /Docker/ });
    expect(option.textContent).toMatch(/14건/);
  });

  it("없는 이름을 치면 «추가» 후보가 생기고, 고르면 그 이름이 값에 들어간다", async () => {
    apiMock.mockResolvedValue(TAGS);
    const user = userEvent.setup();
    const onChange = vi.fn();
    withProviders(<TagPicker value={[]} onChange={onChange} />);
    const input = screen.getByLabelText("태그");
    await user.click(input);
    await user.type(input, "Ansible");
    const created = await screen.findByRole("option", { name: /"Ansible" 추가/ });
    await user.click(created);
    expect(onChange).toHaveBeenCalledWith(["Ansible"]);
  });

  it("이미 있는 태그 이름을 치면 «추가» 후보가 안 생긴다", async () => {
    apiMock.mockResolvedValue(TAGS);
    const user = userEvent.setup();
    withProviders(<TagPicker value={[]} onChange={() => {}} />);
    const input = screen.getByLabelText("태그");
    await user.click(input);
    await user.type(input, "Docker");
    await waitFor(() => expect(screen.getByRole("option", { name: /^Docker/ })).toBeTruthy());
    expect(screen.queryByText(/추가/)).toBeNull();
  });

  /* 목록 거르기는 **검색**(접기)이고 「추가」 판정은 **정체성**(서버 `tags.py::slugify`)이다. 접기는 공백을 지우지만 서버는
     「현황 제외」와 「현황제외」를 다른 태그로 둔다 — 그래서 붙여 친 이름은 비슷한 태그를 목록에 보여 주면서도 새 태그로 만들 수
     있어야 하고, 공백만 다른 이름(끝 공백 · 연속 공백)은 서버가 같은 태그로 보므로 「추가」를 세우지 않는다. */
  const SPACED = { items: [
    { id: "t-3", name: "현황 제외", slug: "현황 제외", document_count: 3 },
    { id: "t-1", name: "Docker", slug: "docker", document_count: 14 },
  ] };

  it("붙여 친 이름은 공백이 든 태그를 목록에 보여 주고, 새 태그로 만들 수도 있다", async () => {
    apiMock.mockResolvedValue(SPACED);
    const user = userEvent.setup();
    const onChange = vi.fn();
    withProviders(<TagPicker value={[]} onChange={onChange} />);
    const input = screen.getByLabelText("태그");
    await user.click(input);
    await user.type(input, "현황제외");
    expect(await screen.findByRole("option", { name: /^현황 제외/ })).toBeTruthy();
    const created = await screen.findByRole("option", { name: /"현황제외" 추가/ });
    await user.click(created);
    expect(onChange).toHaveBeenCalledWith(["현황제외"]);
  });

  it("공백만 다른 이름(연속 공백 · 끝 공백)에는 「추가」가 서지 않는다 — 서버가 같은 태그로 본다", async () => {
    apiMock.mockResolvedValue(SPACED);
    const user = userEvent.setup();
    withProviders(<TagPicker value={[]} onChange={() => {}} />);
    const input = screen.getByLabelText("태그");
    await user.click(input);
    for (const typed of ["현황  제외", "현황 제외 ", " 현황 제외"]) {
      await user.clear(input);
      await user.type(input, typed);
      await waitFor(() => expect(screen.getByRole("option", { name: /^현황 제외/ })).toBeTruthy());
      expect(screen.queryByText(/추가/), typed).toBeNull();
    }
  });

  it("대소문자 · 전각 표기만 다른 이름에도 「추가」가 서지 않는다", async () => {
    apiMock.mockResolvedValue(SPACED);
    const user = userEvent.setup();
    withProviders(<TagPicker value={[]} onChange={() => {}} />);
    const input = screen.getByLabelText("태그");
    await user.click(input);
    for (const typed of ["DOCKER", "docker", "ｄｏｃｋｅｒ"]) {
      await user.clear(input);
      await user.type(input, typed);
      await waitFor(() => expect(screen.getByRole("option", { name: /^Docker/ })).toBeTruthy());
      expect(screen.queryByText(/추가/), typed).toBeNull();
    }
  });
});

describe("tagSlug — 서버 `app/knowledge/tags.py::slugify` 와 같은 정체성", () => {
  it("앞뒤 공백을 걷고 이어진 공백을 한 칸으로 접는다 — 공백을 지우지는 않는다", () => {
    expect(tagSlug("  현황   제외 ")).toBe("현황 제외");
    expect(tagSlug("현황\u{3000}제외")).toBe("현황 제외");
    expect(tagSlug("현황제외")).toBe("현황제외");
    expect(tagSlug("현황제외")).not.toBe(tagSlug("현황 제외"));
  });

  it("NFKC 와 casefold 로 표기를 모은다", () => {
    expect(tagSlug("ＤＯＣＫＥＲ")).toBe("docker");
    expect(tagSlug("Docker")).toBe("docker");
    expect(tagSlug("\u{1112}\u{1167}\u{11AB}\u{1112}\u{116A}\u{11BC}")).toBe("현황");
    // casefold 가 toLowerCase 와 갈리는 두 글자 — 서버는 ß 를 ss 로, ς 를 σ 로 접는다.
    expect(tagSlug("Straße")).toBe("strasse");
    expect(tagSlug("STRASSE")).toBe("strasse");
    expect(tagSlug("ΟΔΟΣ")).toBe(tagSlug("οδοσ"));
  });

  it("값이 없으면 빈 글자다 — 빈 이름에는 「추가」가 서지 않는다", () => {
    expect(tagSlug("")).toBe("");
    expect(tagSlug("   ")).toBe("");
    expect(tagSlug(undefined)).toBe("");
  });
});
