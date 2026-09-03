/* 전문 고르개 셋 — TagPicker · ProjectPicker · UserPicker (§15.3).
 *
 * 이 시험이 고정하는 것:
 *  1. UserPicker 는 아바타 + 이름 + 부서를 그린다(REAUDIT §15.3 «필수 기능»).
 *  2. ProjectPicker 는 이름으로 검색하고 코드를 보조줄로 보여 준다.
 *  3. TagPicker 는 옵션마다 사용 문서 수를 보여 주고, 없는 이름을 치면 "추가" 후보가
 *     생기며, 그것을 고르면 그 이름 그대로 값에 들어간다(새 태그를 서버가 실제로 만드는
 *     것은 문서 저장 시점의 `tags.ensure` — 여기서는 화면이 그 이름을 값에 담는 것만 본다).
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
import { TagPicker } from "./TagPicker.jsx";

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
});
