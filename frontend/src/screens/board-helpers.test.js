import { describe, it, expect } from "vitest";
import { buildPostsQuery, reactionMap, splitComments } from "./board-helpers.js";

describe("buildPostsQuery", () => {
  it("omits empty category and search, defaults sort to recent", () => {
    expect(buildPostsQuery({})).toBe("sort=recent");
    expect(buildPostsQuery({ category: "", q: "" })).toBe("sort=recent");
  });
  it("includes category and query when set", () => {
    const s = buildPostsQuery({ category: "질문", q: "배포", sort: "views" });
    const p = new URLSearchParams(s);
    expect(p.get("category")).toBe("질문");
    expect(p.get("q")).toBe("배포");
    expect(p.get("sort")).toBe("views");
  });
  it("clamps unknown sort to recent", () => {
    expect(new URLSearchParams(buildPostsQuery({ sort: "hacked" })).get("sort")).toBe("recent");
  });
});

describe("reactionMap", () => {
  it("maps emoji to count and mine", () => {
    const m = reactionMap([
      { emoji: "👍", count: 3, mine: true },
      { emoji: "🎉", count: 1, mine: false },
    ]);
    expect(m["👍"]).toEqual({ count: 3, mine: true });
    expect(m["🎉"]).toEqual({ count: 1, mine: false });
  });
  it("handles null and missing fields", () => {
    expect(reactionMap(null)).toEqual({});
    expect(reactionMap([{ emoji: "👀" }])["👀"]).toEqual({ count: 0, mine: false });
  });
});

describe("splitComments", () => {
  it("separates top-level comments from replies grouped by parent", () => {
    const { tops, repliesByParent } = splitComments([
      { id: "a", parent_comment_id: null },
      { id: "b", parent_comment_id: "a" },
      { id: "c", parent_comment_id: null },
      { id: "d", parent_comment_id: "a" },
    ]);
    expect(tops.map((c) => c.id)).toEqual(["a", "c"]);
    expect(repliesByParent["a"].map((c) => c.id)).toEqual(["b", "d"]);
    expect(repliesByParent["c"]).toBeUndefined();
  });
  it("handles empty/undefined", () => {
    expect(splitComments(undefined)).toEqual({ tops: [], repliesByParent: {} });
  });
});
