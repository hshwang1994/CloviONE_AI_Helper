import React from "react";
import {
  FilterConditionLine, FilterSurface, ToolbarEnd, ToolbarRow,
} from "../../ui/FilterBar.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { TagPicker } from "../../ui/TagPicker.jsx";
import { SORTS, VIEW_OPTIONS } from "./constants.js";

/* 문서 목록의 탐색 줄 — **페이지 전폭**이다.
 *
 * 옛 화면은 이 줄이 중앙 칸 안에 서서 탐색기(20rem) 오른쪽에서 시작했고, 조건의 절반
 * (보기·태그 칩)은 탐색기 안에 흩어져 있었다. 지금은 다른 목록 화면과 같은 자리 — 제목
 * 아래 전폭 — 에 조건 전부가 선다.
 *
 * 한 줄 순서는 필터 바 정본이다(핸드오프 README §3 · 계획 §0-4 · D): 검색 320 → 내용 조건(프로젝트 · 분류 ·
 * 태그 · 작성자) → 빈 공간 → 오른쪽 끝 정렬(`ToolbarEnd`). 「보기」는 이 줄의 조건이 아니라 줄 **위**의
 * 세그먼티드가 고른다(`Knowledge.jsx`). 조건이 하나라도 걸리면 줄 아래 실선 뒤에 조건 줄이 선다 —
 * 「조건 N개, 결과 M건」 → 조건 칩 → 「필터 지우기」(ACCEPTANCE D3).
 *
 * 걸린 조건은 칩으로도 선다(티켓 목록과 같은 계약) — 폴더처럼 왼쪽 내비에서만 고를 수
 * 있는 축도 칩으로는 **여기서** 풀 수 있어야 한다. */
export function KnowledgeFilterBar({
  q, view, project, tags, category, author, sort,
  entries, categories, authors,
  onCommitSearch, onQuery, onClearAll, total, conditions,
}) {
  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name }));
  const categoryName = (categories.find((c) => c.id === category) || {}).name || "";
  const authorName = ((authors || []).find((a) => a.value === author) || {}).label || "";
  const viewLabel = (VIEW_OPTIONS.find((o) => o.value === view) || {}).label || "";

  /* 칩은 조건 축과 같은 목록이다(D-388) — 프로젝트는 조건이 아니라 **자리**라 칩이
     없다(바로 위 고르개가 그 상태를 그린다). 폴더 칩은 폴더 축이 화면에서 걷히면서
     함께 없어졌다(문서 개편 1·5번). */
  const chips = [];
  const pushChip = (key, label, onDelete) => { chips.push({ key, label, onDelete }); };
  if (view && viewLabel) pushChip("view", `보기: ${viewLabel}`, () => onQuery({ view: null }));
  if (category) pushChip("category", `분류: ${categoryName}`, () => onQuery({ category: null }));
  for (const name of tags) {
    pushChip(`tag:${name}`, `태그: ${name}`, () => onQuery({ tags: tags.filter((t) => t !== name) }));
  }
  if (author && authorName) {
    pushChip("author", `작성자: ${authorName}`, () => onQuery({ author: null }));
  }

  return (
    <FilterSurface>
      <ToolbarRow>
        <SearchBox
          value={q}
          onSearch={onCommitSearch}
          placeholder="문서 제목, 내용 검색"
          ariaLabel="문서 검색"
        />
        {/* 축의 이름은 **프로젝트**다. 한때 「문서 범위」였는데, 그것은 후보에 프로젝트가
            아닌 값(「공통 문서」)이 섞여 라벨이 내용에 대해 거짓말을 했기 때문이다
            (D-415). 그 값을 「프로젝트 미지정」으로 부르는 지금은 프로젝트 축의 정직한
            값이라 그 이름이 필요 없어졌다.
            값·주소·서버 파라미터(`?project=`, `project_id`, `"none"`)는 안 바뀌었다. */}
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
        {/* 다중 선택은 AND 다 — 고른 태그를 전부 가진 문서로 좁힌다(§11.3).
            값은 이름 배열이라 문서 저장 계약과 같다. */}
        <TagPicker
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
        {/* 정렬은 「무엇을 볼지」가 아니라 「어떻게 볼지」라 오른쪽 끝 묶음이다 — 좁아지면 묶음째 다음 줄로 간다. */}
        <ToolbarEnd>
          <FilterSelect
            label="정렬"
            value={sort}
            onChange={(v) => onQuery({ sort: v })}
            options={SORTS}
          />
        </ToolbarEnd>
      </ToolbarRow>
      <FilterConditionLine
        total={total}
        chips={chips}
        conditions={conditions}
        onClearAll={onClearAll}
        clearLabel="필터 지우기"
      />
    </FilterSurface>
  );
}
