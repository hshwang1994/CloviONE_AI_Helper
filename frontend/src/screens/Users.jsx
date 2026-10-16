import React, { useState } from "react";
import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { ROLE_LABELS } from "../lib/roles.js";
import { expireSession } from "../lib/sessionRedirect.js";
import { diffFields } from "../lib/diffFields.js";
import { fmtDateTime, uaSummary } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { PageHeader, Badge, Button, DataTable, DetailGrid, DetailRow, FormModal, Modal, OverflowMenu, EmptyState, ErrorState, Callout, useConfirm, useToast, ActionFooter } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { useRowSelection, selectionColumn } from "../ui/bulkSelect.jsx";
import { FilterBar, FilterToggle } from "../ui/FilterBar.jsx";
import { useInfiniteList } from "../lib/useInfiniteList.js";
import { CsvTools, useUserBulk } from "./UsersBulk.jsx";
import { buildViewQuery, hashQuery, withHashQuery } from "./datascreen-view.js";
import { DateCell } from "../ui/cells.jsx";
import { toggleSort } from "../ui/TableHeaderCell.jsx";
import { EntityCombobox, FilterSelect, SearchBox, unmatchedLabel } from "../ui/filters.jsx";
import { PersonLine, UserAvatar, personLineLead } from "../ui/UserAvatar.jsx";

// PA-RC-0013: /users만 검색·필터·페이지를 URL에 안 실어서 새로고침·공유에 견디지 못했다
// (대조군 /team-docs·/board·/team-tickets·/audit은 이미 견딘다). DataScreen.jsx가 이미 쓰는
// 순수 함수(datascreen-view.js)의 buildViewQuery/withHashQuery만 가져다 쓴다 — 이 화면은
// registry 기반이 아니라 수제라 DataScreen.jsx 자체는 못 쓰지만, 그 직렬화 로직은
// config.filters 키 목록만 있으면 돌아가는 순수 함수라 registry 없이도 그대로 쓸 수 있다.
// 읽는 쪽은 이미 있는 useSearchParams(HashRouter가 해시 안 쿼리를 그대로 파싱해 준다)를
// 그대로 쓴다 — 쓰는 쪽만 raw history.replaceState로 우회한다(DataScreen.jsx와 동일 이유:
// setSearchParams를 쓰면 아래 220행대의 기존 감시 useEffect가 searchParams 변경 자체에
// 반응해 되먹임 루프에 빠질 위험이 있다).
const USERS_VIEW_CONFIG = {
  filters: [
    { key: "role" }, { key: "active" }, { key: "locked" },
    { key: "department_id" }, { key: "archived" },
  ],
};

// 생성/수정 폼의 역할 선택지를 행위자 권한으로 제한한다. 서버는 비-system_admin이 관리자·시스템
// 관리자 '계정 생성'을 하드 403으로 막고(승인 경로 없음), 역할 '변경'만 관리자 승인 흐름이 있다.
// 그래서 생성은 user/operator/auditor만, 수정은 admin까지(승인) 노출한다.
export function roleOptionsFor(actorRole, mode, allOpts) {
  if (actorRole === "system_admin") return allOpts;
  const allowed = mode === "create" ? ["user", "operator", "auditor"] : ["user", "operator", "auditor", "admin"];
  return allOpts.filter((o) => allowed.includes(o.value));
}

// 입력값이 delay 동안 잠잠할 때만 반영한다 — 타자 한 번마다 요청/스켈레톤 깜빡임을 막는다.
function useDebounced(value, delay) {
  const [v, setV] = useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

/* 역할 이름은 관리 콘솔 한 벌이다(`lib/roles.js::ROLE_LABELS`) — 조직 정합성의 관리자 표가 같은 이름을 쓴다. */
const ROLE_KO = ROLE_LABELS;
const ROLE_OPTS = Object.keys(ROLE_KO).map((v) => ({ value: v, label: ROLE_KO[v] }));
/* 서버의 「부서 없음」 센티널 (P-61, `app/users/router.py::NO_DEPARTMENT`). 부서 id 는 UUID 라
   이 글자와 겹치지 않는다. 목록·CSV 가 같은 필터 문자열을 쓰므로 여기서도 값 하나다. */
const NO_DEPARTMENT = "none";

/** 역할 다섯의 실제 차이 — **서버 권한 표에서 온다** (지시 19).
 *
 * 「관리자는 …를 할 수 있습니다」를 여기 적으면 규칙이 두 벌이 된다. 권한을 서버에서
 * 고쳐도 이 문장은 안 따라오고, **틀린 설명은 아무 오류도 안 낸다.** 그래서 문장을 안 적고
 * `app/core/authz.py::role_help` 가 능력 표에서 계산한 것을 그대로 받는다 — 권한 매트릭스
 * 화면(`#/rbac`)과 **같은 응답이자 같은 질의 키**라 요청은 한 번이다.
 *
 * 못 받아도 화면은 선다. 그때는 설명 없이 이름만 나오고, 그것이 틀린 설명보다 낫다.
 */
export function useRoleHelp(enabled) {
  const { data } = useQuery({
    queryKey: ["admin", "rbac-matrix"],
    queryFn: () => api("/api/admin/rbac-matrix"),
    enabled: !!enabled,
    retry: false,
    staleTime: 300000,
  });
  return (data && Array.isArray(data.role_help)) ? data.role_help : [];
}

/** 역할 한 줄을 사람이 읽는 문장으로. 없으면 빈 문자열이다.
 *
 * 순서가 「성격 → 새로 되는 것 → 안 되는 것」인 이유: 역할을 고르는 사람이 먼저 묻는
 * 것은 「이게 어떤 자리인가」이고, 「바로 아래와 뭐가 다른가」가 그 다음이다. 능력을 전부
 * 나열하면 다섯 줄이 되어 아무도 안 읽는다 — 셋까지만 적고 나머지는 수로 말한다.
 */
export function roleHelpText(row) {
  if (!row) return "";
  const parts = [row.character].filter(Boolean);
  const gains = Array.isArray(row.gains) ? row.gains : [];
  if (gains.length && row.compared_to) {
    const shown = gains.slice(0, 3).join(", ");
    const rest = gains.length > 3 ? ` 외 ${gains.length - 3}가지` : "";
    parts.push(`${row.compared_to}에 더해 ${shown}${rest}도 할 수 있습니다.`);
  }
  const loses = Array.isArray(row.loses) ? row.loses : [];
  if (loses.length && row.compared_to) {
    parts.push(`${row.compared_to}와 달리 ${loses.join(", ")} 권한이 없습니다.`);
  }
  return parts.join(" ");
}

/** 역할 칸 아래에 서는 설명. **다섯을 나란히** 놓는다.
 *
 * 고른 역할 하나만 설명하면 「이 역할이 무엇인가」에는 답하지만 「어느 것을 골라야 하는가」에는
 * 답하지 못한다 — 고르는 사람이 실제로 하는 일은 **비교**다. 다섯이라 한눈에 들어온다.
 *
 * 후보를 걸러 보여 주지 않는다: 행위자가 만들 수 없는 역할(`roleOptionsFor`)도 설명에는
 * 남는다. 「내가 왜 이걸 못 고르나」의 답이 그 줄에 있기 때문이다.
 */
export function RoleHelp({ rows, lead }) {
  const list = Array.isArray(rows) ? rows : [];
  return (
    <Box component="span" sx={{ display: "block" }}>
      {lead ? <Box component="span" sx={{ display: "block" }}>{lead}</Box> : null}
      {list.length ? (
    <Box component="span" sx={{ display: "block", mt: 0.5 }}>
      {list.map((r) => (
        <Box key={r.value} component="span" sx={{ display: "block", mb: 0.375, ...KO_WORD_BREAK }}>
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold }}>{r.label}</Box>
          {": "}
          {roleHelpText(r)}
        </Box>
      ))}
    </Box>
      ) : null}
    </Box>
  );
}

/* 관리 범위 — `app/users/models.py` 의 `ALL_ADMIN_SCOPES` 와 같은 세 값이다.
 * 라벨은 '무엇을 볼 수 있는가'로 쓴다: `global`/`org`/`dept` 는 개발자 말이다. */
const SCOPE_KO = { global: "전체 포털", org: "소속 조직", dept: "소속 부서(하위 포함)" };

/* role=admin + admin_scope 의 조합에 붙는 이름 (RBAC 발견성).
 *
 * app/core/authz.py 의 ROLE_ORDER 와 app/users/models.py 의 admin_scope(global/org/dept)
 * 는 서로 **조합**돼 실제 권한을 만든다 — role=admin + admin_scope=org 가 "조직관리자",
 * dept 가 "부서관리자" 다. 이 조합은 백엔드(app/core/scope.py)에서 이미 동작하고 있었지만
 * 화면 어디에도 이 이름이 없어(설정은 있어도 개념이 안 보여) 관리자가 이 기능 자체를
 * 찾지 못했다. global 은 "전체 관리자" 라고 부르고, system_admin(시스템 관리자)과는
 * 완전히 다른 축(역할이 아니라 범위)이라는 것을 도움말에서 별도로 밝힌다. */
const ADMIN_CONCEPT_KO = { global: "전체 관리자", org: "조직관리자", dept: "부서관리자" };

/* 목록/상세에 붙일 배지. admin 역할이 아니면(system_admin 포함) null — 이 개념은
 * role=admin 조합에만 존재하고, system_admin 은 이미 자기 역할 배지로 구분된다. */
export function adminConcept(row) {
  if (!row || row.role !== "admin") return null;
  const scope = row.admin_scope || "global";
  const label = ADMIN_CONCEPT_KO[scope];
  if (!label) return null;
  // 전체 관리자는 '조직/부서로 좁혀지지 않은 관리자'라는 뜻이라 주의를 끌 필요가 있다(warn),
  // 조직/부서 관리자는 이미 좁혀진 상태를 그대로 알려주는 정보다(info).
  return { label, kind: scope === "global" ? "warn" : "info" };
}

const SCOPE_OPTS = Object.keys(SCOPE_KO).map((v) => ({
  // 드롭다운에서부터 개념 이름이 보이게 — '소속 조직'만 보면 이게 '조직관리자'를 만드는
  // 자리라는 걸 알아채기 어렵다(F2의 "넣는 길이 화면 어디에도 없었다"는 지금까지의 문제).
  value: v, label: SCOPE_KO[v] + "(" + ADMIN_CONCEPT_KO[v] + (v === "global" ? ", 시스템 관리자와는 다른 개념)" : ")"),
}));

/* 상세 패널에 쓸 한 줄. 범위가 `dept`/`org` 인데 대상이 비어 있으면 **그 사람은 아무것도
 * 못 본다** — 저장 경계에서 막지만, 예전 데이터나 CLI 로 들어온 값이 있을 수 있으므로
 * 화면에서도 그 사실을 조용히 넘기지 않는다. */
export function scopeLabel(row, deptOptions) {
  const scope = (row && row.admin_scope) || "global";
  const base = SCOPE_KO[scope] || scope;
  if (scope === "dept") {
    const id = row.scope_dept_id;
    if (!id) return base + " (대상 부서 없음: 아무것도 보이지 않습니다)";
    const hit = (deptOptions && deptOptions.options || []).find((o) => o.value === id);
    return base + ": " + (hit ? hit.label : id);
  }
  if (scope === "org" && !row.scope_org_id) {
    return base + " (대상 조직 없음: 아무것도 보이지 않습니다)";
  }
  return base;
}

/* 화면 안에서 '눌러서 무언가 하는 짧은 글자' — 예전 .c-linkbtn(관리 화면 전용 링크 버튼)을 대신한다.
 * 링크처럼 보이지만 이동이 아니라 동작이므로 <button>이어야 한다(스크린리더가 역할을 옳게 읽는다). */
function LinkButton({ onClick, children }) {
  return (
    <Link component="button" type="button" underline="hover" onClick={onClick} sx={{ font: "inherit", verticalAlign: "baseline" }}>
      {children}
    </Link>
  );
}

// 부서·직책 목록을 드롭다운 옵션으로. 첫 항목은 '없음'(선택 안 함).
// 로드 실패/미등록을 그냥 삼키면 드롭다운이 '없음'만 남아 원인을 알 수 없다 — 상태를 함께 돌려
// 폼이 도움말로 안내하게 한다(등록된 부서가 없음 / 목록을 불러오지 못함).
// currentId/currentLabel — 수정 폼이 여는 대상 사용자에게 지금 지정된 부서·직책. 서버가 active=None으로
// 활성·비활성 모두 돌려주는데도 여기서 active!==false로만 걸러 옵션을 만들면, 배정 이후 비활성화된
// 부서·직책은 목록에서 사라져 FormField가 '선택 안 함'으로 보여준다 — 실제로는 값이 그대로 있는데도
// 화면만 지워진 것처럼 보이고, 이 상태로 저장하면 조용히 다른 값(빈 값)으로 덮어써 버린다. 목록엔 없어도
// 지금 배정된 항목만은 '(비활성)' 표시로 남겨 선택된 채 보이게 한다.
function useNameOptions(endpoint, key, currentId, currentLabel) {
  const q = useQuery({ queryKey: [key], queryFn: () => api(endpoint), retry: false });
  const items = (q.data && q.data.items) || [];
  const activeItems = items.filter((i) => i.active !== false);
  const options = [{ value: "", label: "없음" }, ...activeItems.map((i) => ({ value: i.id, label: i.name }))];
  if (currentId != null && currentId !== "" && !activeItems.some((i) => String(i.id) === String(currentId))) {
    // 목록이 실제로 로드됐을 때만 '(비활성)'을 단정한다 — 로딩 중/오류면 activeItems도 비어 있어,
    // 실제로는 활성인 부서·직책을 '(비활성)'으로 잘못 표시하고(deptHelp/titleHelp의 로딩·오류 안내와
    // 모순) 그대로 저장하면 조용히 값이 바뀔 수 있었다. 목록을 못 불러왔으면 현재 라벨만 넣어 선택을 유지한다.
    const listReady = !q.isLoading && !q.isError && items.length > 0;
    if (listReady) {
      const inactiveItem = items.find((i) => String(i.id) === String(currentId));
      const label = (inactiveItem && inactiveItem.name) || currentLabel || "알 수 없음";
      options.push({ value: currentId, label: label + " (비활성)" });
    } else if (currentLabel) {
      options.push({ value: currentId, label: currentLabel });
    }
  }
  // '항목이 아예 없음'과 '있지만 전부 비활성'을 구분한다 — 후자를 '등록된 게 없다'로 안내하면
  // 관리자가 중복될 수 있는 새 항목을 만들라고 오해한다(실제로는 활성화만 하면 된다).
  const isEmpty = !q.isLoading && !q.isError && items.length === 0;
  const isAllInactive = !q.isLoading && !q.isError && items.length > 0 && activeItems.length === 0;
  return { options, items, isError: q.isError, isLoading: q.isLoading, isEmpty, isAllInactive, refetch: q.refetch };
}

/* 임시 비밀번호 모달 — 생성/재설정 시 서버가 '한 번만' 돌려주는 임시 비밀번호를 보여준다.
 * 토스트(3.5초 자동 소멸)로 흘리면 안 되는 일회성 비밀이라 복사 가능한 지속 모달로 노출한다. */
function TempPasswordModal({ data, onClose }) {
  const toast = useToast();
  // Ops.jsx 진단 번들 '복사' 버튼과 같은 패턴 — 토스트(3.5초 소멸)만으론 라벨 변화가 스크린리더에
  // 안 들린다는 이유로 이미 그 화면에서 버튼 라벨을 잠깐 '복사됨'으로 바꾸는 방식을 쓰고 있다.
  const [copied, setCopied] = useState("");
  /* 복사가 안 된 사실 — 모달 안에 남는다(직접 선택해 복사해야 하는 사람이 읽을 수 있게). 다시 누르면 걷힌다. */
  const [copyNotice, setCopyNotice] = useState(null);
  const copiedTimerRef = React.useRef(null);
  React.useEffect(() => () => { if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current); }, []);
  if (!data) return null;
  function copy() {
    setCopyNotice(null);
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(data.password).then(() => {
      setCopied("복사됨");
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = setTimeout(() => setCopied(""), 1500);
      toast("복사했습니다.", "success");
    }, () => setCopyNotice({ tone: "danger", text: "복사하지 못했습니다. 직접 선택해 복사하세요." }));
    else setCopyNotice({ tone: "info", text: "복사를 지원하지 않는 환경입니다. 직접 선택해 복사하세요." });
  }
  const footer = (
    <ActionFooter placement="modal">
      <Button onClick={copy}>{copied || "복사"}</Button>
      <Button variant="primary" onClick={onClose}>확인</Button>
    </ActionFooter>
  );
  return (
    <Modal open onClose={onClose} title="임시 비밀번호" size="sm" footer={footer}>
      <Typography sx={{ whiteSpace: "pre-line" }}>{data.notice || "이 임시 비밀번호는 지금 한 번만 표시됩니다. 사용자에게 안전하게 전달하세요."}</Typography>
      {copyNotice ? <Callout tone={copyNotice.tone} compact>{copyNotice.text}</Callout> : null}
      {/* role="textbox"는 스크린리더에 '편집 가능'으로 읽히지만 실제로는 도달 불가였다.
          포커스 가능한 읽기 전용 텍스트로 바꿔(tabIndex) 키보드로 접근, 선택할 수 있게 한다.
          aria-label을 달면 접근 가능한 이름 계산을 그 문자열이 덮어써('임시 비밀번호'만 들리고
          실제 비밀번호 글자는 낭독되지 않는다), 위 안내 문단이 이미 맥락을 주므로 라벨 없이 값
          텍스트 자체가 접근 가능한 이름이 되게 둔다.
          user-select:all — 비밀번호는 기호가 섞여 있어 더블클릭으로는 한 토막만 잡힌다. */}
      <Box
        tabIndex={0}
        sx={{
          mt: 1.5, p: 1.5, border: 1, borderColor: "divider", borderRadius: 2,
          bgcolor: "action.hover", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
          fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.bold, letterSpacing: "0.03em",
          userSelect: "all", overflowWrap: "anywhere", textAlign: "center",
        }}
      >
        {data.password}
      </Box>
    </Modal>
  );
}

/* 사용자 관리(§6.2) — 목록은 핵심 정보만. 행을 누르면 상세 모달에서 전체 정보 + 작업. 추가·수정은
 * 공통 중앙 모달 폼. 임시 비밀번호는 일회성 모달로 노출. '보관된 계정 보기'로 복구도 가능.
 *
 * 2026-08 MUI 재설계: 손으로 쓴 입력(.c-search/.c-filter)·페이저·상세 라벨줄을 MUI로 옮겼다.
 * 값은 px가 아니라 rem/테마 값이라 4K에서 글자·여백이 같이 커진다(styles/root.css 레버). */
export function Users() {
  // 통합 검색(Ctrl+K)에서 사람을 고르면 `#/users?q=<이름>` 으로 온다. 초기값을 주소에서
  // 받지 않으면 결과를 눌렀는데 필터 없는 전체 목록이 뜬다 — 아무 일도 안 한 것처럼 보인다.
  const [searchParams, setSearchParams] = useSearchParams();
  // PA-RC-0024: /users/:id — 이 화면 "자신의" 주소가 상세를 가리키는 경우. 아래 ?id=
  // 딥링크(다른 화면이 보내는, 한 번 쓰고 지우는 프리필)와는 다른, 지속적인 canonical
  // 주소다. AdminRoutes.jsx가 /users와 /users/:id 둘 다 이 컴포넌트로 보낸다.
  const routeId = useParams().id;
  /* 다른 화면이 `?id=` 로 넘긴 사용자를 못 연 사실 — 목록 위에 남는다(사라지는 토스트였을 때는 빈 목록에
     떨어진 것처럼 보였다). 다음에 누가 열리면 걷힌다. */
  const [deepLinkFailure, setDeepLinkFailure] = React.useState("");
  const navigate = useNavigate();
  const [q, setQ] = useState(() => searchParams.get("q") || "");
  // PA-RC-0013: 아래 다섯 필터·페이지도 q/department_id와 같은 방식으로 최초 마운트에
  // 주소를 읽는다 — 이 게으른 초기화(useState 함수형 초기값)는 DataScreen.jsx가 이미
  // 쓰는 관용과 같다(마운트 후 setState로 넣으면 기본값으로 한 번 조회했다가 다시
  // 조회해 목록이 두 번 깜빡인다).
  const [roleFilter, setRoleFilter] = useState(() => searchParams.get("role") || "");
  const [activeFilter, setActiveFilter] = useState(() => searchParams.get("active") || "");
  // ADM-06R: 화면·배지(잠김)·잠금 해제 버튼은 이미 다 있는데 "지금 잠긴 사람만 보기"가
  // 안 됐다 — 활성 필터와 같은 모양으로 추가한다.
  const [lockedFilter, setLockedFilter] = useState(() => searchParams.get("locked") || "");
  const [showArchived, setShowArchived] = useState(() => searchParams.get("archived") === "true");
  // 조직도·부서 관리에서 '소속 인원 보기'로 오면 `#/users?department_id=<id>` 다. 백엔드는
  // 이 필터를 이미 지원했지만 화면이 주소를 읽지 않아, 눌러도 필터 없는 전체 목록이 떴다.
  const [deptFilter, setDeptFilter] = useState(() => searchParams.get("department_id") || "");
  const [sortKey, setSortKey] = useState(() => searchParams.get("sort") || "display_name");
  const [sortOrder, setSortOrder] = useState(() => searchParams.get("order") || "asc");
  // 위 두 useState 초기화 함수는 **최초 마운트에서 딱 한 번만** 주소를 읽는다. 그런데
  // 이 화면이 이미 열려 있는 채로(다른 사람 상세를 보던 중 등) 통합 검색·조직도에서
  // 같은 "/users" 라우트로 또 딥링크가 오면(예: q=철수 → q=영희), react-router는 이미
  // 마운트된 <Users/>를 재마운트하지 않으므로 이 초기화 함수가 다시 실행되지 않는다 —
  // 주소는 바뀌었는데 화면은 이전 사람 기준 필터를 계속 보여줘, 바로 위 주석이 막으려던
  // "결과를 눌렀는데 아무 일도 안 한 것처럼 보인다"는 증상을 '최초 진입'이 아닌 경로에서는
  // 그대로 겪는다. 내비게이션으로 주소 문자열 자체가 바뀔 때만(사용자가 화면 안에서 검색어를
  // 직접 지우거나 바꾸는 것은 주소를 바꾸지 않는다) 다시 읽어 반영한다.
  // null(주소 문자열로는 절대 안 나오는 값)로 시작한다 — q/deptFilter는 최초 마운트를 자기
  // useState 초기화 함수로 이미 처리하니 이 효과가 처음엔 건너뛰어도 되지만, id(NOTI-04R,
  // 아래)는 그런 초기화 함수가 없는 "한 번 실행할 동작"이라 최초 마운트에도 반드시 이 효과가
  // 돌아야 한다 — 처음엔 searchParams.toString()으로 시작했더니 첫 렌더의 key와 곧바로
  // 같아져 최초 진입에서 이 효과 전체(따라서 id 처리도)가 조용히 건너뛰어졌었다.
  const appliedSearchRef = React.useRef(null);
  React.useEffect(() => {
    const key = searchParams.toString();
    if (key === appliedSearchRef.current) return;
    appliedSearchRef.current = key;
    setQ(searchParams.get("q") || "");
    setDeptFilter(searchParams.get("department_id") || "");
    setSortKey(searchParams.get("sort") || "display_name");
    setSortOrder(searchParams.get("order") || "asc");
    // NOTI-04R — 다른 화면(알림 벨/목록, 조직도, 감사 로그)이 `?id=`로 특정 사용자를 곧바로
    // 상세로 열 수 있게 한다. 이 화면은 registry 기반이 아니라 수제라 다른 화면들이 쓰는
    // DataScreen.jsx의 `onQuery: {open:"select", id}` 배선을 그대로 못 쓴다 — 같은 계약
    // (단건 GET, 목록에 없어도/다른 페이지여도 열림, 실패 시 이유를 알림)을 여기서 직접 만든다.
    // sel/toast는 이 컴포넌트 아래쪽에서 선언되지만 이 효과의 콜백은 렌더가 끝난 뒤(그
    // 선언들이 이미 실행된 뒤)에만 실행되므로 참조해도 안전하다.
    const id = searchParams.get("id");
    if (id) {
      api("/api/admin/users/" + id)
        .then((item) => { if (item) { setDeepLinkFailure(""); setSel(item); } })
        .catch(() => setDeepLinkFailure("연결된 사용자를 열지 못했습니다(삭제되었거나 접근 권한이 없을 수 있습니다). 목록에서 다시 확인해 주세요."));
      // 한 번 연 뒤에는 주소에서 지운다 — 안 지우면 드로어를 닫고 새로고침할 때마다 같은
      // 사용자가 다시 열린다(DataScreen.jsx가 해시 쿼리를 지우는 것과 같은 이유).
      setSearchParams((prev) => { const next = new URLSearchParams(prev); next.delete("id"); return next; }, { replace: true });
    }
  }, [searchParams]);
  /* 🔴 쪽 번호는 **상태가 아니다.** 목록은 쪽을 넘기지 않고 묶음을 이어 받는다. 옛 주소·
     저장된 뷰는 여전히 `page=3` 을 들고 오므로 그만큼 미리 받아 대략 그 자리에 떨어뜨린다.
     여기 있던 「필터가 바뀌면 1쪽으로, 단 마운트는 빼고」 효과도 함께 사라진다 —
     조건이 바뀌면 질의 키가 바뀌며 받아 둔 묶음을 통째로 버리므로 되돌릴 쪽이 없다. */
  const resumeChunks = (() => {
    const n = parseInt(searchParams.get("page"), 10);
    return Number.isFinite(n) && n >= 1 ? n : 1;
  })();
  const dq = useDebounced(q, 250); // 검색어는 250ms 디바운스 후에만 쿼리로 들어간다
  // PA-RC-0013: 지금 상태를 주소로 되쓴다(DataScreen.jsx와 같은 raw history.replaceState —
  // setSearchParams를 쓰지 않는 이유는 위 import 옆 주석 참고). 이 효과는 반드시 위 id를
  // 소비하는 효과보다 **아래**(=나중 실행)여야 한다 — 그 효과가 `?id=`를 지우려고
  // setSearchParams(prev => ...)를 부르는데, 그 prev가 react-router가 들고 있는 옛
  // searchParams라 우리가 먼저 raw로 써 두면 그 삭제가 우리 값까지 함께 덮어쓴다.
  const viewQuery = (() => {
    const base = buildViewQuery(
    {
      q: dq,
      filters: {
        role: roleFilter, active: activeFilter, locked: lockedFilter,
        department_id: deptFilter, archived: showArchived ? "true" : "",
      },
    },
    USERS_VIEW_CONFIG,
    );
    if (sortKey === "display_name" && sortOrder === "asc") return base;
    return [base, "sort=" + encodeURIComponent(sortKey), "order=" + encodeURIComponent(sortOrder)].filter(Boolean).join("&");
  })();
  React.useEffect(() => {
    const next = withHashQuery(window.location.hash, viewQuery);
    if (next !== window.location.hash) {
      try { window.history.replaceState(null, "", next); } catch (e) { /* ignore */ }
    }
  }, [viewQuery]);
  // 대량 작업 선택 집합. 페이지·필터가 바뀌어도 유지된다 — 여러 페이지에 걸쳐 고른 뒤
  // 한 번에 처리하는 것이 이 기능의 목적이기 때문이다(서버는 id 목록만 본다).
  const selection = useRowSelection();
  const [sel, setSel] = useState(null);
  /* 상세 창의 열쇠 — **다른 사람으로 바뀔 때만** 바뀐다. 화면은 사람을 열 때 다시 마운트되지 않으므로(`navEntry.jsx::
     screenKeyOf`), 창 안의 순간 상태(작업 알림 · 복사 표시 · 진행 중 표시)가 뒤로 가기로 넘어간 다음 사람에게 따라가지 않게
     한다. 닫힐 때는 마지막으로 연 사람의 열쇠를 그대로 둔다 — 같은 창이 닫혀야 닫힘 전환이 그려진다. */
  const detailKey = React.useRef("");
  if (sel && sel.id != null && String(sel.id) !== detailKey.current) detailKey.current = String(sel.id);
  // PA-RC-0033: :id 라우트로 들어왔는데 그 사용자가 없으면(삭제됨/권한 밖) 예전엔 토스트 하나만
  // 뜨고 몇 초 뒤 사라지면 화면엔 흔적이 남지 않았다 — sel과 별개로 들고 있다가 아래 UserDetail의
  // Modal 자리에 기존 ErrorState를 그린다(DataScreen.jsx와 같은 계약, 새 컴포넌트 없음).
  const [routeIdNotFound, setRouteIdNotFound] = useState(false);
  // PA-RC-0024: 위쪽 ?id= 효과(다른 화면이 보내는, 소비 후 지우는 프리필)와 같은 계약
  // (단건 GET, 실패 시 이유 안내)을 경로 :id에도 건다 — 이쪽은 소비 후 지우지 않는다
  // (경로 자체가 상태이므로 지울 대상이 없다). sel 선언 아래 둔 이유는 단순하다 — 이
  // 효과의 의존성 배열이 sel을 읽는데, useState 호출보다 위에서 그 값을 참조하면(클로저
  // 안이 아니라 배열 리터럴 자체가 그 줄에서 바로 평가되므로) "Cannot access 'sel' before
  // initialization"으로 죽는다(실제로 겪음 — 처음에는 ?id= 효과 바로 아래 뒀었다).
  //
  // routeIdSettledRef: :id로 막 들어온 마운트 첫 렌더에서는 sel이 아직 null이다(아래 GET이
  // 안 끝났다) — 그 순간 아래 "반대 방향" 효과가 그걸 "닫혔다"로 오해해 주소를 /users로
  // 지웠다가 GET이 끝나면 다시 /users/:id로 되돌리는 깜빡임이 실제로 있었다(시험이 실패해
  // 잡음 — MemoryRouter라 눈에는 안 보이지만 순서가 실제로 그렇게 돈다). :id가 없으면
  // 기다릴 것도 없으므로 처음부터 true.
  const routeIdSettledRef = React.useRef(!routeId);
  React.useEffect(() => {
    if (!routeId) { routeIdSettledRef.current = true; return; }
    if (sel && String(sel.id) === String(routeId)) { routeIdSettledRef.current = true; return; }
    setRouteIdNotFound(false);
    api("/api/admin/users/" + routeId)
      .then((item) => { if (item) setSel(item); else setRouteIdNotFound(true); })
      // PA-RC-0033: 서버는 없는 레코드와 권한 밖 레코드를 둘 다 404로 접어 준다(IDOR 정보 누출
      // 방지) — 여기서도 그 판단을 그대로 표현만 한다, 새로 구분하지 않는다. 몇 초 뒤 사라지는
      // 토스트 대신 화면에 계속 남는 ErrorState로 바꾼다(아래 UserDetail).
      .catch(() => setRouteIdNotFound(true))
      .finally(() => { routeIdSettledRef.current = true; });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId]);
  // 반대 방향 — sel이 바뀌면(행 클릭으로 열림, 닫기로 사라짐) 주소를 따라가게 한다.
  // replace를 써 뒤로가기 한 번에 상세만 닫히고 목록까지 나가지 않게 한다. 지금 쿼리
  // 문자열(검색어·필터)을 함께 실어야 한다 — 안 그러면 상세를 열자마자 그 필터들이
  // 주소에서 사라진다. react-router의 searchParams가 아니라 window.location.hash를
  // 직접 읽는다 — 이 화면은 필터 상태를 raw history.replaceState로도 쓰므로(위
  // viewQuery 효과) react-router가 추적하는 값이 그 사이 낡았을 수 있다.
  React.useEffect(() => {
    if (!routeIdSettledRef.current) return;
    const nextId = sel ? String(sel.id) : null;
    if (nextId === (routeId || null)) return;
    const qs = hashQuery(window.location.hash);
    const base = nextId ? "/users/" + nextId : "/users";
    navigate(qs ? base + "?" + qs : base, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [tempPw, setTempPw] = useState(null);
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const auth = useAuth();
  const actorRole = auth.data && auth.data.role;
  const dept = useNameOptions("/api/admin/departments", "departments", editing && editing.department_id, editing && editing.department);
  const title = useNameOptions("/api/admin/job-titles", "job-titles", editing && editing.title_id, editing && editing.title);
  // 관리 범위가 '조직'일 때 실제로 어느 조직인지 고를 목록. 서버는 사용자 레코드에 조직 이름을
  // 돌려주지 않으므로(부서·직책과 달리) id를 그대로 폴백 라벨로 쓴다("이름을 못 찾으면 id라도
  // 보인다"는 scopeLabel과 같은 방침).
  const org = useNameOptions("/api/admin/organizations", "organizations", editing && editing.scope_org_id, editing && editing.scope_org_id);
  // 비밀번호 입력 도움말이 12자/3종을 하드코딩하고 있었다 — 실제로 강제되는 값은 Settings 화면에서
  // 관리자가 바꿀 수 있는 password_policy(app/users/service.py)다. 정책이 바뀌어도 여기 문구가
  // 계속 옛 기본값을 말하지 않도록, 지금 적용 중인 값을 읽어와 문구에 반영한다.
  const pwPolicyQ = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/admin/settings"), retry: false, staleTime: 60 * 1000 });
  const pwPolicy = (pwPolicyQ.data && pwPolicyQ.data.settings && pwPolicyQ.data.settings.password_policy && pwPolicyQ.data.settings.password_policy.value) || {};
  const pwMinLen = pwPolicy.min_length != null ? pwPolicy.min_length : 12;
  const pwMinClasses = pwPolicy.min_classes != null ? pwPolicy.min_classes : 3;
  const pwHelp = "비우면 임시 비밀번호가 자동 생성되어 화면에 한 번 표시됩니다. 직접 입력하려면 " + pwMinLen + "자 이상, 문자 종류(대/소문자, 숫자, 기호) " + pwMinClasses + "종 이상을 조합하세요.";
  // 부서, 직책 드롭다운의 실패/미등록 상태를 폼 도움말로 노출한다(막다른 '없음'만 남는 문제).
  // 목적지 화면 이름만 언급하는 정적 텍스트였던 것을 실제로 누를 수 있는 링크로 바꾼다, 새 탭으로
  // 열어(target=_blank) 작성 중이던 사용자 추가/수정 폼(반쯤 채운 값)을 잃지 않고 부서/직책을 먼저
  // 만들고 돌아올 수 있게 한다. FormField(kit.jsx)는 help를 그대로 렌더 자식으로 넣어 문자열 외에
  // React 노드도 받을 수 있다.
  const deptHelp = dept.isError ? (<>부서 목록을 불러오지 못했습니다. <LinkButton onClick={() => dept.refetch()}>다시 시도</LinkButton></>)
    : dept.isLoading ? "부서 목록을 불러오는 중…"
    : dept.isEmpty ? (<>등록된 부서가 없습니다. <Link href="#/departments" target="_blank" rel="noreferrer noopener" underline="hover">‘조직 관리’에서 먼저 추가하세요</Link>(새 탭)</>)
    : dept.isAllInactive ? (<>등록된 부서가 모두 비활성 상태입니다. <Link href="#/departments" target="_blank" rel="noreferrer noopener" underline="hover">‘조직 관리’에서 활성화하세요</Link>(새 탭)</>) : undefined;
  const titleHelp = title.isError ? (<>직책 목록을 불러오지 못했습니다. <LinkButton onClick={() => title.refetch()}>다시 시도</LinkButton></>)
    : title.isLoading ? "직책 목록을 불러오는 중…"
    : title.isEmpty ? (<>등록된 직책이 없습니다. <Link href="#/job-titles" target="_blank" rel="noreferrer noopener" underline="hover">‘직책 관리’에서 먼저 추가하세요</Link>(새 탭)</>)
    : title.isAllInactive ? (<>등록된 직책이 모두 비활성 상태입니다. <Link href="#/job-titles" target="_blank" rel="noreferrer noopener" underline="hover">‘직책 관리’에서 활성화하세요</Link>(새 탭)</>) : undefined;
  const orgHelp = org.isError ? (<>조직 목록을 불러오지 못했습니다. <LinkButton onClick={() => org.refetch()}>다시 시도</LinkButton></>)
    : org.isLoading ? "조직 목록을 불러오는 중…"
    : org.isEmpty ? (<>등록된 조직이 없습니다. <Link href="#/organizations" target="_blank" rel="noreferrer noopener" underline="hover">‘조직 관리’에서 먼저 추가하세요</Link>(새 탭)</>)
    : undefined;
  // 목록·CSV 내보내기가 **같은 필터 문자열**을 쓴다. 두 벌로 만들면 화면에 필터를 걸고
  // 내보낸 파일에 전 직원이 담기는 식으로 갈라지고, 그건 파일을 열기 전까지 아무도 모른다.
  function filterParams(pageParams) {
    const p = pageParams && pageParams.page > 1 ? ["page=" + pageParams.page] : [];
    if (dq) p.push("q=" + encodeURIComponent(dq));
    if (roleFilter) p.push("role=" + encodeURIComponent(roleFilter));
    if (activeFilter) p.push("active=" + activeFilter);
    if (lockedFilter) p.push("locked=" + lockedFilter);
    if (deptFilter) p.push("department_id=" + encodeURIComponent(deptFilter));
    if (showArchived) p.push("archived=true");
    if (sortKey !== "display_name" || sortOrder !== "asc") {
      p.push("sort=" + encodeURIComponent(sortKey));
      p.push("order=" + encodeURIComponent(sortOrder));
    }
    return p.join("&");
  }
  const query = useInfiniteList({
    key: ["users", dq, roleFilter, activeFilter, lockedFilter, deptFilter, showArchived, sortKey, sortOrder],
    rowId: (r) => (r && r.id) || undefined,
    resume: resumeChunks,
    fetch: (pageParams) => api("/api/admin/users?" + filterParams(pageParams)),
  });
  // 사용자를 만들거나(부서/직책/조직 배정) 고치거나(단일 수정 또는 UsersBulk.jsx 대량 지정),
  // 부서·직책·조직 화면(registry/org.js)과 조직도(OrgTree.jsx)가 보여주는 소속/보유 인원
  // (user_count)이 함께 낡는다 — 그 화면들의 드롭다운(위 useNameOptions)도 이 화면과 같은
  // ["departments"]/["job-titles"]/["organizations"] 캐시를 읽고, 삭제 버튼 게이팅
  // (when: (r) => !r.user_count)도 그 인원 수를 본다. 여기 한 곳에서 함께 무효화해 화면을
  // 나갔다 돌아오지 않아도 최신 인원 수를 보게 한다.
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["departments"] });
    qc.invalidateQueries({ queryKey: ["job-titles"] });
    qc.invalidateQueries({ queryKey: ["organizations"] });
    qc.invalidateQueries({ queryKey: ["org-tree"] });
  };
  const total = query.total;
  /* 고른 사용자에게 할 일 — 목록 판 발의 선택 묶음과, 선택을 비운 뒤에도 남는 실패 줄(`UsersBulk.jsx::useUserBulk`). */
  const bulk = useUserBulk({ selection, deptOptions: dept.options, titleOptions: title.options, onDone: refresh });

  /* 열 폭은 화면이 정하지 않는다 — 타입과 열 등급(필수 · 보조 · 문맥)을 주면 `DataTable` 의 열 배분(`columnPlan.planColumns`,
   * D-529)이 표가 받은 폭에서 나눈다. 예전에 8개 열에 고정 rem 을 주었을 때는 폭 합이 1366 의 판을 넘어 이메일 · 이름 · 날짜가
   * 단어 중간에서 꺾였다. 좁으면 보조 열부터 숨기고 표가 그 사실을 말하며, 필수 열은 숨기지 않는다. */
  const columns = [
    // 대량 작업의 선택 열. 체크박스 클릭은 행 클릭(상세 열기)으로 번지지 않는다(bulkSelect.jsx).
    selectionColumn(selection, query.rows.map((r) => r.id)),
    // SEM-01: 선택 체크박스가 첫 열이라(rowName:false로 스스로 제외됨) 표식 없이는 이 표의
    // "상세 보기" 버튼과 체크박스 라벨(selectLabel, bulkSelect.jsx) 둘 다 모든 행이
    // 동일했다 — 이미 화면에 보이는 이메일로 실제로 구별되는 이름을 만든다.
    // PA-RC-0029: 이메일이 이 표의 유일한 고유 식별자인데 131px로 20/20행이 잘렸다(필요
    // 198px) — 같은 표의 '역할'(295px)·'최근 로그인'(287px)이 내용량과 무관하게 더 넓었다.
    // identifier:true 가 식별자 바닥(11rem)과 남는 폭의 몫(비중 2, 상한 22rem)을 준다(D-529).
    { key: "email", label: "이메일", identifier: true, sortable: true, rowName: (r) => r.display_name || r.email },
    {
      // 사람은 얼굴과 함께 선다(D-556) — 조직 관리의 구성원 표와 같은 `PersonLine` 이라 같은 사람이 같은 그림이다.
      key: "display_name", label: "이름", type: "name", sortable: true,
      value: (r) => r.display_name || "알 수 없음",
      lead: personLineLead("xs"),
      render: (r) => <PersonLine person={r} name={r.display_name} size="xs" />,
    },
    {
      // 역할은 이 표에서 가장 민감한(권한 상승 가능성이 있는) 열인데, '활성'·'잠김'과
      // 달리 유일하게 색 없는 맨 텍스트였다 — 같은 Badge 관례로 등급을 색으로도 구분한다.
      // 등급을 색으로 구분한다: system_admin(purple)·admin(warn)·operator/auditor(info, 권한 있는 비-관리자)·
      // 일반 사용자(neutral). 예전엔 operator/auditor가 일반 사용자와 같은 무채색이라 '관리자 아래는 다 같다'로
      // 읽혀, 색 구분의 취지(민감한 역할 열을 등급으로 구분)가 절반만 전달됐다.
      // system_admin은 원래 danger(빨강)였다(VIS-39/DS-08) — 이 제품에서 빨강은 "실패·위험"을
      // 뜻하는 상태색이라(대시보드의 실패 작업 위험 등) 최고 권한 배지가 마치 오류처럼 읽혔다.
      // purple은 이미 검증된 톤(다크모드·대비 확인됨, EXTRA_TONE_VARS)이면서 상태 팔레트
      // (ok/danger/warn/info)와 안 겹쳐 "특별한 등급"을 상태와 안 헷갈리게 표현한다.
      key: "role", label: "역할", type: "enum",
      // PA-RC-0029: 배지 1~2개(짧은 한국어 라벨)만 담는데 295px를 썼다 — 내용량과 무관한 폭이었다. 이제 폭은 그린
      // 글자(`hint` — 역할 이름과 관리 범위 배지)의 가장 긴 것이 정한다(D-529, 열 배분의 값 길이).
      /* 잘린 칸의 hover 글자는 그린 이름이다 — 원래 값(`system_admin`)이 아니다(`kit.jsx::columnCellHint`). */
      hint: (r) => [ROLE_KO[r.role] || r.role, adminConcept(r) && adminConcept(r).label].filter(Boolean).join(", "),
      // admin 역할은 admin_scope 조합으로 실제 성격이 갈린다(조직관리자/부서관리자/전체
      // 관리자) — 역할 배지 하나만으로는 이 화면 어디서도 그 조합이 보이지 않았다(RBAC
      // 발견성 문제). 개념이 있는 조합에만 두 번째 배지를 나란히 붙인다.
      render: (r) => {
        const concept = adminConcept(r);
        return (
          <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
            <Badge value={ROLE_KO[r.role] || r.role} kind={r.role === "system_admin" ? "purple" : r.role === "admin" ? "warn" : (r.role === "operator" || r.role === "auditor") ? "info" : "neutral"} />
            {concept ? <Badge value={concept.label} kind={concept.kind} /> : null}
          </Box>
        );
      },
    },
    {
      // 잠긴(locked) 계정은 활성 상태와 별개 신호라 '활성' 배지만으론 목록에서 구분되지 않는다 —
      // 잠긴 계정은 겉보기엔 활성 계정과 똑같이 보여, 관리자가 이메일을 미리 알고 검색하지 않는 한
      // 목록에서 잠금을 발견할 방법이 없었다. 같은 셀에 잠금 배지를 함께 보여 준다(별도 열 없이).
      // 여러 배지를 한 그룹으로 묶는다 — 좁은 화면 카드 뷰에서 배지가 라벨과 함께 흩어지지 않게
      // 하나의 inline-flex 그룹으로 두고, 배지 사이 간격도 gap이 담당한다(예전엔 공백 텍스트 노드였다).
      // 수명주기(사용 중/비활성/보관됨)는 배타적인 한 개다 — 판정과 이유는 lifecycleBadge 에 있다(X14).
      // 열 이름도 '활성'이 아니라 '상태'다: 이 열이 답하는 것은 "활성인가"가 아니라 "지금 이
      // 계정으로 로그인이 되는가, 안 된다면 어느 문을 열어야 하는가"이기 때문이다.
      key: "active", label: "상태", type: "status",
      render: (r) => {
        const life = lifecycleBadge(r);
        return (
          <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
            <Badge value={life.label} kind={life.kind} />
            {r.locked ? <Badge value="잠김" kind="danger" /> : null}
          </Box>
        );
      },
    },
    // 상세 드로어(Row label="부서"/"직책")는 inactiveSuffix로 '(비활성)'을 붙이는데 목록 열은
    // render 없이 원시 텍스트만 보여줘 같은 화면 안에서 같은 사실이 다르게 보였다 — 같은 헬퍼로 맞춘다.
    /* 부서 · 직책은 보조 열이다 — 좁으면 최근 로그인 · 생성 일자 다음으로 숨는다. 이름 · 이메일 · 상태 · 역할은 필수다(D-529). */
    { key: "department", label: "부서", type: "enum", tier: "secondary", value: (r) => r.department ? r.department + inactiveSuffix(dept, r.department_id) : "-" },
    { key: "title", label: "직책", type: "enum", tier: "secondary", value: (r) => r.title ? r.title + inactiveSuffix(title, r.title_id) : "-" },
    // RESP-01: 900~1200 구간(사이드바 아직 안 접힘)에서 열을 전부 채우면 TableContainer가
    // 가로 스크롤을 겪는다(실측, /users). 이메일·이름·역할·상태·부서·직책은 훑어보기의
    // 핵심이지만 아래 둘은 상세에서도 바로 확인되는 부가 정보라 그 구간에서만 뺀다.
    // PA-RC-0029: 'ko-KR' Intl 포맷(dateStyle:medium+timeStyle:short)이 "2026. 8. 17. 오후
    // 3:24"처럼 길어 287px를 자연스럽게 요구했다 — 이메일보다 우선순위가 낮은 보조 열이라
    // width로 줄인다. overflowWrap:anywhere가 이미 있어(kit.jsx) 좁아지면 두 줄로 접힐 뿐
    // 잘리지 않는다.
    { key: "last_login_at", label: "최근 로그인", type: "datetime", nowrap: true, render: (r) => <DateCell value={r.last_login_at} />, hideNarrow: true },
    { key: "created_at", label: "생성 일자", type: "datetime", sortable: true, nowrap: true, render: (r) => <DateCell value={r.created_at} />, hideNarrow: true },
  ];

  const items = query.rows;
  const hasFilter = !!(q || roleFilter || activeFilter || lockedFilter || deptFilter || showArchived);
  // 실제 '내용' 필터(검색·역할·활성·잠김·부서)만 — '보관된 계정 보기' 토글은 뷰 전환일 뿐 지울 필터가 아니다.
  const hasContentFilter = !!(q || roleFilter || activeFilter || lockedFilter || deptFilter);
  function clearFilters() { setQ(""); setRoleFilter(""); setActiveFilter(""); setLockedFilter(""); setDeptFilter(""); setShowArchived(false); }
  // 내용 필터만 지운다(보관함 뷰는 유지) — 툴바의 '필터 지우기'가 clearFilters를 쓰면 보관함을
  // 보던 중에도 showArchived까지 조용히 꺼져 뷰가 바뀌었다(뷰 전환과 필터 지우기는 다른 조작이다).
  function clearContentFilters() { setQ(""); setRoleFilter(""); setActiveFilter(""); setLockedFilter(""); setDeptFilter(""); }
  // 걸린 부서 조건을 이름으로 말한다 — id 만 주소에 있으면 칩이 UUID 를 보인다.
  const deptFilterName = deptFilter
    ? ((dept.items || []).find((d) => String(d.id) === String(deptFilter)) || {}).name
    : null;
  /* 부서 칸의 후보 — 「미지정」(서버의 「부서 없음」 센티널 `none`, P-61)이 맨 앞이고 부서가 뒤다. 비활성 부서도 후보에
     남는다: 그 부서에 아직 사람이 있을 수 있고, 표의 「부서」 열도 그 부서를 「(비활성)」으로 보인다. 같은 이름의 부서가
     다른 조직에 있을 수 있어 조직 이름을 보조 줄로 낸다. */
  const deptFilterOptions = [{ value: NO_DEPARTMENT, label: "미지정" }].concat(
    (dept.items || []).map((d) => ({
      value: d.id,
      label: d.name + (d.active === false ? " (비활성)" : ""),
      secondary: d.org_name || undefined,
    })),
  );
  /* 예전에 여기 있던 것: 「이 쪽이 비었는데 앞 쪽엔 있으면 앞 쪽으로 되돌린다」. 쪽 번호가
     없어지면서 그 되돌리기가 필요한 상태 자체가 사라졌다 — 마지막 행이 보관되면 목록이
     그만큼 짧아질 뿐이고, 사용자는 여전히 자기가 보던 자리에 있다. */

  // 역할 설명은 **관리 콘솔 권한 표**에서 온다. 이 화면을 열 수 있는 사람이면 그 표도
  // 읽을 수 있다(둘 다 `console.read`) — 못 읽으면 빈 목록이라 설명 없이 이름만 나온다.
  const roleRows = useRoleHelp(true);

  const createFields = [
    { name: "email", label: "이메일", type: "email", required: true, help: "로그인 아이디로 쓰입니다." }, { name: "display_name", label: "이름", type: "text", required: true }, { name: "role", label: "역할", type: "select", value: "user", options: roleOptionsFor(actorRole, "create", ROLE_OPTS), help: <RoleHelp rows={roleRows} lead={actorRole === "system_admin" ? "관리자, 시스템 관리자 계정도 추가할 수 있습니다." : "관리자, 시스템 관리자 계정은 시스템 관리자만 추가할 수 있습니다."} /> }, { name: "department_id", label: "부서", type: "entity", value: "", options: dept.options, help: deptHelp }, { name: "title_id", label: "직책", type: "entity", value: "", options: title.options, help: titleHelp }, { name: "password", label: "초기 비밀번호(선택)", type: "password", help: pwHelp }, { name: "active", label: "활성", type: "checkbox", value: true, checkLabel: "활성", help: "비활성화하면 비활성 상태로 추가됩니다(로그인 불가). 나중에 상세에서 활성화할 수 있습니다." }, { name: "must_change_password", label: "다음 로그인 시 비밀번호 변경", type: "checkbox", value: true, checkLabel: "다음 로그인 때 비밀번호를 바꾸게 함", help: "선택하면 이 사람은 다음 로그인 직후 비밀번호를 바꿀 때까지 다른 화면으로 갈 수 없습니다." }, ];
  const editFields = [
    // required: 빈 이름으로 제출하면 서버는 display_name=null을 '변경 없음'으로 취급해 조용히
    // 아무것도 안 바꾼다(update_user는 not None일 때만 반영), 클라이언트에서 먼저 막아 저장됐다는
    // 오신호(성공 토스트)를 방지한다.
    { name: "display_name", label: "이름", type: "text", required: true }, {
      // 관리자 승인 흐름 안내는 system_admin이 아닌 행위자에게만 붙어 있었는데, 역할이 실제로
      // 바뀌면(어떤 역할로든) 이 사용자의 모든 세션이 즉시 강제 로그아웃된다(app/users/service.py
      // update_user, docs/USER_LIFECYCLE.md §3), 이 부작용은 actorRole과 무관하게 항상 적용되므로 별도로 안내한다.
      name: "role", label: "역할", type: "select", options: roleOptionsFor(actorRole, "edit", ROLE_OPTS), help: <RoleHelp rows={roleRows} lead={(actorRole === "system_admin" ? "" : "관리자로 변경하면 승인 요청이 접수됩니다. ") + "역할이 바뀌면 이 사용자의 모든 로그인 세션이 즉시 해제됩니다."} />, }, { name: "department_id", label: "부서", type: "entity", options: dept.options, help: deptHelp }, { name: "title_id", label: "직책", type: "entity", options: title.options, help: titleHelp }, { name: "must_change_password", label: "다음 로그인 시 비밀번호 변경", type: "checkbox", checkLabel: "다음 로그인 때 비밀번호를 바꾸게 함", help: "선택하면 이 사람은 다음 로그인 직후 비밀번호를 바꿀 때까지 다른 화면으로 갈 수 없습니다." },
      /* 관리 범위 (F2) — **부서 관리자를 만들 수 있는 유일한 입구**다.
       *
       * 모델(`users.admin_scope`)과 읽는 쪽(`app/core/scope.py`)은 0024 부터 있었는데
       * 넣는 길이 스키마·라우터·화면 어디에도 없었다. 그래서 모든 관리자가 영원히 `global`
       * 이었고, 범위 IDOR 테스트 넷은 값을 손으로 대입해서 초록이었다(T3 '가짜 안전감').
       *
       * 역할과 같은 무게로 다룬다: 범위를 넓히는 것은 권한을 주는 일이고, 바뀌면 그
       * 사용자의 세션이 즉시 끊긴다. 그래서 안내 문구도 역할 옆에 나란히 둔다. */
      // showIf: app/core/scope.py build_scope는 role===user일 때 admin_scope 컬럼을 아예
      // 읽지 않는다(부서 기반 자동 범위를 대신 쓴다) — role을 'user'로 두거나 바꾼 채 이
      // 필드를 저장하면 값은 DB에 남고 세션까지 강제 해제되지만 실제로는 아무 효과도 없는
      // 죽은 설정이 된다(상세 패널의 '관리 범위' 줄도 role!=='user'일 때만 그려 같은 경계를 쓴다).
      { name: "admin_scope", label: "관리 범위", type: "select", options: SCOPE_OPTS,
        showIf: (v) => v.role !== "user",
        help: "관리자가 관리 화면에서 볼 수 있는 범위입니다. 좁히면 그 범위 밖 사람과 자원이 목록에서 사라집니다. 범위가 바뀌면 이 사용자의 모든 로그인 세션이 즉시 해제됩니다. "
          + "전체는 전체 관리자, 조직은 조직관리자, 부서는 부서관리자라고 부릅니다. 전체 관리자는 이름이 비슷하지만 역할이 다른 시스템 관리자와 별개입니다." },
      // showIf: app/users/service.py _apply_admin_scope는 admin_scope='org'인데 scope_org_id가
      // 없으면 저장을 거부한다("조직 범위에는 대상 조직을 지정해야 합니다") — 그런데 이 폼에는
      // scope_org_id를 고를 필드가 아예 없었다. SCOPE_OPTS는 '소속 조직'을 고를 수 있는 선택지로
      // 보여주면서 실제로 조직을 지정할 방법을 안 줬으니, '조직관리자'를 만들려는 시도는 매번
      // 이 검증 오류로 막혔다(F2 코멘트의 "부서 관리자를 만들 수 있는 유일한 입구"는 있었지만
      // 조직관리자를 만들 입구는 없었던 셈).
      { name: "scope_org_id", label: "범위 대상 조직", type: "entity", options: org.options,
        showIf: (v) => v.role !== "user" && v.admin_scope === "org",
        help: (orgHelp ? orgHelp : "'조직'을 고른 경우에만 씁니다. 비워 두면 저장할 수 없습니다. 아무것도 못 보는 계정이 되기 때문입니다.") },
      // showIf: 도움말이 "'부서'를 고른 경우에만 씁니다"라고 말하면서도 admin_scope가 global/org일
      // 때도 계속 보였다 — AI 쿼터 화면(범위가 '사용자'일 때만 필요한 대상 ID 칸)과 같은 모양의
      // 문제라 같은 장치(showIf)로 맞춘다.
      { name: "scope_dept_id", label: "범위 대상 부서", type: "entity", options: dept.options,
        showIf: (v) => v.role !== "user" && v.admin_scope === "dept",
        help: "'부서'를 고른 경우에만 씁니다. 이 부서와 그 하위 부서까지 봅니다. 비워 두면 저장할 수 없습니다. 아무것도 못 보는 계정이 되기 때문입니다." },
    ];

  function announce(res, okMsg) {
    // 서버(app/users/router.py)는 상태를 top-level status 문자열로만 준다, approval_pending
    // 불리언 필드는 실제 응답 계약에 없는 죽은 분기라 제거한다.
    if (res && res.status === "approval_pending") toast("승인 요청이 접수되었습니다. 관리자 승인 후 반영됩니다.", "info");
    else toast(okMsg, "success");
  }
  // 서버가 임시 비밀번호를 돌려주면(생성/재설정) 일회성 모달로 노출한다.
  function maybeShowTempPw(res) {
    if (res && res.temp_password) { setTempPw({ password: res.temp_password, notice: res.temp_password_notice }); return true; }
    return false;
  }

  return (
    <div className="c-screen">
      {/* PA-RC-0022: 상시 안내였던 것을 PageHeader의 제목 옆 도움말 토글로 옮긴다 — 문구는
          한 글자도 안 바꿨다, 기본 접힘만 바뀐다. 한 문단에 4가지 서로 다른 사실(생성,
          비활성화 대 보관, 승인, 임시 비밀번호)을 몰아넣으면 스캔하기 어려웠다는 이전 결정은
          그대로 유지한다 — "& p" 간격 스타일을 help 내용 쪽에 그대로 옮긴다. */}
      <PageHeader area="사용자와 권한" title="사용자"
        description="조직의 모든 사용자 계정을 찾고, 권한과 상태를 관리합니다."
        actions={<>
          {/* 내보내기는 지금 화면에 걸린 필터 그대로 나간다(같은 filterParams). */}
          <CsvTools exportQuery={filterParams(false)} onImported={refresh} />
          <Button variant="primary" onClick={() => setCreating(true)}>사용자 추가</Button>
        </>}
        help={<Box sx={{ "& p": { m: 0 }, "& p + p": { mt: 0.75 } }}>
          <p>계정을 추가하고 역할, 부서, 직책을 관리합니다. 행을 누르면 상세에서 비밀번호 재설정, 세션 해제, 잠금 해제를 할 수 있습니다.</p>
          <p><strong>비활성화</strong>는 로그인만 막고(쉽게 되돌림), <strong>보관</strong>은 목록에서 감추되 기록은 남기고 복구할 수 있습니다.</p>
          <p>일반 사용자를 <strong>관리자</strong>로 올리면 승인 요청이 접수되어 승인 후 반영됩니다.</p>
          <p>임시 비밀번호는 계정을 추가하거나 비밀번호를 재설정할 때 화면에 한 번만 표시됩니다.</p>
        </Box>} />
      {deepLinkFailure ? <Callout tone="danger" compact>{deepLinkFailure}</Callout> : null}
      {/* 필터 바 — DataScreen(재설계 기준 화면)과 같은 자동 줄바꿈 그리드. 화면이 넓어지면 열이
          늘어 한 줄에 담기고, 좁아지면 접힌다(예전엔 flex 한 줄이라 1366px에서 이미 두 줄로 꺾였다).
          SEM-02(PA-F-031): h1 하나뿐이라 필터·목록이 스크린리더 제목 탐색에서 구획 없는 한
          덩어리였다. 시각은 그대로(.sr-only), 다른 목록 화면과 같은 패턴. */}
      <Typography component="h2" className="sr-only">필터</Typography>
      {/* 판이 아니다 — 지시 80. 검색 · 부서 · 역할 · 활성 · 잠김이 한 줄에 서고 「보관된 계정 보기」는 보기 방식이라 그 줄 오른쪽
          끝이다(조합 계약 C-1). 예전에는 검색만 한 줄을 쓰고 필터가 다음 줄로 내려갔고, 결과 수는 면 밖 한 줄이 말했다.
          걸린 조건(조직 콘솔에서 넘어온 부서 조건 포함)은 모두 조건 줄의 칩이다. */}
      <FilterBar
        search={(
          /* 공용 `SearchBox` 를 쓴다 — 예전에는 이 화면만 손으로 만든 검색창이었고, 디바운스도 없이 글자마다 질의가 나갔다. */
          <SearchBox
            value={q}
            onSearch={setQ}
            placeholder="이메일 또는 이름 검색"
            ariaLabel="사용자 검색"
          />
        )}
        /* 필터 바의 켬/끔은 스위치가 아니라 34 중립 단추다 — 켜져 있을 때만 눌린 면이다(핸드오프 RULES §3 · 계획 P-14). */
        end={<FilterToggle pressed={showArchived} onClick={() => setShowArchived(!showArchived)}>보관된 계정 보기</FilterToggle>}
        conditions={{
          chips: [
            q ? { key: "q", label: `검색: ${q}`, onDelete: () => setQ("") } : null,
            roleFilter ? { key: "role", label: `역할: ${(ROLE_OPTS.find((o) => o.value === roleFilter) || {}).label || roleFilter}`, onDelete: () => setRoleFilter("") } : null,
            activeFilter ? { key: "active", label: `활성: ${activeFilter === "true" ? "활성" : "비활성"}`, onDelete: () => setActiveFilter("") } : null,
            lockedFilter ? { key: "locked", label: `잠김: ${lockedFilter === "true" ? "지금 잠김" : "잠기지 않음"}`, onDelete: () => setLockedFilter("") } : null,
            deptFilter ? { key: "dept", label: `부서: ${deptFilter === NO_DEPARTMENT ? "미지정" : (deptFilterName || unmatchedLabel(deptFilter, dept.isLoading))}`, onDelete: () => setDeptFilter("") } : null,
            /* 칩 낱말은 켬/끔 단추 낱말(「보관된 계정 보기」)과 다르다 — 같은 이름의 누를 것이 둘이면 낭독기가 가르지 못한다. */
            showArchived ? { key: "archived", label: "보관된 계정만", onDelete: () => setShowArchived(false) } : null,
          ].filter(Boolean),
          total: query.first ? (total != null ? total : items.length) : null,
          /* 보관함을 보는 중엔 내용 필터만 지운다 — 보관함 밖으로 조용히 밀려나지 않게(아래 빈 상태와 같은 이유). */
          onClearAll: hasContentFilter ? clearContentFilters : null,
          clearLabel: "필터 초기화",
        }}
      >
        {/* 부서는 **범위**라 조건 칸의 맨 앞이다(`FilterBar.jsx::FILTER_GROUP_ORDER` — 범위 → 대상 → 분류 → 상태). 표에 「부서」
            열이 있는데 부서 칸이 없어서, 부서 조건은 조직 콘솔에서 넘어올 때만 걸렸고 그 사실을 칩과 안내 상자가 두 번 말했다.
            이제 이 칸이 조건을 걸고 풀며, 걸린 조건은 조건 줄의 칩 하나가 말한다. 주소 키는 칩 · 딥링크와 같은
            `department_id` 다. 부서는 조직이 자라면 후보도 자라는 Entity 라 검색형이고, 이름이 긴 축이라 wide 칸이다. */}
        <EntityCombobox
          label="부서"
          value={deptFilter}
          onChange={(v) => setDeptFilter(v || "")}
          options={deptFilterOptions}
          loading={dept.isLoading}
          allLabel="부서: 전체"
          size="wide"
        />
        <FilterSelect label="역할" value={roleFilter} onChange={setRoleFilter} options={ROLE_OPTS} allLabel="역할: 전체" />
        <FilterSelect
          label="활성" value={activeFilter} onChange={setActiveFilter} allLabel="활성: 전체"
          options={[{ value: "true", label: "활성" }, { value: "false", label: "비활성" }]}
        />
        <FilterSelect
          label="잠김" value={lockedFilter} onChange={setLockedFilter} allLabel="잠김: 전체"
          options={[{ value: "true", label: "지금 잠김" }, { value: "false", label: "잠기지 않음" }]}
        />
      </FilterBar>
      {/* keepPreviousData 라 검색 · 필터를 바꿔도 표는 그대로 있어(깜빡임 방지) 조작이 씹혔다고 오인하기 쉽다 —
          최초 로딩과 별개로 백그라운드 재조회 중임을 알린다. */}
      {query.first && query.isFetching && !query.isLoading ? (
        <Typography variant="caption" color="text.secondary" role="status" aria-live="polite" sx={{ display: "block", mb: 1 }}>불러오는 중…</Typography>
      ) : null}

      {/* 🔴 여기 부서 조건을 말하는 안내 상자(「부서 ‘…’ 소속만 보고 있습니다. 부서 필터 해제」)가 있었다. 같은 조건을 조건 줄의
          칩(「부서: …」)이 이미 말하고 그 칩의 ×가 조건을 푼다 — 한 사실을 두 곳에서 말했다(D-501). 조직 콘솔의 「부서 미지정
          N명」 링크로 온 `none` 도 칸과 칩이 「미지정」으로 말한다. */}
      {bulk.notice}

      <Typography component="h2" className="sr-only">목록</Typography>
      {query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
        {/* 보관함을 보는 중엔 목록이 채워져 있으면 상단에 지속 배너를 띄운다, 툴바의 작은 체크박스
            하나만으론 스크롤, 맥락 전환 후 보관 계정을 살아 있는 계정으로 오인하기 쉬웠다.

            문구는 「포함해」가 아니라 「만」이다. 서버의 `archived=true` 는 보관함을 여는
            문이라 사용 중인 계정을 **빼고** 답한다(`app/users/router.py`). 배포 환경에서
            「부서 미지정」 타일(11명)을 눌러 이 상자를 켜면 목록이 9건으로 줄어드는데,
            그때 배너가 「포함해 보고 있습니다」라고 하면 관리자는 사라진 2명을 사고로 읽는다.
            수를 여기 적지 않는 이유는 그것이 데이터라서다 — 세는 일은 목록이 한다. */}
        {showArchived && items.length > 0 ? <Box sx={{ mb: 2.5 }}><Callout tone="info">보관된 계정만 보고 있습니다. 사용 중인 계정을 다시 보려면 ‘보관된 계정 보기’를 끄세요.</Callout></Box> : null}
        {/* 목록 판 — 불러오는 중 · 빈 목록 · 행 · 발(받은 건수 · 「사용자 더 보기」 · 선택 묶음)이 한 판 안이다(조합 계약 C-3).
            판은 넘침을 자르지 않아 고정 열 이름이 페이지를 따라온다. 손으로 그린 페이저와 목록 위 일괄 작업 줄이
            여기 있었다 — 이제 목록 판 발 하나를 다른 화면과 함께 쓴다. */}
        <DataTable
          placement="surface"
          stickyHeader
          loading={query.isLoading}
          columns={columns} rows={items} rowKey={(r) => r.id} onRow={setSel}
          sort={{ key: sortKey, dir: sortOrder }}
          onSort={(key) => {
            const next = toggleSort({ key: sortKey, dir: sortOrder }, key, key === "created_at" ? "desc" : "asc");
            setSortKey(next.key);
            setSortOrder(next.dir);
          }}
          emptyState={showArchived ? (
            // 보관함을 보는 중엔 내용 필터만 지운다(clearContentFilters), clearFilters를 쓰면
            // showArchived까지 꺼져 조용히 보관함 밖으로 밀려난다(툴바의 동일 버튼과 같은 이유, 위 참고).
            <EmptyState layout="region" title="보관된 계정이 없습니다." help="보관한 계정이 여기에 표시됩니다."
              action={hasContentFilter ? <Button size="sm" onClick={clearContentFilters}>필터 초기화</Button> : <Button size="sm" onClick={() => setShowArchived(false)}>보관함 나가기</Button>} />
          ) : hasFilter ? (
            /* 조건 0건의 지우기는 30 보조 단추다(핸드오프 RULES §1 · 조합 계약 C-4). */
            <EmptyState layout="region" art="search" title="검색 조건에 맞는 사용자가 없습니다." help="검색어나 필터를 지우고 다시 확인하세요."
              action={<Button size="sm" onClick={clearFilters}>필터 초기화</Button>} />
          ) : (
            /* 만드는 단추는 30 이고 채움이 아니다 — 화면의 채움은 머리의 「사용자 추가」 하나다(RULES §1 · §3). */
            <EmptyState layout="region" title="등록된 사용자가 없습니다." help="‘사용자 추가’를 눌러 계정을 추가하세요."
              action={<Button size="sm" onClick={() => setCreating(true)}>사용자 추가</Button>} />
          )}
          list={{
            total, loaded: query.loaded,
            hasNext: query.hasNext, isFetchingNext: query.isFetchingNext, onMore: query.fetchNext,
            unit: "명", moreLabel: "사용자 더 보기",
          }}
          selection={bulk.selection}
        />
        </>
      )}

      {/* 작업 후 드로어를 닫지 않는다, 상세는 자체 useQuery로 서버 최신 상태를 다시 불러
          결과(활성/잠금/세션 수 변화)를 그 자리에서 보여준다. 창은 다른 사람으로 바뀔 때만 새로 선다(`detailKey`). */}
      <UserDetail key={detailKey.current} user={sel} notFound={routeIdNotFound}
        onClose={() => {
          // PA-RC-0033: 없는 id 오류는 sel이 애초에 null이라 위 "반대 방향" 효과(sel 변화 감지)가
          // 안 걸린다 — 여기서 직접 목록 주소로 되돌린다(같은 element라 목록 인스턴스는 그대로,
          // PA-RC-0024 계약 유지).
          if (routeIdNotFound) {
            setRouteIdNotFound(false);
            const qs = hashQuery(window.location.hash);
            navigate(qs ? "/users?" + qs : "/users", { replace: true });
          } else {
            setSel(null);
          }
        }}
        onEdit={(u) => setEditing(u)}
        onTempPw={(res) => maybeShowTempPw(res)} pwHelp={pwHelp} dept={dept} title={title}
        onChanged={() => { refresh(); }} />

      <FormModal open={creating} title="사용자 추가" fields={createFields} submitLabel="추가"
        screenKey="users" formKind="create"
        onClose={() => setCreating(false)}
        onSubmit={async (body) => {
          // 흔한 오타는 서버 왕복(영문 검증 오류) 전에 한국어로 잡는다. 서버(_EMAIL_SHAPE_RE)는 도메인에
          // 점을 요구하지 않는다 — 여기서 점을 강제하면 서버가 받아줄 사내 도메인 이메일을 프런트가
          // 먼저 튕겨낼 수 있어, 서버 정규식과 같은 느슨한 모양만 검사한다(도메인 정책은 서버가 최종 판단).
          if (body.email && !/^[^\s@]+@[^\s@]+$/.test(String(body.email))) throw new Error("올바른 이메일 형식이 아닙니다.");
          try {
            const res = await api("/api/admin/users", { method: "POST", body });
            setCreating(false); refresh();
            if (!maybeShowTempPw(res)) announce(res, "사용자를 추가했습니다.");
          } catch (e) {
            // 보관된 계정이 그 이메일을 쥐고 있는 409 — 원문 질문("복구하시겠습니까?")을 죽은 배너로
            // 흘리지 않고 실제 복구 행동으로 잇는다(서버가 details.archived_user_id를 함께 준다).
            if (e.status === 409 && e.body && e.body.error && e.body.error.code === "archived_email_conflict") {
              const archivedId = e.body.error.details && e.body.error.details.archived_user_id;
              if (archivedId && await confirm("그 이메일은 보관된 계정이 쓰고 있습니다. 그 계정을 복구할까요? 방금 입력한 역할, 부서 등 값은 적용되지 않고, 계정은 보관 전 정보 그대로 복구됩니다.", { title: "보관된 계정 복구", confirmLabel: "복구" })) {
                await api("/api/admin/users/" + archivedId + "/unarchive", { method: "POST", body: {} });
                setCreating(false); refresh();
                toast("보관된 계정을 예전 정보 그대로 복구했습니다. 방금 입력한 값은 반영되지 않았으니 필요하면 상세에서 수정하세요.", "success");
                return;
              }
              // 복구를 취소했거나 id가 없으면 폼을 유지하고 **폼 위 오류로** 말한다(다른 이메일로 바꿀 수 있게) —
              // 토스트는 사라지고, 사람은 그 이메일로 왜 못 만드는지 다시 찾아야 했다.
              throw new Error(e.body.error.message || "그 이메일은 보관된 계정이 쓰고 있습니다.");
            }
            throw e;   // 그 외 오류는 FormModal이 폼 상단에 표시하도록 다시 던진다
          }
        }} />

      <FormModal open={!!editing} title={editing ? (editing.display_name || editing.email) + " 수정" : ""}
        fields={editFields} initial={editing || {}} submitLabel="저장" onClose={() => setEditing(null)}
        screenKey="users" formKind="edit"
        onSubmit={async (body) => {
          // 전체 스냅샷이 아니라 실제로 바뀐 필드만 PATCH한다(diffFields) — 안 그러면 이 폼이 열려
          // 있는 사이 다른 관리자가 바꾼 필드(역할 승인 등)를 조용히 원래 값으로 되돌려 버릴 수 있다.
          const diff = diffFields(body, editing);
          // 실제로 바뀐 필드가 없으면 서버 왕복 없이 그냥 닫는다 — 서버는 빈 PATCH를 '변경 없음'으로
          // 조용히 받아주므로, 그대로 보내고 성공 토스트를 띄우면 뭔가 저장된 것처럼 오신호를 준다.
          if (Object.keys(diff).length === 0) { setEditing(null); toast("수정된 내용이 없습니다.", "info"); return; }
          const res = await api("/api/admin/users/" + editing.id, { method: "PATCH", body: diff });
          setEditing(null); refresh(); qc.invalidateQueries({ queryKey: ["user"] }); qc.invalidateQueries({ queryKey: ["user-sessions"] }); announce(res, "사용자 정보를 저장했습니다.");
        }} />

      <TempPasswordModal data={tempPw} onClose={() => setTempPw(null)} />
    </div>
  );
}

/* 상세의 라벨/값 줄과 격자는 `kit.jsx::DetailRow`·`DetailGrid` 다 — 예전에는 이 파일이
 * DataScreen 상세와 같은 sx 를 손으로 복사해 들고 있었다(네 벌 중 하나, D-457). */

const SESSION_COLUMNS = [
  { key: "client_ip", label: "IP", render: (s) => s.client_ip || "-" },
  { key: "user_agent", label: "기기/브라우저", render: (s) => <Tooltip title={s.user_agent || ""}><span>{uaSummary(s.user_agent)}</span></Tooltip> },
  { key: "last_seen_at", label: "최근 활동", type: "datetime", nowrap: true, render: (s) => <DateCell value={s.last_seen_at} /> },
];

/* 계정 수명주기 한 줄 (X14).
 *
 * ## 무엇이 틀렸었나
 *
 * 목록의 '활성' 열은 `r.active` 만 보고 초록 '사용 중' 배지를 그렸다. 그런데 **보관은
 * `active` 를 건드리지 않는다**(app/users/service.py `archive_user`: "복구했을 때 보관 전
 * 상태로 정확히 돌아와야 한다"). 그래서 보관된 계정 대부분이 목록에서 **초록 '사용 중'**
 * 으로 떴다 — 로그인이 막혀 있는데(app/core/deps.py) 화면은 정상 계정이라고 말한 것이다.
 * 옆에 회색 '보관됨' 칩이 하나 더 붙긴 했지만, 초록 배지와 나란히 있으면 사람은 초록을 읽는다.
 *
 * ## 어떻게 고치나
 *
 * 세 상태는 **서로 배타적**이고, 정확히 하나만 그린다. 지금 이 계정으로 로그인이 되는지가
 * 기준이다(그게 관리자가 이 열에서 궁금해하는 유일한 것이다):
 *
 *   보관됨   로그인 불가. 목록·검색에서도 빠진다. '복구' 로 되돌린다        (warn)
 *   비활성   로그인 불가. 목록에는 그대로 남는다. '활성화' 로 되돌린다      (neutral)
 *   사용 중  로그인 가능                                                    (ok)
 *
 * 보관과 비활성의 색을 다르게 준다 — 둘 다 회색이면 "로그인이 안 된다" 는 같은 결론까지만
 * 전해지고, **되돌리는 방법이 다르다는 것**은 전해지지 않는다. 보관 쪽이 더 무거운 상태라
 * (목록에서 사라지고 이메일이 잠긴다) 주의 톤을 준다.
 *
 * 잠김은 이 축이 아니다 — 비밀번호를 여러 번 틀려서 걸린 **일시적** 상태이고 '잠금 해제' 로
 * 푼다. 그래서 위 셋과 나란히가 아니라 덧붙는 배지로 남는다.
 */
export function lifecycleBadge(row) {
  if (row.archived_at) return { label: "보관됨", kind: "warn" };
  return row.active ? { label: "사용 중", kind: "ok" } : { label: "비활성", kind: "neutral" };
}

// 부서·직책이 비활성화됐는데도 이름만 봐서는 정상처럼 보이는 문제(수정 폼은 이미 처리, 상세는
// 안 함) — dept/title 목록에서 지금 배정된 id를 찾아 active===false면 '(비활성)'을 덧붙인다.
// 목록을 아직 못 불러왔거나(로딩/오류) id를 못 찾으면 판단을 보류하고 이름만 보여준다(오탐 방지).
function inactiveSuffix(nameOpts, currentId) {
  if (!nameOpts || currentId == null || currentId === "") return "";
  const found = (nameOpts.items || []).find((i) => String(i.id) === String(currentId));
  return found && found.active === false ? " (비활성)" : "";
}

function UserDetail({ user, notFound, onClose, onEdit, onChanged, onTempPw, pwHelp, dept, title }) {
  const [busy, setBusy] = useState(false);
  /* 상세 작업의 실패와 복사가 안 된 사실 — 이 모달 안에 남는다. 다음 작업을 누르면 걷힌다. */
  const [actionNotice, setActionNotice] = useState(null);
  const [resetting, setResetting] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();
  const qc = useQueryClient();
  const auth = useAuth();
  const nav = useNavigate();
  const uid = user && user.id;
  // '복사' 버튼 상태·타이머 — 훅이므로 반드시 이른 return(`if (!user) return null;`) 위에 둔다.
  // 예전엔 이 세 훅이 그 return 아래(copyId 근처)에 있어, user가 null→비null로 바뀌는 순간
  // (상세를 처음 열 때) 훅 개수가 12→15로 늘어 React가 "Rendered more hooks than during the
  // previous render"를 던졌고, ErrorBoundary가 상세 팝업을 통째로 오류 화면으로 대체했다.
  const [copiedId, setCopiedId] = useState("");
  const copiedIdTimerRef = React.useRef(null);
  React.useEffect(() => () => { if (copiedIdTimerRef.current) clearTimeout(copiedIdTimerRef.current); }, []);
  const actorRole = auth.data && auth.data.role;
  const actorId = auth.data && auth.data.id;
  // 상세는 목록 행 스냅샷(stale)이 아니라 서버 최신 상태를 다시 불러온다(잠금/세션 수/활성 등이
  // 목록 조회 이후 바뀌었을 수 있다). 로딩 중에는 목록 행으로 폴백해 깜빡임을 막는다.
  const detailQ = useQuery({ queryKey: ["user", uid], queryFn: () => api("/api/admin/users/" + uid), enabled: !!uid, retry: false });
  // 세션 조회는 관리 권한이 없으면 서버가 403을 준다. 목록 행/상세의 역할로 미리 판단해, 관리할 수
  // 없는 대상에는 아예 요청하지 않는다(불필요한 403과 '세션 정보를 불러오지 못했습니다' 노이즈 방지).
  const prelimRole = (detailQ.data && detailQ.data.role) || (user && user.role);
  const canManagePrelim = !(prelimRole === "system_admin" && actorRole !== "system_admin");
  const sessionsQ = useQuery({ queryKey: ["user-sessions", uid], queryFn: () => api("/api/admin/users/" + uid + "/sessions"), enabled: !!uid && canManagePrelim, retry: false });
  if (!user) {
    // PA-RC-0033: :id가 없는 사용자를 가리키면 목록 위 모달 자리에 그대로 ErrorState를 그린다
    // (DataScreen.jsx와 같은 계약) — sel이 끝까지 null이라 아래 정상 상세 렌더 경로를 못 타므로
    // 여기서 별도 분기가 필요하다.
    if (notFound) {
      return (
        <Modal open onClose={onClose} title="" size="lg">
          <ErrorState layout="region" error={{ status: 404 }} />
        </Modal>
      );
    }
    return null;
  }

  const d = detailQ.data || user;
  // 상세 재조회가 실패하면(예: 다른 관리자가 그 사이 이 사용자를 보관/삭제) d는 목록 행의 낡은
  // 스냅샷으로 조용히 남는다 — 아래에서 이 실패를 드러내고, 신뢰할 수 없는 상태로 쓰기 작업이
  // 나가지 않도록 조작 버튼을 잠근다.
  const detailStale = detailQ.isError;
  // 권한 경계: system_admin 계정은 system_admin만 관리할 수 있다(서버 ensure_can_manage_target).
  const canManage = !(d.role === "system_admin" && actorRole !== "system_admin");
  const isSelf = !!actorId && actorId === uid;
  const sessions = (sessionsQ.data && sessionsQ.data.items) || [];
  const sessionCount = d.active_session_count != null ? d.active_session_count : (sessionsQ.data ? sessions.length : null);

  function refetchDetail() {
    qc.invalidateQueries({ queryKey: ["user", uid] });
    qc.invalidateQueries({ queryKey: ["user-sessions", uid] });
  }

  // 작업 후 드로어는 열어 둔 채 상세·세션·목록을 다시 불러 결과를 그 자리에서 보여준다.
  async function run(path, { confirm: confirmMsg, danger, okMsg, format } = {}) {
    if (confirmMsg && !(await confirm(confirmMsg, { danger }))) return;
    setBusy(true);
    setActionNotice(null);
    try {
      const res = await api(path, { method: "POST", body: {} });
      // format이 {msg, kind}를 돌려주면 그 톤으로(성공만이 아니라 info/warn도) 알린다.
      const out = format ? format(res) : (okMsg || "처리했습니다.");
      if (out && typeof out === "object") toast(out.msg, out.kind || "success");
      else toast(out, "success");
      onChanged(); refetchDetail();
    }
    catch (e) {
      // 다른 admin 화면(DataScreen.jsx handleApiError)과 같은 401 처리 — 세션이 끊긴 채 계속
      // 여기서만 일반 오류 토스트로 흘리면, 다시 로그인하라는 신호 없이 다음 조작도 계속 실패한다.
      if (e && e.status === 401) { expireSession(); return; }
      setActionNotice({ tone: "danger", text: e.message });
    }
    finally { setBusy(false); }
  }
  // 비밀번호 재설정 — 관리자가 새 비밀번호를 직접 정하거나(입력) 비우면 임시 비밀번호를 자동
  // 생성해 일회성 모달로 노출한다. 서버는 password를 주면 그 값으로, 없으면 임시값을 만든다.
  async function submitReset(body) {
    const res = await api("/api/admin/users/" + uid + "/reset-password", { method: "POST", body });
    setResetting(false);
    if (body && body.password) toast("비밀번호를 재설정했습니다.", "success");
    else onTempPw(res);
    onChanged(); refetchDetail();
  }

  const id = uid;
  // 콘솔 어디에도 사용자의 raw id를 보여주는 곳이 없어(감사 로그의 행위자·대상 ID 필터 등에 붙여
  // 넣을 값을 얻을 방법이 없었다) 상세에서 복사할 수 있게 한다. copiedId 상태·타이머 훅은 위쪽
  // (이른 return 앞)으로 옮겼다 — 여기 두면 Rules of Hooks 위반으로 상세 팝업이 크래시했다.
  function copyId() {
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(id).then(() => {
      setCopiedId("복사됨");
      if (copiedIdTimerRef.current) clearTimeout(copiedIdTimerRef.current);
      copiedIdTimerRef.current = setTimeout(() => setCopiedId(""), 1500);
      toast("ID를 복사했습니다.", "success");
    }, () => setActionNotice({ tone: "danger", text: "복사하지 못했습니다. 직접 선택해 복사하세요." }));
    else setActionNotice({ tone: "info", text: "복사를 지원하지 않는 환경입니다. 직접 선택해 복사하세요." });
  }
  // 되돌리기 어려운 작업(비활성화, 보관)은 별도 묶음으로 떼어 오조작을 줄인다, 이전엔 무해한
  // 유틸리티(재설정, 세션 해제 등) 사이에 섞여 있어 위험 작업을 잘못 누르기 쉬웠다.
  // 상세 재조회 실패로 서버 최신 상태를 신뢰할 수 없는 동안은(detailStale) 쓰기 작업을 잠근다 -
  // 안 그러면 관리자가 목록의 낡은 스냅샷을 보고 지금과 다른 상태(예: 이미 비활성화됨)에 대해
  // 조작할 수 있다.
  const actionsDisabled = busy || detailStale;
  const navItems = [
    { key: "audit-object", label: "감사 로그에서 보기", disabled: busy,
      onClick: () => nav("/audit?object_type=user&object_id=" + encodeURIComponent(uid)) },
    { key: "audit-actor", label: "이 사용자의 활동 보기", disabled: busy,
      onClick: () => nav("/audit?user_id=" + encodeURIComponent(uid)) },
  ];

  /* 여기 「Notion 연결 확인」 항목이 있었고, 상세에는 연결 상태 줄과 그 화면으로 가는
     링크가 있었다. 그 화면도 S20 이 함께 내렸다 — 담당자 축은 이제 옛 짝이 없으면 그
     사람의 user id 로 서고(D-285), 짝을 새로 만드는 경로는 제품에 없다. */
  const manageItems = canManage ? [
    isSelf ? null : { key: "revoke", label: "세션 해제", disabled: actionsDisabled,
      onClick: () => run("/api/admin/users/" + id + "/revoke-sessions", { confirm: "이 사용자의 모든 로그인 세션을 끊을까요?", danger: true, format: (res) => (res && res.revoked_count ? res.revoked_count + "개 세션을 해제했습니다." : "해제할 활성 세션이 없습니다.") }) },
    d.active ? null : { key: "enable", label: "활성화", disabled: actionsDisabled,
      onClick: () => run("/api/admin/users/" + id + "/enable", { confirm: "이 사용자를 다시 활성화할까요?", okMsg: "다시 활성화했습니다." }) },
    d.archived_at ? { key: "unarchive", label: "복구", disabled: actionsDisabled,
      onClick: () => run("/api/admin/users/" + id + "/unarchive", { confirm: "이 사용자를 복구할까요?", okMsg: "복구했습니다." }) } : null,
    ...navItems,
    // 퇴사 처리는 이 화면에서 하지 않는다 — 보유 티켓을 먼저 보여 주고 재배정까지 함께 해야
    // '비활성화만 하고 티켓은 퇴사자에게 남아 있는' 상태가 안 생긴다(그것이 현재 운영 공백이었다).
    // 본인 계정은 서버가 409로 거절하므로 애초에 안내하지 않는다.
    isSelf ? null : { key: "offboard", label: "오프보딩(퇴사 처리)", disabled: busy,
      onClick: () => nav("/offboarding") },
    (d.active && !isSelf) ? { key: "disable", label: "비활성화", tone: "danger", disabled: actionsDisabled,
      onClick: () => run("/api/admin/users/" + id + "/disable", { confirm: "이 사용자를 비활성화할까요? 로그인할 수 없게 됩니다.", danger: true, okMsg: "비활성화했습니다." }) } : null,
    (!d.archived_at && !isSelf) ? { key: "archive", label: "보관", tone: "danger", disabled: actionsDisabled,
      onClick: () => run("/api/admin/users/" + id + "/archive", { confirm: "이 사용자를 보관할까요? 목록에서 사라지지만 기록은 남고 복구할 수 있습니다.", danger: true, okMsg: "보관했습니다." }) } : null,
  ].filter(Boolean) : [];

  const footer = canManage ? (
    /* 모달 발은 `ActionFooter` 하나다 — 면 · 위 선 · 여백의 주인이 하나이고, 발의 단추는 34 다(핸드오프 RULES §3 · 계획 B-7). 발에 ghost 를 두지 않는다. */
    <ActionFooter
      placement="modal"
      extra={(
        <>
          {/* 계정 잠금 해제는 이 화면에서 가장 시급한 복구 조작이라 메뉴에 접지 않는다. */}
          {d.locked ? <Button disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/unlock", { confirm: "이 계정의 잠금을 해제할까요?", okMsg: "잠금을 해제했습니다." })}>잠금 해제</Button> : null}
          <Button disabled={actionsDisabled} onClick={() => setResetting(true)}>비밀번호 재설정</Button>
          <OverflowMenu ariaLabel="사용자 작업 더 보기" items={manageItems} />
          {/* 본인 계정을 보는 중엔 비활성화, 보관, 세션 해제가 조용히 사라진다(자기 보호), 이유를
              바로 옆에서 밝히지 않으면 버그로 보이기 쉽다. */}
          {isSelf ? <Typography variant="caption" color="text.secondary">본인 계정은 비활성화, 보관, 세션 해제를 할 수 없습니다.</Typography> : null}
        </>
      )}
    >
      {/* detailStale일 때 다른 모든 쓰기 버튼과 마찬가지로 잠근다, 수정은 role을 포함한 임의
          필드를 PATCH할 수 있어(권한 상승 가능), 낡은 스냅샷을 근거로 열리면 안 된다. */}
      <Button variant="primary" disabled={actionsDisabled} onClick={() => onEdit(d)}>수정</Button>
    </ActionFooter>
  ) : (
    <ActionFooter
      placement="modal"
      extra={<Typography variant="caption" color="text.secondary">이 계정을 관리할 권한이 없습니다. 시스템 관리자만 관리할 수 있습니다.</Typography>}
    >
      <OverflowMenu ariaLabel="사용자 작업 더 보기" items={navItems} />
    </ActionFooter>
  );

  return (
    <>
    <Modal open={!!user} onClose={onClose} title={d.display_name || d.email} footer={footer} size="lg">
      {actionNotice ? <Callout tone={actionNotice.tone} compact>{actionNotice.text}</Callout> : null}
      {/* detailStale이 모든 작업 버튼을 잠그지만(actionsDisabled), 그 이유를 아무 데도 보여주지
          않으면 관리자는 버튼이 왜 안 눌리는지 알 길이 없다, sessionsQ.isError와 같은 패턴으로
          여기서도 실패와 재시도 경로를 드러낸다. */}
      {detailStale ? (
        <Box sx={{ mb: 2 }}>
          <Callout tone="danger" action={<Button size="sm" onClick={refetchDetail}>다시 시도</Button>}>
            최신 상태를 불러오지 못해 지금은 작업할 수 없습니다.
          </Callout>
        </Box>
      ) : null}
      <DetailGrid>
        <DetailRow label="사진">
          {/* 본인이 올린 사진 · 고른 그림 그대로(D-556). 없으면 프로필 화면과 같은 규칙의 기본 그림. */}
          <UserAvatar person={d} size="lg" label={d.display_name || d.email} />
        </DetailRow>
        <DetailRow label="이메일">{d.email}</DetailRow>
        <DetailRow label="ID">
          {/* user-select:all — id는 하이픈이 섞인 UUID라 더블클릭만으로는 한 토막만 선택된다. */}
          <Box component="span" tabIndex={0} sx={{ userSelect: "all", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: FONT_SIZE.bodySm, overflowWrap: "anywhere" }}>{d.id}</Box>
          {" "}
          <LinkButton onClick={copyId}>{copiedId || "복사"}</LinkButton>
        </DetailRow>
        <DetailRow label="역할">{ROLE_KO[d.role] || d.role}{isSelf ? " (본인)" : ""}</DetailRow>
        {/* 목록과 **같은 판정**을 쓴다(X14) — 한쪽만 고치면 같은 계정이 목록에서는 '보관됨'
            인데 상세에서는 '사용 중'으로 보인다. 보관된 계정은 `active` 가 참인 채로 남아
            있으므로(복구 때 되돌리려고), 복구하면 어느 상태로 돌아오는지도 함께 말한다. */}
        <DetailRow label="상태">
          <Badge value={lifecycleBadge(d).label} kind={lifecycleBadge(d).kind} />
          {d.archived_at ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              로그인할 수 없고 목록에서도 빠집니다. 복구하면 {d.active ? "사용 중" : "비활성"} 상태로 돌아옵니다.
            </Typography>
          ) : !d.active ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              로그인할 수 없습니다. 목록에는 그대로 남아 있고 ‘활성화’로 되돌릴 수 있습니다.
            </Typography>
          ) : null}
        </DetailRow>
        <DetailRow label="부서">{d.department ? d.department + inactiveSuffix(dept, d.department_id) : "-"}</DetailRow>
        {/* 지금 이 사람이 **어디까지 보는지**. 관리자에게만 의미가 있으므로 일반 사용자에는
            안 그린다(전체 범위가 기본값이라 모든 계정에 '전체 포털'이 붙으면 소음이 된다). */}
        {d.role && d.role !== "user" ? (
          <DetailRow label="관리 범위">
            {/* role=admin + admin_scope 조합의 이름(조직관리자/부서관리자/전체 관리자)을
                범위 설명 앞에 배지로 붙인다 — scopeLabel() 자체는 F2 계약(예: "소속 부서
                (하위 포함): ClovirONE팀")을 그대로 유지한다(users-scope.test.js). */}
            {adminConcept(d) ? <Badge value={adminConcept(d).label} kind={adminConcept(d).kind} /> : null}
            {" " + scopeLabel(d, dept)}
          </DetailRow>
        ) : null}
        <DetailRow label="직책">{d.title ? d.title + inactiveSuffix(title, d.title_id) : "-"}</DetailRow>
        {/* 목록 컬럼과 같은 어휘('잠김')를 쓴다, 여기서만 원시 불리언을 Badge에 그대로 넘기면
            '잠금: 예/아니오'로 읽혀, 같은 화면 안에서 같은 상태를 다른 말로 부르게 된다. */}
        <DetailRow label="잠금"><Badge value={d.locked ? "잠김" : "정상"} kind={d.locked ? "danger" : "neutral"} /></DetailRow>
        <DetailRow label="다음 로그인 시 비밀번호 변경"><Badge value={!!d.must_change_password} /></DetailRow>
        <DetailRow label="최근 로그인">{fmtDateTime(d.last_login_at)}</DetailRow>
        <DetailRow label="추가일">{fmtDateTime(d.created_at)}</DetailRow>
        {d.archived_at ? <DetailRow label="보관 시각">{fmtDateTime(d.archived_at)}</DetailRow> : null}
        {/* 로딩 중(em-dash)과 권한 없음(em-dash)이 예전엔 같은 표시라 구분이 안 됐다, 각각 다른 문구로 밝힌다. */}
        <DetailRow label="활성 세션">{sessionCount != null ? sessionCount + "개" : !canManagePrelim ? "권한 없음" : "불러오는 중…"}</DetailRow>
      </DetailGrid>
      {/* 관리 권한이 없으면 세션 조회를 아예 안 하므로(위 sessionsQ) 실패/목록 블록도 감춘다 -
          '관리 권한 없음'과 '세션 로드 실패'가 동시에 뜨는 모순을 없앤다. */}
      <Box sx={{ mt: 3 }}>
        {!canManage ? null : sessionsQ.isLoading ? (
          <Typography variant="caption" color="text.secondary">세션 정보를 불러오는 중…</Typography>
        ) : sessionsQ.isError ? (
          <Typography variant="caption" color="text.secondary">세션 정보를 불러오지 못했습니다. <LinkButton onClick={() => sessionsQ.refetch()}>다시 시도</LinkButton></Typography>
        ) : sessions.length ? (
          <>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>로그인 세션 (IP, 기기, 최근 활동)</Typography>
            <DataTable columns={SESSION_COLUMNS} rows={sessions} rowKey={(s) => s.id} />
          </>
        ) : (sessionsQ.data ? <EmptyState layout="inline" title="활성 세션이 없습니다." /> : null)}
      </Box>
    </Modal>
    <FormModal open={resetting} title="비밀번호 재설정"
      fields={[{ name: "password", label: "새 비밀번호(선택)", type: "password", help: pwHelp || "비우면 임시 비밀번호가 자동 생성되어 화면에 한 번만 표시됩니다." }]}
      submitLabel="재설정" onClose={() => setResetting(false)} onSubmit={submitReset} />
    </>
  );
}
