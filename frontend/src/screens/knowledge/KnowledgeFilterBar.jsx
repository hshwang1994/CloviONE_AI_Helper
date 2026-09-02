import React from "react";
import { Button } from "../../ui/kit.jsx";
import {
  FilterActions, FilterChips, FilterRow, FilterSurface, ToolbarRow,
} from "../../ui/FilterBar.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { TagPicker } from "../../ui/TagPicker.jsx";
import { SORTS, VIEW, VIEW_OPTIONS, spaceDisplayName } from "./constants.js";

/* 문서 목록의 탐색 줄 — **페이지 전폭**이다.
 *
 * 옛 화면은 이 줄이 중앙 칸 안에 서서 탐색기(20rem) 오른쪽에서 시작했고, 조건의 절반
 * (보기·태그 칩)은 탐색기 안에 흩어져 있었다. 지금은 다른 목록 화면과 같은 자리 — 제목
 * 아래 전폭 — 에 조건 전부가 선다. 축 순서는 `FILTER_GROUP_ORDER` 를 따른다:
 * 보기(범위) → 프로젝트(개체) → 분류·태그(분류) → 작성자(개체) → 정렬.
 *
 * 걸린 조건은 칩으로도 선다(티켓 목록과 같은 계약) — 폴더처럼 왼쪽 내비에서만 고를 수
 * 있는 축도 칩으로는 **여기서** 풀 수 있어야 한다. */
export function KnowledgeFilterBar({
  q, view, spaceId, folderId, folderName, tags, category, author, sort,
  spaces, categories, authors,
  onCommitSearch, onQuery, onClearAll, hasFilter,
}) {
  const spaceOptions = spaces.map((s) => ({ value: s.id, label: spaceDisplayName(s) }));
  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));
  const categoryName = (categories.find((c) => c.id === category) || {}).name || "";
  const authorName = ((authors || []).find((a) => a.value === author) || {}).label || "";
  const viewLabel = (VIEW_OPTIONS.find((o) => o.value === view) || {}).label || "";

  /* 칩은 조건 축과 같은 목록이다(D-388) — 프로젝트(공간)는 조건이 아니라 자리라 칩이
     없다(좌측 내비와 위의 고르개가 그 상태를 그린다). */
  const chips = [];
  const pushChip = (key, label, onDelete) => { chips.push({ key, label, onDelete }); };
  if (view && viewLabel) pushChip("view", `보기: ${viewLabel}`, () => onQuery({ view: null }));
  if (folderId) {
    pushChip("folder", `폴더: ${folderName || "고른 폴더"}`, () => onQuery({ folder: null }));
  }
  if (category) pushChip("category", `분류: ${categoryName}`, () => onQuery({ category: null }));
  for (const name of tags) {
    pushChip(`tag:${name}`, `태그: ${name}`, () => onQuery({ tags: tags.filter((t) => t !== name) }));
  }
  if (author && authorName) {
    pushChip("author", `작성자: ${authorName}`, () => onQuery({ author: null }));
  }

  return (
    <>
      <FilterSurface>
        <ToolbarRow>
          <SearchBox
            value={q}
            onSearch={onCommitSearch}
            placeholder="문서 제목, 내용 검색"
            ariaLabel="문서 검색"
          />
        </ToolbarRow>
        <FilterRow>
          {/* 「보기」는 값이 넷뿐인 **닫힌 축**이다 — FilterSelect 가 맞다. 빈 값 문구는
              기본형(「보기 전체」)을 쓴다: 「전체 문서」라고 적으면 정적 프로브가 「문서」
              낱말로 이 고르개를 개체 축으로 오판하고, 요약 타일이 이미 같은 낱말을 든다. */}
          <FilterSelect
            label="보기"
            value={view || VIEW.all}
            onChange={(v) => onQuery({ view: v || null })}
            options={VIEW_OPTIONS}
          />
          <EntityCombobox
            label="프로젝트"
            allLabel="전체"
            value={spaceId}
            onChange={(v) => onQuery({ space: v || null, folder: null })}
            options={spaceOptions}
          />
          <FilterSelect
            label="분류"
            allLabel="분류 전체"
            value={category}
            onChange={(v) => onQuery({ category: v || null })}
            options={categoryOptions}
          />
          {/* 다중 선택은 AND 다 — 고른 태그를 전부 가진 문서로 좁힌다(§11.3).
              값은 이름 배열이라 문서 저장 계약과 같다. */}
          <TagPicker
            label="기술 태그"
            value={tags}
            onChange={(next) => onQuery({ tags: next })}
          />
          {/* 사람은 **기수가 무한히 자라는 대상**이다 — 사람이 늘면 후보도 는다. 평범한
              드롭다운으로 두면 이름을 알면서도 목록을 눈으로 훑게 된다(C2 · R-5). */}
          <EntityCombobox
            label="작성자"
            allLabel="전체"
            value={author}
            onChange={(v) => onQuery({ author: v || null })}
            options={authors}
          />
          <FilterSelect
            label="정렬"
            value={sort}
            onChange={(v) => onQuery({ sort: v })}
            options={SORTS}
          />
          {hasFilter ? (
            <FilterActions>
              <Button variant="ghost" size="sm" onClick={onClearAll}>필터 지우기</Button>
            </FilterActions>
          ) : null}
        </FilterRow>
      </FilterSurface>
      <FilterChips items={chips} onClearAll={chips.length > 1 ? onClearAll : null} clearLabel="필터 지우기" />
    </>
  );
}
