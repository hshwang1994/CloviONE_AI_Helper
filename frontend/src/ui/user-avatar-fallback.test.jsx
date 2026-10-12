import React from "react";
import { describe, it, expect } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { UserAvatar } from "./UserAvatar.jsx";

/* 사람 그림의 정본은 하나다(D-556) — 사진 주소가 있는데 서버가 404 · 오류를 주면(범위 밖 · 파일 없음 ·
 * 낡은 주소) 깨진 그림 아이콘이 아니라 **그 사람의 기본 그림**이 선다. 새 주소(`?v=` 가 바뀜)가 오면 다시 시도한다. */
describe("UserAvatar — 사진이 깨지면 기본 그림으로 물러난다", () => {
  const person = { user_id: "u-1", avatar_url: "/api/profile/avatar/u-1?v=1", avatar_default_key: "thumbs:2" };

  it("사진 주소가 있으면 그 사진을 그린다", () => {
    const { container } = render(<UserAvatar person={person} label="홍길동" />);
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toBe(person.avatar_url);
  });

  it("사진이 오류를 내면 그 사람이 고른 기본 그림이 선다", () => {
    const { container } = render(<UserAvatar person={person} label="홍길동" />);
    fireEvent.error(container.querySelector("img"));
    expect(container.querySelector(`img[src="${person.avatar_url}"]`)).toBeNull();
    const fallback = container.querySelector("[data-avatar-pending], [data-avatar-key]");
    expect(fallback).not.toBeNull();
    const key = fallback.getAttribute("data-avatar-pending") || fallback.getAttribute("data-avatar-key");
    expect(key).toBe("thumbs:2");
  });

  it("새 사진 주소가 오면 다시 시도한다", () => {
    const { container, rerender } = render(<UserAvatar person={person} label="홍길동" />);
    fireEvent.error(container.querySelector("img"));
    expect(container.querySelector(`img[src="${person.avatar_url}"]`)).toBeNull();
    const next = { ...person, avatar_url: "/api/profile/avatar/u-1?v=2" };
    rerender(<UserAvatar person={next} label="홍길동" />);
    expect(container.querySelector(`img[src="${next.avatar_url}"]`)).not.toBeNull();
  });

  it("사진도 고른 그림도 없으면 id 를 씨앗으로 한 기본 그림이 선다", () => {
    const { container } = render(<UserAvatar person={{ user_id: "u-9" }} label="아무개" />);
    expect(container.querySelector("img[src^='/api/']")).toBeNull();
    expect(container.querySelector("[data-avatar-pending], [data-avatar-key]")).not.toBeNull();
  });
});
