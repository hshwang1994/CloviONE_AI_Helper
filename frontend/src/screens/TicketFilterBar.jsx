import React from "react";
import Typography from "@mui/material/Typography";
import { Button, EmptyState } from "../ui/kit.jsx";
import { DebouncedTextField, EntityCombobox, FilterSelect, SearchBox } from "../ui/filters.jsx";
import { FilterActions, FilterChips, FilterRow, FilterSurface, ResultLine, ToolbarRow } from "../ui/FilterBar.jsx";
import { priorityKo } from "../lib/priority.js";
import { affiliation, needsOrg } from "../lib/people.js";
import { useAssigneeOptions, useTicketMeta, useTicketProjects } from "./ticket-options.js";

/* 티켓 목록 화면 네 곳(내 티켓·미할당·팀 티켓·스프린트)이 함께 쓰는 필터 줄.
 *
 * ## 왜 하나로 모았나
 *
 * 예전에는 화면마다 필터가 따로였다. 내 티켓은 상태 하나, 팀 티켓은 상태 + 담당자, 미할당과
 * 스프린트는 아무것도 없었다. 그리고 그 상태 필터조차 **어휘가 갈릴 뻔한 자리**라 한쪽만
 * 고치면 두 화면이 다른 말을 하게 된다고 코드에 적혀 있었다. 부품 하나로 모으면 그 갈라짐이
 * 구조적으로 불가능해진다.
 *
 * ## 조건은 **서버가** 건다
 *
 * `app/tickets/router.py` 가 목록 세 개(mine/unassigned/team)에서 같은 질의 파라미터를 받는다:
 * status, priority, difficulty, project_id, assignee_user_id, category, due, q + page.
 * 그래서 이 부품은 값만 들고 있고 거르지 않는다. 클라이언트에서 거르면 서버가 자른 한
 * 페이지(기본 20건) 안에서만 걸러져, 사용자는 "필터를 걸었더니 티켓이 사라졌다"를 겪는다.
 *
 * 예외는 스프린트다. 그 화면은 `/api/sprint/summary` 가 그 주치를 **전량** 주므로 페이지가
 * 없고, 거기서는 `matchesTicketFilters` 로 화면이 직접 거르는 것이 정직하다.
 *
 * ## 화면마다 조건이 다른 이유
 *
 * `fields` 로 고른다. 뜻이 없는 조건을 그리지 않기 위해서다:
 *   - 내 티켓의 담당자는 언제나 나다(서버가 그 조건을 아예 안 받는다).
 *   - 미할당은 정의상 담당자가 없다.
 *   - 스프린트 행은 리포트 경로에서 와서 프로젝트와 대분류를 싣지 않는다. 그걸 필터로
 *     내놓으면 고르는 순간 목록이 언제나 비는데, 사용자는 그걸 "티켓이 없다"로 읽는다.
 */

/** 서버가 받는 기한 버킷. 값은 app/tickets/repository.py 의 DUE_BUCKETS 와 같아야 한다. */
export const DUE_OPTIONS = [
  { value: "overdue", label: "지연" },
  { value: "this_week", label: "이번 주" },
  { value: "next_week", label: "다음 주" },
];

const LABELS = {
  project_id: "프로젝트",
  status: "상태",
  priority: "우선순위",
  difficulty: "난이도",
  assignee_user_id: "담당자",
  due: "기한",
  category: "대분류",
  q: "검색어",
};

const META_FIELDS = ["status", "priority", "difficulty"];
const MULTI_FIELDS = ["status", "priority", "difficulty", "project_id", "assignee_user_id"];
const RANGE_KEYS = ["created_from", "created_to", "est_wd_min", "est_wd_max", "act_wd_min", "act_wd_max"];

export const TICKET_LIST_EXTRA = {
  page: 1,
  sort: "created_at",
  order: "desc",
  created_from: "",
  created_to: "",
  est_wd_min: "",
  est_wd_max: "",
  act_wd_min: "",
  act_wd_max: "",
};

const SORT_DEFAULT_DIR = {
  created_at: "desc",
  due: "asc",
  due_date: "asc",
  title: "asc",
  status: "asc",
  priority: "asc",
  tid: "asc",
  est_wd: "desc",
  act_wd: "desc",
};

export function ticketSortOf(state) {
  const key = (state && state.sort) || "created_at";
  return { key: key === "due_date" ? "due" : key, dir: (state && state.order) || "desc" };
}

export function nextTicketSort(state, key) {
  const sortKey = key === "due" ? "due_date" : key;
  const current = (state && state.sort) || "created_at";
  const dir = (state && state.order) || "desc";
  if (current === sortKey) {
    return { sort: sortKey, order: dir === "asc" ? "desc" : "asc" };
  }
  return { sort: sortKey, order: SORT_DEFAULT_DIR[key] || SORT_DEFAULT_DIR[sortKey] || "asc" };
}

export function columnFilterValue(state, field) {
  if (field === "created_at") return { from: state.created_from || "", to: state.created_to || "" };
  if (field === "est_wd") return { min: state.est_wd_min || "", max: state.est_wd_max || "" };
  if (field === "act_wd") return { min: state.act_wd_min || "", max: state.act_wd_max || "" };
  return state[field];
}

export function applyColumnFilter(field, next) {
  if (field === "created_at") {
    return { created_from: (next && next.from) || "", created_to: (next && next.to) || "" };
  }
  if (field === "est_wd") {
    return { est_wd_min: (next && next.min) || "", est_wd_max: (next && next.max) || "" };
  }
  if (field === "act_wd") {
    return { act_wd_min: (next && next.min) || "", act_wd_max: (next && next.max) || "" };
  }
  return { [field]: next };
}

/* 스프린트가 **화면에서 직접** 거를 수 있는 조건. 행이 실제로 싣는 값만 들어 있다.
 * 여기 없는 조건을 스프린트 필터에 넣으면 고르는 순간 목록이 언제나 빈다 — 그건 "필터가
 * 안 먹는다"보다 나쁘다(사용자는 그것을 '티켓이 없다'로 읽는다). 이 목록과
 * `matchesTicketFilters` 는 한 쌍이다.
 *
 * 프로젝트와 담당자가 여기 있는 이유: `app/sprints/service.py` 가 담당자별 티켓을
 * `by_assignee` 로 주고, 그 안의 티켓은 `tickets_service.ticket_views()` 결과라 목록 API 와
 * **완전히 같은 dict** 다(project_ids, assignee_user_ids 를 싣는다). 예전 응답 모양은
 * 리포트 경로(`_ticket_detail`)라 그 값이 없었고, 그래서 두 조건이 빠져 있었다. */
export const SPRINT_FIELDS = ["q", "project_id", "status", "priority", "difficulty", "assignee_user_id"];

/* 옛 응답 모양(리포트 경로 = `developers[].tickets`)일 때 쓰는 축소판.
 *
 * 화면이 응답 모양을 보고 둘 중 하나를 고른다. 없는 값을 조건으로 내놓지 않기 위해서다 —
 * 프로젝트를 고를 수 있게 그려 놓고 행에 프로젝트가 없으면, 고르는 순간 목록이 통째로
 * 비고 사용자는 그것을 "이 프로젝트엔 티켓이 없다"로 읽는다. */
export const SPRINT_REPORT_FIELDS = ["q", "status", "priority", "difficulty"];

/* 이 화면이 URL 에 둘 상태 한 벌.
 *
 * `extra` 는 필터가 아닌 상태다. 기본값은 `{ page: 1 }` — 서버가 목록을 자르는 화면이라면
 * 페이지가 **반드시** 같이 주소에 있어야 한다(필터만 남기면 공유한 링크가 늘 1페이지다).
 * 페이지가 없는 화면(스프린트는 그 주치를 전량 받는다)은 자기 것으로 바꿔 넘긴다. */
export function ticketFilterSpec(fields, extra = { page: 1 }) {
  const spec = {};
  for (const key of fields) spec[key] = MULTI_FIELDS.includes(key) ? [] : "";
  return { ...spec, ...extra };
}

export function asList(value) {
  if (Array.isArray(value)) return value.filter((v) => v !== "" && v != null);
  return value ? [value] : [];
}

function isFilled(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") {
    return Object.values(value).some((v) => v != null && v !== "");
  }
  return !!value;
}

/** 필터가 하나라도 걸려 있는가 — 빈 목록이 '필터 때문'인지 '정말 없음'인지 가르는 값. */
export function hasTicketFilter(state, fields) {
  return fields.some((key) => isFilled(state[key]));
}

/** 지금 실제로 걸려 있는 조건의 키 목록 — 결과 줄이 «조건 N개» 를 말할 때 쓴다. */
export function activeConditions(state, fields) {
  return fields.filter((key) => isFilled(state[key]));
}

/** 전부 지운 상태 조각. 필터 줄의 버튼과 빈 상태의 버튼이 **같은 것**을 해야 한다. */
export function clearTicketFilters(fields) {
  const empty = {};
  for (const key of fields) empty[key] = MULTI_FIELDS.includes(key) ? [] : "";
  for (const key of RANGE_KEYS) empty[key] = "";
  return empty;
}

function appendQueryValue(p, key, v) {
  if (Array.isArray(v)) {
    for (const item of v) {
      if (item !== "" && item != null) p.append(key, String(item));
    }
    return;
  }
  if (v) p.set(key, String(v));
}

/** 화면 상태 → 서버 질의 파라미터. 빈 값은 보내지 않는다(서버는 빈 문자열을 조건 없음으로 읽지만, 주소가 지저분해진다). */
export function ticketQueryParams(state, fields, extra) {
  const p = extra instanceof URLSearchParams ? extra : new URLSearchParams(extra || "");
  for (const key of fields) appendQueryValue(p, key, state[key]);
  for (const key of RANGE_KEYS) {
    if (state[key]) p.set(key, String(state[key]));
  }
  if (state.sort && (state.sort !== "created_at" || state.order !== "desc")) {
    p.set("sort", String(state.sort));
    p.set("order", String(state.order || "desc"));
  }
  if (state.page > 1) p.set("page", String(state.page));
  return p;
}

/* 티켓 한 건이 조건을 지나는가 — **스프린트 전용**(그 화면만 전량을 받아 스스로 거른다).
 * 서버가 거르는 목록에는 절대 쓰지 마라: 한 페이지 안에서만 걸러 총 건수와 어긋난다.
 * 판정은 app/tickets/repository.py 의 TicketFilters.matches 와 같은 규칙이다. */
const CLIENT_JUDGED = ["status", "priority", "difficulty"];

/* 티켓 하나가 **여러 개**를 가질 수 있는 조건 → 그 값이 들어 있는 자리들.
 * 스칼라로 비교하면 프로젝트가 둘인 티켓·담당자가 둘인 티켓이 조용히 떨어진다.
 * 판정은 서버와 같다: 하나라도 맞으면 통과(app/tickets/query.py 의 filter_clauses).
 *
 * 🔴 프로젝트는 **자리가 둘**이다. 화면이 고르는 값은 Portal 프로젝트 id 인데
 * (`/api/tickets/projects`), 이관해 온 티켓의 `project_ids` 에 들어 있는 것은 옛 소스의
 * relation id 다 — 두 축은 절대 같은 문자열이 되지 않는다. 옛 축만 보면 스프린트의
 * 프로젝트 조건이 **모든 티켓에서 언제나 거짓**이 되고, 화면에는 "이 프로젝트엔 티켓이
 * 없다" 로 보인다(오류가 아니라 빈 목록이라 아무도 신고하지 않는다). 서버는 이미 두 축을
 * `OR` 로 함께 본다 — 그 판정을 여기서도 그대로 쓴다. */
const CLIENT_JUDGED_MULTI = {
  project_id: ["project_uid", "project_ids"],
  assignee_user_id: ["assignee_user_ids"],
};

/** 행의 여러 자리에서 값을 모은다 — 스칼라 한 칸이든 배열이든 같은 목록으로 편다. */
function valuesAt(ticket, keys) {
  const out = [];
  for (const key of keys) {
    const v = ticket[key];
    if (Array.isArray(v)) out.push(...v);
    else if (v) out.push(v);
  }
  return out;
}

export function matchesTicketFilters(ticket, state, fields) {
  for (const key of fields) {
    const raw = state[key];
    const wantList = Array.isArray(raw) ? raw.filter(Boolean) : (raw ? [raw] : []);
    if (!wantList.length) continue;
    if (key === "q") {
      const q = String(wantList[0]).toLowerCase();
      if (!String(ticket.title || "").toLowerCase().includes(q)) return false;
      continue;
    }
    const multi = CLIENT_JUDGED_MULTI[key];
    if (multi) {
      const have = valuesAt(ticket, multi).map(String);
      if (!wantList.some((w) => have.includes(String(w)))) return false;
      continue;
    }
    /* 화면이 판단할 수 없는 조건이면 **소리를 낸다**. 조용히 통과시키면 "필터를 걸었는데
       전체가 나온다" 가 되고, 조용히 떨어뜨리면 "티켓이 하나도 없다" 가 된다 — 둘 다
       사용자가 원인을 알아챌 수 없는 방향의 오류다. 지금 부르는 곳은 스프린트 하나뿐이고
       `SPRINT_FIELDS` 가 위의 두 집합 안에 있으므로 실제로는 절대 나지 않는다(검사가 고정한다).
       `due`(기한 버킷)와 `category` 는 일부러 밖에 남겨 뒀다 — 기한 버킷은 '오늘'이 있어야
       풀리고, 대분류는 리포트 경로 행에 없다. */
    if (!CLIENT_JUDGED.includes(key)) {
      throw new Error(`화면에서 거를 수 없는 조건입니다: ${key}`);
    }
    if (!wantList.includes(ticket[key])) return false;
  }
  return true;
}

/* 빈 목록의 두 가지 뜻을 가른다.
 *
 * 회색 한 줄은 "필터 때문에 없음"과 "정말 없음"을 구분해 주지 않는다 — 문서 목록이 이미
 * 같은 이유로 세 갈래(동기화 전·필터·진짜 빈)로 나뉘어 있다. 필터가 걸린 쪽에는 **그 자리에서
 * 되돌릴 버튼**을 준다. 사용자가 무엇을 눌렀는지 잊었을 때 화면 위 필터 일곱 개를 되짚게
 * 하는 것은 안내가 아니다. */
export function TicketEmptyState({ filtered, onClear, title, help }) {
  if (filtered) {
    return (
      <EmptyState
        art="search"
        title="조건에 맞는 티켓이 없습니다"
        help="지금 걸린 필터에 맞는 티켓이 없습니다. 검색어나 필터를 지우면 더 많은 티켓이 보입니다."
        action={onClear ? <Button variant="primary" onClick={onClear}>필터 지우기</Button> : null}
      />
    );
  }
  return <EmptyState art="tickets" title={title || "표시할 티켓이 없습니다"} help={help} />;
}

function assigneeOptions(rows) {
  const list = Array.isArray(rows) ? rows : [];
  const withOrg = needsOrg(list);
  return list.map((c) => {
    const aff = affiliation(c, { withOrg });
    return { value: c.user_id, label: aff ? `${c.display_name} (${aff})` : c.display_name };
  });
}

/* `scope` 와 `extra` 를 나눠 받는 이유 (W5 재정정 — 독립 검수가 잡았다).
 *
 * 예전에는 호출부가 둘을 한 덩어리(`extra`)로 넘겼고 그 덩어리가 **줄 맨 끝**에 그려졌다.
 * 그래서 `/team-tickets` 의 부서 필터가 기한 뒤에 서서, 바로 위 주석이 「순서는 C2 가
 * 정한다: scope(부서) → entity → …」라고 적어 둔 것을 같은 파일이 39줄 뒤에서 어겼다.
 * 실측: 부서가 세 번째 줄에 혼자 섰다. 축의 순서는 **부품이** 지켜야 한다 — 호출부에
 * 맡기면 화면마다 갈린다. */
export function TicketFilterBar({
  fields, value, onChange, total, scope, extra, onClear,
  defaultStatusKeys, allStatus, onShowAll, resetLabel = "필터 지우기",
}) {
  const wantMeta = fields.some((f) => META_FIELDS.includes(f));
  const metaQ = useTicketMeta(wantMeta);
  const projectsQ = useTicketProjects(fields.includes("project_id"));
  const assigneesQ = useAssigneeOptions(fields.includes("assignee_user_id"));
  const meta = metaQ.data || {};
  const projectOpts = ((projectsQ.data && projectsQ.data.projects) || []).map((p) => ({ value: p.id, label: p.name || "(제목 없음)" }));
  const peopleOpts = assigneeOptions(assigneesQ.data && assigneesQ.data.assignees);
  const statusOpts = meta.statuses || [];
  const priorityOpts = (meta.priorities || []).map((p) => ({ value: p, label: priorityKo(p) }));
  const difficultyOpts = meta.difficulties || [];

  /* 참조가 고정돼야 한다. 검색 입력은 `React.memo` 로 감싼 부품이라, 매 렌더마다 새 함수를
     주면 메모가 매번 깨지고 디바운스 타이머가 다시 시작된다. */
  const commitSearch = React.useCallback((next) => onChange({ q: next }), [onChange]);
  const commitCategory = React.useCallback((next) => onChange({ category: next }), [onChange]);

  const usingDefaultStatus = !!(defaultStatusKeys && defaultStatusKeys.length) && !allStatus && !isFilled(value.status);
  const effectiveStatus = usingDefaultStatus ? defaultStatusKeys : asList(value.status);
  const filtered = hasTicketFilter(value, fields) || usingDefaultStatus || !!allStatus
    || RANGE_KEYS.some((key) => !!value[key]);
  const atDefault = !hasTicketFilter(value, fields) && !allStatus && RANGE_KEYS.every((key) => !value[key]);
  const clear = React.useCallback(() => {
    if (onClear) { onClear(); return; }
    onChange(clearTicketFilters(fields));
  }, [onClear, onChange, fields]);

  const show = (key) => fields.includes(key);
  const set = (key) => (v) => onChange({ [key]: v });
  const optionLabel = (opts, v) => {
    const hit = (Array.isArray(opts) ? opts : []).find((o) => String(typeof o === "string" ? o : o.value) === String(v));
    if (!hit) return String(v);
    return typeof hit === "string" ? hit : hit.label;
  };

  const chips = [];
  const pushChip = (key, label, onDelete) => {
    chips.push({ key, label, onDelete });
  };
  if (show("status")) {
    for (const s of effectiveStatus) {
      pushChip(`status:${s}`, `상태: ${optionLabel(statusOpts, s)}`, () => {
        const next = effectiveStatus.filter((v) => v !== s);
        if (!next.length && usingDefaultStatus) onChange({ status: [], all_status: true });
        else onChange({ status: next, all_status: false });
      });
    }
  }
  if (show("priority") && isFilled(value.priority)) {
    for (const v of asList(value.priority)) {
      pushChip(`priority:${v}`, `우선순위: ${optionLabel(priorityOpts, v)}`, () => onChange({ priority: asList(value.priority).filter((x) => x !== v) }));
    }
  }
  if (show("difficulty") && isFilled(value.difficulty)) {
    for (const v of asList(value.difficulty)) {
      pushChip(`difficulty:${v}`, `난이도: ${v}`, () => onChange({ difficulty: asList(value.difficulty).filter((x) => x !== v) }));
    }
  }
  if (show("project_id") && isFilled(value.project_id)) {
    for (const v of asList(value.project_id)) {
      pushChip(`project:${v}`, `프로젝트: ${optionLabel(projectOpts, v)}`, () => onChange({ project_id: asList(value.project_id).filter((x) => x !== v) }));
    }
  }
  if (show("assignee_user_id") && isFilled(value.assignee_user_id)) {
    for (const v of asList(value.assignee_user_id)) {
      pushChip(`assignee:${v}`, `담당자: ${optionLabel(peopleOpts, v)}`, () => onChange({ assignee_user_id: asList(value.assignee_user_id).filter((x) => x !== v) }));
    }
  }
  if (show("due") && value.due) {
    pushChip("due", `기한: ${optionLabel(DUE_OPTIONS, value.due)}`, () => onChange({ due: "" }));
  }
  if (show("category") && value.category) {
    pushChip("category", `대분류: ${value.category}`, () => onChange({ category: "" }));
  }
  if (show("q") && value.q) {
    pushChip("q", `검색: ${value.q}`, () => onChange({ q: "" }));
  }
  if (value.created_from || value.created_to) {
    pushChip("created_at", `생성일: ${value.created_from || "…"} ~ ${value.created_to || "…"}`, () => onChange({ created_from: "", created_to: "" }));
  }
  if (value.est_wd_min || value.est_wd_max) {
    pushChip("est_wd", `예상 WD: ${value.est_wd_min || "…"} ~ ${value.est_wd_max || "…"}`, () => onChange({ est_wd_min: "", est_wd_max: "" }));
  }
  if (value.act_wd_min || value.act_wd_max) {
    pushChip("act_wd", `실제 WD: ${value.act_wd_min || "…"} ~ ${value.act_wd_max || "…"}`, () => onChange({ act_wd_min: "", act_wd_max: "" }));
  }

  const resultConditions = [
    ...activeConditions(value, fields),
    ...(usingDefaultStatus ? ["status"] : []),
    ...(RANGE_KEYS.some((key) => value[key]) ? ["range"] : []),
  ];

  return (
    <>
      {/* 판이 아니다 — 지시 80. 컨트롤 다섯 개를 페이지 폭 흰 사각형에 담으면 오른쪽
          대부분이 빈다. 목록과의 경계는 아래 실선과 결과 줄이 만든다. */}
      <FilterSurface>
        {show("q") ? (
          <ToolbarRow>
            <SearchBox
              value={value.q}
              onSearch={commitSearch}
              placeholder="제목 검색"
              ariaLabel={LABELS.q}
            />
          </ToolbarRow>
        ) : null}
        {/* 순서는 C2 가 정한다: scope(부서) → entity(프로젝트·담당자) → 분류 → 상태 → 기간.
            예전에는 선언 순서가 곧 화면 순서라 화면마다 축의 순서가 달랐다. */}
        <FilterRow>
          {/* scope 가 먼저다 — 「어느 범위를 볼 것인가」는 나머지 조건의 전제다. */}
          {scope}
          {show("project_id") ? (
            <EntityCombobox
              multiple
              label={LABELS.project_id}
              value={asList(value.project_id)}
              onChange={set("project_id")}
              loading={projectsQ.isLoading}
              options={projectOpts}
            />
          ) : null}
          {show("assignee_user_id") ? (
            <EntityCombobox
              multiple
              label={LABELS.assignee_user_id}
              value={asList(value.assignee_user_id)}
              onChange={set("assignee_user_id")}
              loading={assigneesQ.isLoading}
              options={peopleOpts}
            />
          ) : null}
          {show("category") ? (
            <DebouncedTextField label={LABELS.category} value={value.category} onCommit={commitCategory} />
          ) : null}
          {show("status") ? (
            <FilterSelect
              multiple
              label={LABELS.status}
              value={asList(value.status)}
              onChange={set("status")}
              options={statusOpts}
              allLabel={usingDefaultStatus ? "종료 제외" : undefined}
            />
          ) : null}
          {show("priority") ? (
            <FilterSelect
              multiple
              label={LABELS.priority} value={asList(value.priority)} onChange={set("priority")}
              options={priorityOpts}
            />
          ) : null}
          {show("difficulty") ? (
            <FilterSelect multiple label={LABELS.difficulty} value={asList(value.difficulty)} onChange={set("difficulty")} options={difficultyOpts} />
          ) : null}
          {show("due") ? (
            <FilterSelect label={LABELS.due} value={value.due} onChange={set("due")} options={DUE_OPTIONS} kind="date" />
          ) : null}
          {extra}
          {filtered && !atDefault ? (
            <FilterActions>
              <Button variant="ghost" size="sm" onClick={clear}>{resetLabel}</Button>
            </FilterActions>
          ) : null}
        </FilterRow>
      </FilterSurface>
      <FilterChips
        items={chips}
        extraAction={onShowAll && !allStatus ? (
          <Typography
            component="button"
            type="button"
            variant="body2"
            onClick={onShowAll}
            sx={{
              border: 0, background: "none", cursor: "pointer", color: "text.secondary", font: "inherit",
              "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
            }}
          >
            전체 보기
          </Typography>
        ) : null}
      />
      {/* 건수는 «이 조건에 대한 결과» 라는 관계가 보이는 자리에 둔다 — 필터와 목록 사이. */}
      {total != null ? <ResultLine total={total} conditions={resultConditions} /> : null}
    </>
  );
}
