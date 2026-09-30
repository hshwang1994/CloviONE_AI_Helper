import React from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { roleLabel } from "../../lib/roles.js";
import { useInfiniteList } from "../../lib/useInfiniteList.js";
import { Badge, CountChip, DataTable, ErrorState, Section } from "../../ui/kit.jsx";
import { FilterBar, FilterToggle } from "../../ui/FilterBar.jsx";
import { FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { PersonLine } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* 조직 · 부서의 구성원 목록 — 두 판이 같은 부품을 쓴다 (계획 3.6, D-510).
 *
 * 예전 판은 8명까지 아바타와 이름만 그렸다(`OrgPeopleGrid`). 동명이인을 가를 정보가 없었고 큰 부서는 나머지를
 * 볼 길이 사용자 화면뿐이었다. 사용자 목록 API 가 조직으로도, 하위 부서까지로도, 소속 종류로도 거를 수 없었기
 * 때문이다(BACKLOG P-104). 이제 서버가 그 조건을 받고 이 목록이 페이지로 받는다.
 *
 * 조건은 이 판의 상태다(주소가 아니다) — 주소의 `q` 는 왼쪽 조직도 검색이 쓴다. 판은 고른 대상마다 새로 서므로
 * (`OrgConsole` 의 `key`) 다른 부서로 옮기면 조건도 처음으로 돌아간다.
 *
 * 수는 서버의 `total` 이 말한다. 조직도 줄의 수와 같은 규칙(지금 일하는 사람)이 기본 조건이다.
 * 질의 키 뿌리가 `users` 인 이유는 `orgQueries.js` 머리말에 있다 - 사용자 화면이 저장하면 이 목록도 갱신된다. */

const STATE_OPTIONS = [
  { value: "active", label: "활성" },
  { value: "inactive", label: "비활성" },
  { value: "archived", label: "보관" },
];

export const MEMBERSHIP_OPTIONS = [
  { value: "department", label: "부서 소속" },
  { value: "organization", label: "조직 직속" },
  { value: "unassigned", label: "미지정" },
];

function stateOf(user) {
  if (user.archived_at) return { label: "보관", kind: "neutral" };
  if (user.active === false) return { label: "비활성", kind: "warn" };
  return { label: "활성", kind: "ok" };
}

function columnsFor({ showDepartment, duplicateNames }) {
  return [
    {
      key: "display_name", label: "이름", type: "title",
      rowName: (u) => u.display_name || u.email,
      render: (u) => (
        <Box sx={{ minWidth: 0 }}>
          <PersonLine person={u} name={u.display_name} size="xs" />
          {/* 같은 이름이 이 목록에 둘 이상이면 둘째 줄이 이메일이다 - 이름만으로는 누구인지 모른다. */}
          {duplicateNames.has(u.display_name) ? (
            <Typography component="p" sx={{ m: 0, fontSize: FONT_SIZE.bodySm, color: "text.secondary", overflowWrap: "anywhere" }}>
              {u.email}
            </Typography>
          ) : null}
        </Box>
      ),
    },
    { key: "email", label: "이메일", type: "identifier" },
    { key: "title", label: "직책", type: "enum", render: (u) => u.title || "-" },
    showDepartment ? { key: "department", label: "부서", type: "path", render: (u) => u.department || "-" } : null,
    {
      key: "state", label: "상태", type: "status",
      render: (u) => { const s = stateOf(u); return <Badge value={s.label} kind={s.kind} />; },
    },
    { key: "role", label: "역할", type: "enum", render: (u) => roleLabel(u.role) },
  ].filter(Boolean);
}

/**
 * `scope` — `{ kind: "org", orgId }` 또는 `{ kind: "dept", deptId }`.
 * `membership` · `onMembership` — 조직 판만 쓴다(소속 종류 조건). 판이 「미지정 목록 보기」로 바꾼다.
 */
export function OrgMembersList({ scope, title = "구성원", membership = "", onMembership, emptyText }) {
  const nav = useNavigate();
  const [q, setQ] = React.useState("");
  const [state, setState] = React.useState("active");
  const [descendants, setDescendants] = React.useState(false);
  const isDept = scope.kind === "dept";

  const params = React.useMemo(() => {
    const out = {};
    if (isDept) {
      out.department_id = scope.deptId;
      if (descendants) out.include_descendants = "true";
    } else {
      out.org_id = scope.orgId;
      if (membership) out.membership_kind = membership;
    }
    if (q) out.q = q;
    if (state) out.state = state;
    return out;
  }, [isDept, scope.deptId, scope.orgId, descendants, membership, q, state]);

  const list = useInfiniteList({
    key: ["users", "org-members", params],
    rowId: (u) => (u && u.id) || undefined,
    fetch: (page) => api("/api/admin/users?" + new URLSearchParams({
      ...params, page: String(page.page), page_size: String(page.page_size),
    }).toString()),
  });

  const rows = list.rows;
  const duplicateNames = React.useMemo(() => {
    const seen = new Map();
    for (const u of rows) seen.set(u.display_name, (seen.get(u.display_name) || 0) + 1);
    return new Set([...seen].filter(([, n]) => n > 1).map(([name]) => name));
  }, [rows]);
  const showDepartment = !isDept || descendants;
  const columns = columnsFor({ showDepartment, duplicateNames });

  const chips = [
    q ? { key: "q", label: `검색: ${q}`, onDelete: () => setQ("") } : null,
    !isDept && membership ? {
      key: "membership",
      label: `소속: ${(MEMBERSHIP_OPTIONS.find((o) => o.value === membership) || {}).label || membership}`,
      onDelete: () => onMembership && onMembership(""),
    } : null,
  ].filter(Boolean);
  const filtered = chips.length > 0 || state !== "active" || descendants;

  return (
    <Section
      title={title}
      titleAs="h3"
      /* 수는 제목 옆 칩이다 - 지금 조건에 맞는 사람의 수(서버의 `total`)다. */
      action={list.total != null ? <CountChip value={`${list.total}명`} /> : null}
      sx={{ mb: 0 }}
    >
      <Box sx={{ display: "grid", rowGap: 2 }}>
        <FilterBar
          search={<SearchBox value={q} onSearch={setQ} placeholder="이름, 이메일 검색" ariaLabel={`${title} 검색`} />}
          end={isDept ? (
            <FilterToggle pressed={descendants} onClick={() => setDescendants((v) => !v)}>하위 부서 포함</FilterToggle>
          ) : null}
          conditions={chips.length ? {
            chips, total: list.total, unit: "명", noun: "사람",
            onClearAll: () => { setQ(""); if (onMembership) onMembership(""); },
          } : undefined}
        >
          <FilterSelect
            label="상태" value={state} onChange={(v) => setState(v || "")} options={STATE_OPTIONS}
            allLabel="보관 제외 전체"
          />
          {!isDept ? (
            <FilterSelect
              label="소속" value={membership} onChange={(v) => onMembership && onMembership(v || "")}
              options={MEMBERSHIP_OPTIONS}
            />
          ) : null}
        </FilterBar>
        {list.isError ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : (
          <DataTable
            placement="card"
            columns={columns}
            rows={rows}
            rowKey={(u) => u.id}
            loading={list.isLoading}
            onRow={(u) => nav("/users/" + u.id)}
            rowHref={(u) => "#/users/" + u.id}
            empty={filtered ? "조건에 맞는 사람이 없습니다." : (emptyText || "속한 사람이 없습니다.")}
            list={{
              total: list.total, loaded: list.loaded, hasNext: list.hasNext,
              isFetchingNext: list.isFetchingNext, onMore: list.fetchNext, unit: "명", moreLabel: "구성원 더 보기",
            }}
          />
        )}
        {!isDept && membership === "unassigned" ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            여러 사람의 소속을 한 번에 지정하려면 조직 정합성 화면의 사람 탭을 쓰세요.
          </Typography>
        ) : null}
      </Box>
    </Section>
  );
}
