import React from "react";
import { FilterBar } from "../../ui/FilterBar.jsx";
import { EntityCombobox, FilterSelect, SearchBox, unmatchedLabel } from "../../ui/filters.jsx";
import { TagPicker } from "../../ui/TagPicker.jsx";
import { SORTS, VIEW_OPTIONS } from "./constants.js";

/* 문서 목록의 탐색 줄 — **페이지 전폭**이다.
 *
 * 한 줄 순서는 필터 바 정본이다(핸드오프 README §3 · 조합 계약 C-1): 검색 320 → 내용 조건(프로젝트 · 분류 ·
 * 태그 · 작성자) → 빈 공간 → 오른쪽 끝 정렬. 「보기」는 이 줄의 조건이 아니라 줄 **위**의 세그먼티드가 고른다
 * (`Knowledge.jsx`). 조건이 하나라도 걸리면 같은 면 안 둘째 줄이 조건 줄이다 —
 * 「조건 N개, 결과 M건」 → 조건 칩 → 「필터 지우기」(ACCEPTANCE D3).
 *
 * **모든 조건은 칩을 가진다**(조합 계약 C-1). 예전에는 검색어를 조건으로 세면서 칩은 안 그렸고 태그 셋을 조건
 * 하나로 세서, 「조건 2개」 옆에 칩이 하나였다. 조건 수는 이제 칩 수다.
 *
 * 프로젝트는 **사람이 고른 자리일 때만** 조건이다(D-388 을 이어 받는다). 프로젝트가 하나뿐인 조직에서 화면이
 * 스스로 연 그 프로젝트는 조건이 아니다 — 아무것도 안 건 사람에게 「조건 1개」를 보이지 않는다. 호출부가
 * `projectIsCondition` 으로 그 판정을 넘긴다. */
export function KnowledgeFilterBar({
  q, view, project, projectIsCondition, tags, category, author, sort,
  entries, categories, authors,
  onCommitSearch, onQuery, onClearAll, total,
}) {
  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));
  const categoryName = (categories.find((c) => c.id === category) || {}).name || "";
  const authorName = ((authors || []).find((a) => a.value === author) || {}).label || "";
  const viewLabel = (VIEW_OPTIONS.find((o) => o.value === view) || {}).label || "";
  const projectName = ((entries || []).find((e) => e.value === project) || {}).label || "";

  const chips = [];
  const pushChip = (key, label, onDelete) => { chips.push({ key, label, onDelete }); };
  if (q) pushChip("q", `검색: ${q}`, () => onQuery({ q: null }));
  if (view && viewLabel) pushChip("view", `보기: ${viewLabel}`, () => onQuery({ view: null }));
  /* 이름을 모르는 프로젝트(후보 질의 실패 · 옛 링크)는 식별자를 드러내지 않는 낱말로 선다 — 칸과 같은 규칙이다. */
  if (project && projectIsCondition) pushChip("project", `프로젝트: ${projectName || unmatchedLabel(project, false)}`, () => onQuery({ project: null }));
  if (category) pushChip("category", `분류: ${categoryName}`, () => onQuery({ category: null }));
  for (const name of tags) {
    pushChip(`tag:${name}`, `태그: ${name}`, () => onQuery({ tags: tags.filter((t) => t !== name) }));
  }
  if (author && authorName) {
    pushChip("author", `작성자: ${authorName}`, () => onQuery({ author: null }));
  }

  return (
    <FilterBar
      search={(
        <SearchBox
          value={q}
          onSearch={onCommitSearch}
          placeholder="문서 제목, 내용 검색"
          ariaLabel="문서 검색"
        />
      )}
      /* 정렬은 「무엇을 볼지」가 아니라 「어떻게 볼지」라 오른쪽 끝 묶음이다 — 좁아지면 묶음째 다음 줄로 간다.
         「전체」가 답이 아닌 축이라 빈 항목이 없다. */
      end={(
        <FilterSelect
          label="정렬"
          value={sort}
          onChange={(v) => onQuery({ sort: v })}
          options={SORTS}
          noAllOption
        />
      )}
      conditions={{ chips, total, onClearAll, clearLabel: "필터 지우기" }}
    >
      {/* 축의 이름은 **프로젝트**다(D-415). 값 · 주소 · 서버 파라미터(`?project=`, `project_id`, `"none"`)는 그대로다. */}
      <EntityCombobox
        label="프로젝트"
        allLabel="전체"
        value={project}
        onChange={(v) => onQuery({ project: v || null })}
        options={entries}
      />
      <FilterSelect
        label="분류"
        allLabel="분류 전체"
        value={category}
        onChange={(v) => onQuery({ category: v || null })}
        options={categoryOptions}
      />
      {/* 다중 선택은 AND 다 — 고른 태그를 전부 가진 문서로 좁힌다(§11.3). 값은 이름 배열이라 문서 저장 계약과 같다. */}
      <TagPicker
        value={tags}
        onChange={(next) => onQuery({ tags: next })}
      />
      {/* 사람은 **기수가 무한히 자라는 대상**이다 — 평범한 드롭다운으로 두면 이름을 알면서도 목록을 눈으로 훑게 된다(C2 · R-5). */}
      <EntityCombobox
        label="작성자"
        allLabel="전체"
        value={author}
        onChange={(v) => onQuery({ author: v || null })}
        options={authors}
      />
    </FilterBar>
  );
}
