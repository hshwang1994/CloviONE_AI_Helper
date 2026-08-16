import React, { useState } from "react";
import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputAdornment from "@mui/material/InputAdornment";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { api } from "../lib/api.js";
import { diffFields } from "../lib/diffFields.js";
import { fmtDateTime, shortUA } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { PageHeader, Card, Badge, Button, DataTable, FormModal, Modal, Skeleton, EmptyState, ErrorState, Callout, useConfirm, useToast } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { useRowSelection, selectionColumn } from "../ui/bulkSelect.jsx";
import { FilterBarGrid } from "../ui/FilterBar.jsx";
import { BulkBar, CsvTools } from "./UsersBulk.jsx";

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

const ROLE_KO ={ user: "일반 사용자", operator: "운영자", admin: "관리자", auditor: "감사자", system_admin: "시스템 관리자" };
const ROLE_OPTS = Object.keys(ROLE_KO).map((v) => ({ value: v, label: ROLE_KO[v] }));

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
  const copiedTimerRef = React.useRef(null);
  React.useEffect(() => () => { if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current); }, []);
  if (!data) return null;
  function copy() {
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(data.password).then(() => {
      setCopied("복사됨");
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = setTimeout(() => setCopied(""), 1500);
      toast("복사했습니다.", "success");
    }, () => toast("복사 실패", "error"));
    else toast("복사를 지원하지 않는 환경입니다. 직접 선택해 복사하세요.", "info");
  }
  const footer = (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Box className="k-footer-main">
        <Button onClick={copy}>{copied || "복사"}</Button>
        <Button variant="primary" onClick={onClose}>확인</Button>
      </Box>
    </Box>
  );
  return (
    <Modal open onClose={onClose} title="임시 비밀번호" size="sm" footer={footer}>
      <Typography sx={{ whiteSpace: "pre-line" }}>{data.notice || "이 임시 비밀번호는 지금 한 번만 표시됩니다. 사용자에게 안전하게 전달하세요."}</Typography>
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
          fontSize: "1rem", fontWeight: FONT_WEIGHT.bold, letterSpacing: "0.03em",
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
  const [q, setQ] = useState(() => searchParams.get("q") || "");
  const [roleFilter, setRoleFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  // ADM-06R: 화면·배지(잠김)·잠금 해제 버튼은 이미 다 있는데 "지금 잠긴 사람만 보기"가
  // 안 됐다 — 활성 필터와 같은 모양으로 추가한다.
  const [lockedFilter, setLockedFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  // 조직도·부서 관리에서 '소속 인원 보기'로 오면 `#/users?department_id=<id>` 다. 백엔드는
  // 이 필터를 이미 지원했지만 화면이 주소를 읽지 않아, 눌러도 필터 없는 전체 목록이 떴다.
  const [deptFilter, setDeptFilter] = useState(() => searchParams.get("department_id") || "");
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
    // NOTI-04R — 다른 화면(알림 벨/목록, 조직도, 감사 로그)이 `?id=`로 특정 사용자를 곧바로
    // 상세로 열 수 있게 한다. 이 화면은 registry 기반이 아니라 수제라 다른 화면들이 쓰는
    // DataScreen.jsx의 `onQuery: {open:"select", id}` 배선을 그대로 못 쓴다 — 같은 계약
    // (단건 GET, 목록에 없어도/다른 페이지여도 열림, 실패 시 이유를 알림)을 여기서 직접 만든다.
    // sel/toast는 이 컴포넌트 아래쪽에서 선언되지만 이 효과의 콜백은 렌더가 끝난 뒤(그
    // 선언들이 이미 실행된 뒤)에만 실행되므로 참조해도 안전하다.
    const id = searchParams.get("id");
    if (id) {
      api("/api/admin/users/" + id)
        .then((item) => { if (item) setSel(item); })
        .catch(() => toast("연결된 사용자를 열지 못했습니다(삭제되었거나 접근 권한이 없을 수 있습니다). 목록에서 다시 확인해 주세요.", "error"));
      // 한 번 연 뒤에는 주소에서 지운다 — 안 지우면 드로어를 닫고 새로고침할 때마다 같은
      // 사용자가 다시 열린다(DataScreen.jsx가 해시 쿼리를 지우는 것과 같은 이유).
      setSearchParams((prev) => { const next = new URLSearchParams(prev); next.delete("id"); return next; }, { replace: true });
    }
  }, [searchParams]);
  const [page, setPage] = useState(1);
  const dq = useDebounced(q, 250); // 검색어는 250ms 디바운스 후에만 쿼리로 들어간다
  React.useEffect(() => { setPage(1); }, [dq, roleFilter, activeFilter, lockedFilter, showArchived, deptFilter]);
  // 대량 작업 선택 집합. 페이지·필터가 바뀌어도 유지된다 — 여러 페이지에 걸쳐 고른 뒤
  // 한 번에 처리하는 것이 이 기능의 목적이기 때문이다(서버는 id 목록만 본다).
  const selection = useRowSelection();
  const [sel, setSel] = useState(null);
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
  const pwHelp = "비우면 임시 비밀번호가 자동 생성되어 화면에 한 번 표시됩니다. 직접 입력 시 " + pwMinLen + "자 이상, 문자 종류(대/소문자, 숫자, 기호) " + pwMinClasses + "종 이상을 조합하세요.";
  // 부서, 직책 드롭다운의 실패/미등록 상태를 폼 도움말로 노출한다(막다른 '없음'만 남는 문제).
  // 목적지 화면 이름만 언급하는 정적 텍스트였던 것을 실제로 누를 수 있는 링크로 바꾼다, 새 탭으로
  // 열어(target=_blank) 작성 중이던 사용자 추가/수정 폼(반쯤 채운 값)을 잃지 않고 부서/직책을 먼저
  // 만들고 돌아올 수 있게 한다. FormField(kit.jsx)는 help를 그대로 렌더 자식으로 넣어 문자열 외에
  // React 노드도 받을 수 있다.
  const deptHelp = dept.isError ? (<>부서 목록을 불러오지 못했습니다. <LinkButton onClick={() => dept.refetch()}>다시 시도</LinkButton></>)
    : dept.isLoading ? "부서 목록을 불러오는 중…"
    : dept.isEmpty ? (<>등록된 부서가 없습니다, <Link href="#/departments" target="_blank" rel="noreferrer noopener" underline="hover">‘부서 관리’에서 먼저 추가하세요</Link>(새 탭)</>)
    : dept.isAllInactive ? (<>등록된 부서가 모두 비활성 상태입니다, <Link href="#/departments" target="_blank" rel="noreferrer noopener" underline="hover">‘부서 관리’에서 활성화하세요</Link>(새 탭)</>) : undefined;
  const titleHelp = title.isError ? (<>직책 목록을 불러오지 못했습니다. <LinkButton onClick={() => title.refetch()}>다시 시도</LinkButton></>)
    : title.isLoading ? "직책 목록을 불러오는 중…"
    : title.isEmpty ? (<>등록된 직책이 없습니다, <Link href="#/job-titles" target="_blank" rel="noreferrer noopener" underline="hover">‘직책 관리’에서 먼저 추가하세요</Link>(새 탭)</>)
    : title.isAllInactive ? (<>등록된 직책이 모두 비활성 상태입니다, <Link href="#/job-titles" target="_blank" rel="noreferrer noopener" underline="hover">‘직책 관리’에서 활성화하세요</Link>(새 탭)</>) : undefined;
  const orgHelp = org.isError ? (<>조직 목록을 불러오지 못했습니다. <LinkButton onClick={() => org.refetch()}>다시 시도</LinkButton></>)
    : org.isLoading ? "조직 목록을 불러오는 중…"
    : org.isEmpty ? (<>등록된 조직이 없습니다, <Link href="#/organizations" target="_blank" rel="noreferrer noopener" underline="hover">‘조직 관리’에서 먼저 추가하세요</Link>(새 탭)</>)
    : undefined;
  // 목록·CSV 내보내기가 **같은 필터 문자열**을 쓴다. 두 벌로 만들면 화면에 필터를 걸고
  // 내보낸 파일에 전 직원이 담기는 식으로 갈라지고, 그건 파일을 열기 전까지 아무도 모른다.
  function filterParams(withPage) {
    const p = withPage ? ["page=" + page] : [];
    if (dq) p.push("q=" + encodeURIComponent(dq));
    if (roleFilter) p.push("role=" + encodeURIComponent(roleFilter));
    if (activeFilter) p.push("active=" + activeFilter);
    if (lockedFilter) p.push("locked=" + lockedFilter);
    if (deptFilter) p.push("department_id=" + encodeURIComponent(deptFilter));
    if (showArchived) p.push("archived=true");
    return p.join("&");
  }
  const query = useQuery({
    queryKey: ["users", dq, roleFilter, activeFilter, lockedFilter, deptFilter, showArchived, page],
    queryFn: () => api("/api/admin/users?" + filterParams(true)),
    // 이전 결과를 유지해 새 쿼리 로딩 중에도 표를 스켈레톤으로 갈아엎지 않는다(깜빡임/스크롤 유실 방지).
    placeholderData: keepPreviousData,
    retry: false,
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
  const total = query.data && query.data.total;
  const pageSize = (query.data && query.data.page_size) || 20;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / pageSize)) : null;

  /* 열 폭은 브라우저 auto 레이아웃에 맡긴다 — 8개 열에 고정 폭(rem)을 주면 요청 폭 합이 1366px
   * 사내 장비의 가용 폭을 넘겨, 이메일·이름·날짜가 단어 중간에서 꺾여 3줄로 접혔다(설정 표에서는
   * 폭을 지정하지 않은 '설명' 열이 아예 한 줄에 한 자씩 세로로 무너졌다). 넓은 화면에서는 내용에
   * 비례해 자연히 벌어지므로 4K에서도 손해가 없다. */
  const columns = [
    // 대량 작업의 선택 열. 체크박스 클릭은 행 클릭(상세 열기)으로 번지지 않는다(bulkSelect.jsx).
    selectionColumn(selection, (query.data && query.data.items || []).map((r) => r.id)),
    // SEM-01: 선택 체크박스가 첫 열이라(rowName:false로 스스로 제외됨) 표식 없이는 이 표의
    // "상세 보기" 버튼과 체크박스 라벨(selectLabel, bulkSelect.jsx) 둘 다 모든 행이
    // 동일했다 — 이미 화면에 보이는 이메일로 실제로 구별되는 이름을 만든다.
    { key: "email", label: "이메일", rowName: (r) => r.display_name || r.email },
    { key: "display_name", label: "이름" },
    {
      // 역할은 이 표에서 가장 민감한(권한 상승 가능성이 있는) 열인데, '활성'·'잠김'·'Notion'과
      // 달리 유일하게 색 없는 맨 텍스트였다 — 같은 Badge 관례로 등급을 색으로도 구분한다.
      // 등급을 색으로 구분한다: system_admin(purple)·admin(warn)·operator/auditor(info, 권한 있는 비-관리자)·
      // 일반 사용자(neutral). 예전엔 operator/auditor가 일반 사용자와 같은 무채색이라 '관리자 아래는 다 같다'로
      // 읽혀, 색 구분의 취지(민감한 역할 열을 등급으로 구분)가 절반만 전달됐다.
      // system_admin은 원래 danger(빨강)였다(VIS-39/DS-08) — 이 제품에서 빨강은 "실패·위험"을
      // 뜻하는 상태색이라(대시보드의 실패 작업 위험 등) 최고 권한 배지가 마치 오류처럼 읽혔다.
      // purple은 이미 검증된 톤(다크모드·대비 확인됨, EXTRA_TONE_VARS)이면서 상태 팔레트
      // (ok/danger/warn/info)와 안 겹쳐 "특별한 등급"을 상태와 안 헷갈리게 표현한다.
      key: "role", label: "역할",
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
      key: "active", label: "상태",
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
    { key: "department", label: "부서", render: (r) => r.department ? r.department + inactiveSuffix(dept, r.department_id) : "-" },
    { key: "title", label: "직책", render: (r) => r.title ? r.title + inactiveSuffix(title, r.title_id) : "-" },
    { key: "notion_mapping_status", label: "Notion 연결", render: (r) => <Badge value={r.notion_mapping_status} /> },
    { key: "last_login_at", label: "최근 로그인", render: (r) => fmtDateTime(r.last_login_at) },
  ];

  const items = (query.data && query.data.items) || [];
  const hasFilter = !!(q || roleFilter || activeFilter || lockedFilter || deptFilter || showArchived);
  // 실제 '내용' 필터(검색·역할·활성·잠김·부서)만 — '보관된 계정 보기' 토글은 뷰 전환일 뿐 지울 필터가 아니다.
  const hasContentFilter = !!(q || roleFilter || activeFilter || lockedFilter || deptFilter);
  function clearFilters() { setQ(""); setRoleFilter(""); setActiveFilter(""); setLockedFilter(""); setDeptFilter(""); setShowArchived(false); }
  // 내용 필터만 지운다(보관함 뷰는 유지) — 툴바의 '필터 지우기'가 clearFilters를 쓰면 보관함을
  // 보던 중에도 showArchived까지 조용히 꺼져 뷰가 바뀌었다(뷰 전환과 필터 지우기는 다른 조작이다).
  function clearContentFilters() { setQ(""); setRoleFilter(""); setActiveFilter(""); setLockedFilter(""); setDeptFilter(""); }
  // 부서 딥링크로 들어온 상태를 이름으로 알려 준다 — id만 주소에 있으면 왜 목록이 좁아졌는지
  // 화면 어디에도 설명이 없다(필터 select에는 부서 항목이 없다).
  const deptFilterName = deptFilter
    ? ((dept.items || []).find((d) => String(d.id) === String(deptFilter)) || {}).name
    : null;
  // 페이지에 항목이 없는데 이전 페이지엔 있으면(마지막 행을 보관·비활성 처리한 경우 등)
  // '사용자가 없습니다' 대신 범위 안 페이지로 되돌린다(pager가 사라져 돌아갈 길이 막히는 문제).
  React.useEffect(() => {
    if (!query.isLoading && !query.isError && items.length === 0 && page > 1) setPage((p) => Math.max(1, p - 1));
  }, [items.length, page, query.isLoading, query.isError]);

  const createFields = [
    { name: "email", label: "이메일", type: "email", required: true, help: "로그인 아이디로 쓰입니다." }, { name: "display_name", label: "이름", type: "text", required: true }, { name: "role", label: "역할", type: "select", value: "user", options: roleOptionsFor(actorRole, "create", ROLE_OPTS), help: actorRole === "system_admin" ? "관리자, 시스템 관리자 계정도 추가할 수 있습니다." : "관리자, 시스템 관리자 계정 추가는 시스템 관리자만 가능합니다." }, { name: "department_id", label: "부서", type: "select", value: "", options: dept.options, help: deptHelp }, { name: "title_id", label: "직책", type: "select", value: "", options: title.options, help: titleHelp }, { name: "password", label: "초기 비밀번호(선택)", type: "password", help: pwHelp }, { name: "active", label: "활성", type: "checkbox", value: true, checkLabel: "활성", help: "비활성화하면 비활성 상태로 추가됩니다(로그인 불가). 나중에 상세에서 활성화할 수 있습니다." }, { name: "must_change_password", label: "첫 로그인 시 비밀번호 변경", type: "checkbox", value: true, checkLabel: "변경 요구" }, ];
  const editFields = [
    // required: 빈 이름으로 제출하면 서버는 display_name=null을 '변경 없음'으로 취급해 조용히
    // 아무것도 안 바꾼다(update_user는 not None일 때만 반영), 클라이언트에서 먼저 막아 저장됐다는
    // 오신호(성공 토스트)를 방지한다.
    { name: "display_name", label: "이름", type: "text", required: true }, {
      // 관리자 승인 흐름 안내는 system_admin이 아닌 행위자에게만 붙어 있었는데, 역할이 실제로
      // 바뀌면(어떤 역할로든) 이 사용자의 모든 세션이 즉시 강제 로그아웃된다(app/users/service.py
      // update_user, docs/USER_LIFECYCLE.md §3), 이 부작용은 actorRole과 무관하게 항상 적용되므로 별도로 안내한다.
      name: "role", label: "역할", type: "select", options: roleOptionsFor(actorRole, "edit", ROLE_OPTS), help: (actorRole === "system_admin" ? "" : "관리자로 변경하면 승인 요청이 접수됩니다. ") + "역할이 바뀌면 이 사용자의 모든 로그인 세션이 즉시 해제됩니다.", }, { name: "department_id", label: "부서", type: "select", options: dept.options, help: deptHelp }, { name: "title_id", label: "직책", type: "select", options: title.options, help: titleHelp }, { name: "must_change_password", label: "첫 로그인 시 비밀번호 변경", type: "checkbox", checkLabel: "변경 요구" },
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
          + "전체는 전체 관리자, 조직은 조직관리자, 부서는 부서관리자라고 부릅니다. 이름은 다르지만 시스템 관리자(system_admin, 역할 자체가 다른 계정)와는 별개 개념입니다." },
      // showIf: app/users/service.py _apply_admin_scope는 admin_scope='org'인데 scope_org_id가
      // 없으면 저장을 거부한다("조직 범위에는 대상 조직을 지정해야 합니다") — 그런데 이 폼에는
      // scope_org_id를 고를 필드가 아예 없었다. SCOPE_OPTS는 '소속 조직'을 고를 수 있는 선택지로
      // 보여주면서 실제로 조직을 지정할 방법을 안 줬으니, '조직관리자'를 만들려는 시도는 매번
      // 이 검증 오류로 막혔다(F2 코멘트의 "부서 관리자를 만들 수 있는 유일한 입구"는 있었지만
      // 조직관리자를 만들 입구는 없었던 셈).
      { name: "scope_org_id", label: "범위 대상 조직", type: "select", options: org.options,
        showIf: (v) => v.role !== "user" && v.admin_scope === "org",
        help: (orgHelp ? orgHelp : "'조직'을 고른 경우에만 씁니다. 비워 두면 저장이 거부됩니다. 아무것도 못 보는 계정이 되기 때문입니다.") },
      // showIf: 도움말이 "'부서'를 고른 경우에만 씁니다"라고 말하면서도 admin_scope가 global/org일
      // 때도 계속 보였다 — AI 쿼터 화면(범위가 '사용자'일 때만 필요한 대상 ID 칸)과 같은 모양의
      // 문제라 같은 장치(showIf)로 맞춘다.
      { name: "scope_dept_id", label: "범위 대상 부서", type: "select", options: dept.options,
        showIf: (v) => v.role !== "user" && v.admin_scope === "dept",
        help: "'부서'를 고른 경우에만 씁니다. 이 부서와 그 하위 부서까지 봅니다. 비워 두면 저장이 거부됩니다. 아무것도 못 보는 계정이 되기 때문입니다." },
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
        actions={<>
          {/* 내보내기는 지금 화면에 걸린 필터 그대로 나간다(같은 filterParams). */}
          <CsvTools exportQuery={filterParams(false)} onImported={refresh} />
          <Button variant="primary" onClick={() => setCreating(true)}>+ 사용자 추가</Button>
        </>}
        help={<Box sx={{ "& p": { m: 0 }, "& p + p": { mt: 0.75 } }}>
          <p>계정을 만들고 역할, 부서, 직책을 관리합니다. 행을 누르면 상세에서 비밀번호 재설정, 세션 해제, 잠금 해제 등을 할 수 있습니다.</p>
          <p><strong>비활성화</strong>는 로그인만 막고(쉽게 되돌림), <strong>보관</strong>은 목록에서 감추되 기록은 남기고 복구할 수 있습니다.</p>
          <p>일반 사용자를 <strong>관리자</strong>로 올리면 승인 요청이 접수되어 승인 후 반영됩니다.</p>
          <p>임시 비밀번호는 생성, 재설정 시 화면에 한 번만 표시됩니다.</p>
        </Box>} />
      {/* 필터 바 — DataScreen(재설계 기준 화면)과 같은 자동 줄바꿈 그리드. 화면이 넓어지면 열이
          늘어 한 줄에 담기고, 좁아지면 접힌다(예전엔 flex 한 줄이라 1366px에서 이미 두 줄로 꺾였다).
          SEM-02(PA-F-031): h1 하나뿐이라 필터·목록이 스크린리더 제목 탐색에서 구획 없는 한
          덩어리였다. 시각은 그대로(.sr-only), 다른 목록 화면과 같은 패턴. */}
      <Typography component="h2" className="sr-only">필터</Typography>
      <Card sx={{ p: 2, mb: 2.5 }}>
        <FilterBarGrid>
          <TextField
            type="search" size="small" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="이메일 또는 이름 검색"
            inputProps={{ "aria-label": "사용자 검색" }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
            sx={{ gridColumn: { sm: "span 2" } }}
          />
          <TextField select size="small" label="역할" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <MenuItem value="">역할: 전체</MenuItem>
            {ROLE_OPTS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="활성" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={activeFilter} onChange={(e) => setActiveFilter(e.target.value)}>
            <MenuItem value="">활성: 전체</MenuItem>
            <MenuItem value="true">활성</MenuItem>
            <MenuItem value="false">비활성</MenuItem>
          </TextField>
          <TextField select size="small" label="잠김" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={lockedFilter} onChange={(e) => setLockedFilter(e.target.value)}>
            <MenuItem value="">잠김: 전체</MenuItem>
            <MenuItem value="true">지금 잠김</MenuItem>
            <MenuItem value="false">잠기지 않음</MenuItem>
          </TextField>
          <FormControlLabel
            sx={{ m: 0 }}
            control={<Checkbox size="small" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />}
            label={<Typography variant="body2">보관된 계정 보기</Typography>}
          />
          {hasContentFilter ? <Button size="sm" onClick={clearContentFilters}>필터 지우기</Button> : null}
          {/* keepPreviousData라 검색, 필터를 바꿔도 표는 그대로 있어(깜빡임 방지) 타자/필터 조작이 씹혔다고
              오인하기 쉽다, isLoading(최초 로딩)과 별개로, 백그라운드 재조회 중임을 작은 텍스트로 알린다. */}
          {query.isFetching && !query.isLoading ? (
            <Typography variant="caption" color="text.secondary" role="status" aria-live="polite">불러오는 중…</Typography>
          ) : null}
        </FilterBarGrid>
      </Card>

      {deptFilter ? (
        <Box sx={{ mb: 2.5 }}>
          <Callout tone="info">
            {"부서 ‘" + (deptFilterName || deptFilter) + "’ 소속만 보고 있습니다. "}
            <LinkButton onClick={() => setDeptFilter("")}>부서 필터 해제</LinkButton>
          </Callout>
        </Box>
      ) : null}
      <BulkBar selection={selection} onDone={refresh}
        deptOptions={dept.options} titleOptions={title.options} />

      <Typography component="h2" className="sr-only">목록</Typography>
      {query.isLoading ? (
        <Card><Skeleton lines={5} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        showArchived ? (
          // 보관함을 보는 중엔 내용 필터만 지운다(clearContentFilters), clearFilters를 쓰면
          // showArchived까지 꺼져 조용히 보관함 밖으로 밀려난다(툴바의 동일 버튼과 같은 이유, 위 참고).
          <EmptyState title="보관된 계정이 없습니다" help="보관 처리한 계정이 여기에 표시됩니다."
            action={hasContentFilter ? <Button onClick={clearContentFilters}>필터 지우기</Button> : <Button onClick={() => setShowArchived(false)}>보관함 나가기</Button>} />
        ) : hasFilter ? (
          <EmptyState art="search" title="조건에 해당하는 사용자가 없습니다" help="검색어나 필터를 지우고 다시 확인하세요."
            action={<Button onClick={clearFilters}>필터 지우기</Button>} />
        ) : (
          <EmptyState title="사용자가 없습니다" help="'사용자 추가'로 새 계정을 만드세요."
            action={<Button variant="primary" onClick={() => setCreating(true)}>+ 사용자 추가</Button>} />
        )
      ) : (
        <>
        {/* 보관함을 보는 중엔 목록이 채워져 있으면 상단에 지속 배너를 띄운다, 툴바의 작은 체크박스
            하나만으론 스크롤, 맥락 전환 후 보관 계정을 살아 있는 계정으로 오인하기 쉬웠다. */}
        {showArchived ? <Box sx={{ mb: 2.5 }}><Callout tone="info">보관된 계정을 포함해 보고 있습니다, ‘보관됨’ 배지가 붙은 계정은 일반 목록에서 감춰진 상태입니다.</Callout></Box> : null}
        <Card>
          <DataTable columns={columns} rows={items} rowKey={(r) => r.id} onRow={setSel} />
          {total != null ? (
            // DataScreen.jsx의 모든 목록 화면과 같은 landmark, 라이브 영역(다른 19개 관리 섹션과 동일) -
            // 이 화면만 bare div라 스크린리더 사용자에게 페이지 이동 랜드마크도, 페이지 변경 안내도 없었다.
            <Box component="nav" aria-label="페이지 이동"
              sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, pt: 2, mt: 1, borderTop: 1, borderColor: "divider" }}>
              {totalPages > 1 ? <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>이전</Button> : null}
              <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ minWidth: "8rem", textAlign: "center" }}>
                {totalPages > 1 ? `${page} / ${totalPages}, ` : ""}총 {total}명
              </Typography>
              {totalPages > 1 ? <Button size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>다음</Button> : null}
            </Box>
          ) : null}
        </Card>
        </>
      )}

      {/* 작업 후 드로어를 닫지 않는다, 상세는 자체 useQuery로 서버 최신 상태를 다시 불러
          결과(활성/잠금/세션 수 변화)를 그 자리에서 보여준다. */}
      <UserDetail user={sel} onClose={() => setSel(null)} onEdit={(u) => setEditing(u)}
        onTempPw={(res) => maybeShowTempPw(res)} pwHelp={pwHelp} dept={dept} title={title}
        onChanged={() => { refresh(); }} />

      <FormModal open={creating} title="사용자 추가" fields={createFields} submitLabel="추가"
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
                toast("보관된 계정을 복구했습니다(예전 정보 그대로, 방금 입력한 값은 반영되지 않았습니다. 필요하면 상세에서 따로 수정하세요).", "success");
                return;
              }
              // 복구를 취소했거나 id가 없으면 폼을 유지하고 안내만(다른 이메일로 바꿀 수 있게).
              toast(e.body.error.message || "그 이메일은 보관된 계정이 쓰고 있습니다.", "info");
              return;
            }
            throw e;   // 그 외 오류는 FormModal이 폼 상단에 표시하도록 다시 던진다
          }
        }} />

      <FormModal open={!!editing} title={editing ? (editing.display_name || editing.email) + " 수정" : ""}
        fields={editFields} initial={editing || {}} submitLabel="저장" onClose={() => setEditing(null)}
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

/* 상세의 라벨/값 한 줄. 넓은 화면에서는 이 줄들이 2~3열로 접힌다(아래 DETAIL_GRID) — 4K에서
 * 한 열로 길게 늘어놓으면 오른쪽이 통째로 비고 눈은 위아래로만 움직인다(DataScreen 상세와 같은 규칙). */
function Row({ label, children }) {
  return (
    <Box sx={{
      display: "grid", gridTemplateColumns: { xs: "1fr", sm: "10rem minmax(0,1fr)" }, gap: 1,
      py: 1.25, borderBottom: 1, borderColor: "divider", minWidth: 0,
    }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>{children}</Box>
    </Box>
  );
}
const DETAIL_GRID = {
  display: "grid", columnGap: 4, rowGap: 0,
  gridTemplateColumns: { xs: "1fr", xxl: "repeat(2, minmax(0,1fr))", uhd: "repeat(3, minmax(0,1fr))" },
};

const SESSION_COLUMNS = [
  { key: "client_ip", label: "IP", render: (s) => s.client_ip || "-" },
  { key: "user_agent", label: "기기/브라우저", render: (s) => <Tooltip title={s.user_agent || ""}><span>{shortUA(s.user_agent)}</span></Tooltip> },
  { key: "last_seen_at", label: "최근 활동", render: (s) => fmtDateTime(s.last_seen_at) },
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

function UserDetail({ user, onClose, onEdit, onChanged, onTempPw, pwHelp, dept, title }) {
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false); // 저빈도 유틸리티를 '더보기'로 접어 좁은 화면에서 작업줄이 넘치지 않게 한다
  const [notionNotice, setNotionNotice] = useState(null); // "conflict" | "no-match" | null — Notion 연결 확인 실패를 토스트 소멸 이후에도 남긴다
  const confirm = useConfirm();
  const toast = useToast();
  const qc = useQueryClient();
  const auth = useAuth();
  const nav = useNavigate();
  const uid = user && user.id;
  // 다른 사용자의 드로어로 넘어가면 이전 사용자의 Notion 연결 확인 결과 안내와 '더보기' 펼침
  // 상태를 함께 초기화한다 — moreOpen만 남기면 A의 펼친 상태가 B의 드로어에도 그대로 이어진다.
  React.useEffect(() => { setNotionNotice(null); setMoreOpen(false); }, [uid]);
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
  if (!user) return null;

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
      if (e && e.status === 401) { toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error"); window.location.href = "/login"; return; }
      toast(e.message, "error");
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
    }, () => toast("복사 실패", "error"));
    else toast("복사를 지원하지 않는 환경입니다. 직접 선택해 복사하세요.", "info");
  }
  // 되돌리기 어려운 작업(비활성화, 보관)은 별도 묶음으로 떼어 오조작을 줄인다, 이전엔 무해한
  // 유틸리티(재설정, 세션 해제 등) 사이에 섞여 있어 위험 작업을 잘못 누르기 쉬웠다.
  // 상세 재조회 실패로 서버 최신 상태를 신뢰할 수 없는 동안은(detailStale) 쓰기 작업을 잠근다 -
  // 안 그러면 관리자가 목록의 낡은 스냅샷을 보고 지금과 다른 상태(예: 이미 비활성화됨)에 대해
  // 조작할 수 있다.
  const actionsDisabled = busy || detailStale;
  // 이 두 버튼(감사 로그, 활동 보기)은 읽기 전용 내비게이션이라 canManage(쓰기 권한 게이트)와
  // 무관하게 항상 노출한다, 백엔드는 이 경로(/audit)에 ensure_can_manage_target 같은 대상 역할
  // 제한을 두지 않는다. 예전엔 이 버튼들이 canManage 삼항식 안에 있어, system_admin이 아닌 관리자가
  // 다른 system_admin 계정을 보는 중(canManage=false)엔 감사 기록조차 볼 방법이 사라졌다.
  const readonlyNav = (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
      <Button disabled={busy} onClick={() => nav("/audit?object_type=user&object_id=" + encodeURIComponent(uid))}>감사 로그에서 보기</Button>
      <Button disabled={busy} onClick={() => nav("/audit?user_id=" + encodeURIComponent(uid))}>이 사용자의 활동 보기</Button>
    </Box>
  );
  const dangerActions = [];
  // 퇴사 처리는 이 화면에서 하지 않는다 — 보유 티켓을 먼저 보여 주고 재배정까지 함께 해야
  // '비활성화만 하고 티켓은 퇴사자에게 남아 있는' 상태가 안 생긴다(그것이 현재 운영 공백이었다).
  // 본인 계정은 서버가 409로 거절하므로 애초에 안내하지 않는다.
  if (!isSelf) dangerActions.push(
    <Button key="offboard" disabled={busy} onClick={() => nav("/offboarding")}>오프보딩(퇴사 처리)</Button>);
  if (d.active && !isSelf) dangerActions.push(
    <Button key="disable" variant="danger" disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/disable", { confirm: "이 사용자를 비활성화할까요? 로그인할 수 없게 됩니다.", danger: true, okMsg: "비활성화했습니다." })}>비활성화</Button>);
  if (!d.archived_at && !isSelf) dangerActions.push(
    <Button key="archive" variant="danger" disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/archive", { confirm: "이 사용자를 보관할까요? 목록에서 사라지지만 기록은 남고 복구할 수 있습니다.", danger: true, okMsg: "보관했습니다." })}>보관</Button>);
  // 버튼이 여러 개라 좁은 화면에서 넘치지 않도록 k-footer-extra(줄바꿈)에 무해한 부가 작업을 담고,
  // 위험 작업은 별도 group 묶음, 주 작업(수정)만 k-footer-main에 둔다.
  const footer = canManage ? (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Box className="k-footer-extra">
        <Button disabled={actionsDisabled} onClick={() => setResetting(true)}>비밀번호 재설정</Button>
        {/* 계정 잠금 해제는 이 화면에서 가장 시급도가 높은 복구 조작이다, '활성화'와 대칭으로, 저빈도 유틸리티 묶음(더보기) 안에 숨기지 않고 항상 보이게 한다. */}
        {d.locked ? <Button disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/unlock", { confirm: "이 계정의 잠금을 해제할까요?", okMsg: "잠금을 해제했습니다." })}>잠금 해제</Button> : null}
        {/* 저빈도 유틸리티(Notion 연결 확인, 세션 해제, 감사 로그)는 '더보기'로 접는다, 이전엔
            무해한 재설정부터 위험 작업까지 최대 7개 버튼이 한 줄에 다 나와(좁은 460px 폭 기준) 줄바꿈이
            뒤섞이고 위험 작업(비활성화/보관) 옆에 바짝 붙어 있었다. */}
        {/* aria-controls로 이 토글이 여는/접는 실제 영역(user-detail-more)을 스크린리더에 알린다 -
            이전엔 aria-expanded만 있어 무엇이 펼쳐지는지 프로그래매틱하게 연결되지 않았다. */}
        <Button disabled={busy} onClick={() => setMoreOpen((v) => !v)} aria-expanded={moreOpen} aria-controls="user-detail-more">{moreOpen ? "간단히" : "더보기"}</Button>
        {moreOpen ? (
          // display:contents, id를 달 실제 엘리먼트가 필요하지만, 감싸는 div가 레이아웃에 끼면 이
          // 버튼들이 부모 k-footer-extra 플렉스 흐름 밖으로 한 덩어리가 된다. display:contents는
          // 이 div 자체를 레이아웃에서 투명하게 만들어(자식이 부모의 직접 플렉스 아이템이 됨)
          // id/aria-controls 연결만 추가하고 기존 줄바꿈 배치는 그대로 유지한다.
          <Box id="user-detail-more" sx={{ display: "contents" }}>
            <Button disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/notion-mapping/verify", {
              // "verified" 외 실패도 전부 같은 문구로 뭉뚱그리지 않는다 — "conflict"(여러 계정과 동시에
              // 일치)는 관리자가 매핑을 새로 만드는 게 아니라 충돌을 해결해야 하는 별개 상황이다.
              // 실패 시 토스트(자동 소멸)만 남기지 않고 notionNotice에 담아, 드로어 안에 실제로 누를
              // 수 있는 링크로 남긴다(부서/직책 empty-state 링크와 같은 패턴).
              format: (res) => {
                const status = res && res.mapping && res.mapping.status;
                const detail = (res && res.mapping && res.mapping.error_message) || "";
                if (status === "verified") { setNotionNotice(null); return { msg: "Notion 연결을 확인했습니다.", kind: "success" }; }
                if (status === "conflict") { setNotionNotice("conflict"); return { msg: (detail || "일치하는 Notion 계정이 여러 개 발견되었습니다.") + " ‘Notion 사용자 연결’ 화면에서 충돌을 해결하세요.", kind: "info" }; }
                setNotionNotice("no-match");
                return { msg: detail || "연결된 Notion 계정을 찾지 못했습니다. ‘Notion 사용자 연결’ 화면에서 매핑을 만들 수 있습니다.", kind: "info" };
              },
            })}>Notion 연결 확인</Button>
            {!isSelf ? <Button disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/revoke-sessions", { confirm: "이 사용자의 모든 로그인 세션을 끊을까요?", danger: true, format: (res) => (res && res.revoked_count ? res.revoked_count + "개 세션을 해제했습니다." : "해제할 활성 세션이 없습니다.") })}>세션 해제</Button> : null}
          </Box>
        ) : null}
        {!d.active
          // kit.jsx ModalFooter 관례상 '기본 작업'은 하나만 primary다, '수정'이 그 자리를 이미
          // 차지하므로 '활성화'는 '복구'와 같은 비-primary 톤으로 맞춘다.
          ? <Button disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/enable", { confirm: "이 사용자를 다시 활성화할까요?", okMsg: "다시 활성화했습니다." })}>활성화</Button>
          : null}
        {d.archived_at
          ? <Button disabled={actionsDisabled} onClick={() => run("/api/admin/users/" + id + "/unarchive", { confirm: "이 사용자를 복구할까요?", okMsg: "복구했습니다." })}>복구</Button>
          : null}
      </Box>
      {dangerActions.length ? (
        <Box role="group" aria-label="주의가 필요한 작업"
          sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", ml: { sm: 1.5 } }}>{dangerActions}</Box>
      ) : null}
      {/* 본인 계정을 보는 중엔 비활성화, 보관, 세션 해제 버튼이 조용히 사라진다(자기 보호), 이유를
          바로 옆에서 밝히지 않으면 버그로 보이기 쉽다. */}
      {isSelf ? <Typography variant="caption" color="text.secondary">본인 계정은 비활성화, 보관, 세션 해제를 할 수 없습니다.</Typography> : null}
      {readonlyNav}
      <Box className="k-footer-main">
        {/* detailStale일 때 다른 모든 쓰기 버튼과 마찬가지로 잠근다, 수정은 role을 포함한 임의
            필드를 PATCH할 수 있어(권한 상승 가능), 낡은 스냅샷을 근거로 열리면 안 된다. */}
        <Button variant="primary" disabled={actionsDisabled} onClick={() => onEdit(d)}>수정</Button>
      </Box>
    </Box>
  ) : (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Typography variant="caption" color="text.secondary">이 계정을 관리할 권한이 없습니다(system_admin 전용).</Typography>
      {readonlyNav}
    </Box>
  );

  return (
    <>
    <Modal open={!!user} onClose={onClose} title={d.display_name || d.email} footer={footer} size="lg">
      {/* detailStale이 모든 작업 버튼을 잠그지만(actionsDisabled), 그 이유를 아무 데도 보여주지
          않으면 관리자는 버튼이 왜 안 눌리는지 알 길이 없다, sessionsQ.isError와 같은 패턴으로
          여기서도 실패와 재시도 경로를 드러낸다. */}
      {detailStale ? (
        <Box sx={{ mb: 2 }}>
          <Callout tone="warn">
            최신 상태를 불러오지 못해 작업을 수행할 수 없습니다. <LinkButton onClick={refetchDetail}>다시 시도</LinkButton>
          </Callout>
        </Box>
      ) : null}
      <Box sx={DETAIL_GRID}>
        <Row label="이메일">{d.email}</Row>
        <Row label="ID">
          {/* user-select:all — id는 하이픈이 섞인 UUID라 더블클릭만으로는 한 토막만 선택된다. */}
          <Box component="span" tabIndex={0} sx={{ userSelect: "all", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: FONT_SIZE.bodySm, overflowWrap: "anywhere" }}>{d.id}</Box>
          {" "}
          <LinkButton onClick={copyId}>{copiedId || "복사"}</LinkButton>
        </Row>
        <Row label="역할">{ROLE_KO[d.role] || d.role}{isSelf ? " (본인)" : ""}</Row>
        {/* 목록과 **같은 판정**을 쓴다(X14) — 한쪽만 고치면 같은 계정이 목록에서는 '보관됨'
            인데 상세에서는 '사용 중'으로 보인다. 보관된 계정은 `active` 가 참인 채로 남아
            있으므로(복구 때 되돌리려고), 복구하면 어느 상태로 돌아오는지도 함께 말한다. */}
        <Row label="상태">
          <Badge value={lifecycleBadge(d).label} kind={lifecycleBadge(d).kind} />
          {d.archived_at ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              로그인할 수 없고 목록에서도 빠집니다. 복구하면 {d.active ? "사용 중" : "비활성"} 상태로 돌아옵니다.
            </Typography>
          ) : !d.active ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              로그인할 수 없습니다. 목록에는 그대로 남아 있고 ‘활성화’로 되돌립니다.
            </Typography>
          ) : null}
        </Row>
        <Row label="부서">{d.department ? d.department + inactiveSuffix(dept, d.department_id) : "-"}</Row>
        {/* 지금 이 사람이 **어디까지 보는지**. 관리자에게만 의미가 있으므로 일반 사용자에는
            안 그린다(전체 범위가 기본값이라 모든 계정에 '전체 포털'이 붙으면 소음이 된다). */}
        {d.role && d.role !== "user" ? (
          <Row label="관리 범위">
            {/* role=admin + admin_scope 조합의 이름(조직관리자/부서관리자/전체 관리자)을
                범위 설명 앞에 배지로 붙인다 — scopeLabel() 자체는 F2 계약(예: "소속 부서
                (하위 포함): ClovirONE팀")을 그대로 유지한다(users-scope.test.js). */}
            {adminConcept(d) ? <Badge value={adminConcept(d).label} kind={adminConcept(d).kind} /> : null}
            {" " + scopeLabel(d, dept)}
          </Row>
        ) : null}
        <Row label="직책">{d.title ? d.title + inactiveSuffix(title, d.title_id) : "-"}</Row>
        <Row label="Notion 연결"><Badge value={d.notion_mapping_status} /></Row>
        {/* 목록 컬럼과 같은 어휘('잠김')를 쓴다, 여기서만 원시 불리언을 Badge에 그대로 넘기면
            '잠금: 예/아니오'로 읽혀, 같은 화면 안에서 같은 상태를 다른 말로 부르게 된다. */}
        <Row label="잠금"><Badge value={d.locked ? "잠김" : "정상"} kind={d.locked ? "danger" : "neutral"} /></Row>
        <Row label="비밀번호 변경 요구"><Badge value={!!d.must_change_password} /></Row>
        <Row label="최근 로그인">{fmtDateTime(d.last_login_at)}</Row>
        <Row label="추가일">{fmtDateTime(d.created_at)}</Row>
        {d.archived_at ? <Row label="보관 시각">{fmtDateTime(d.archived_at)}</Row> : null}
        {/* 로딩 중(em-dash)과 권한 없음(em-dash)이 예전엔 같은 표시라 구분이 안 됐다, 각각 다른 문구로 밝힌다. */}
        <Row label="활성 세션">{sessionCount != null ? sessionCount + "개" : !canManagePrelim ? "권한 없음" : "불러오는 중…"}</Row>
      </Box>
      {notionNotice ? (
        <Box sx={{ mt: 2 }}>
          <Callout tone="info">
            {notionNotice === "conflict" ? "일치하는 Notion 계정이 여러 개 발견되었습니다." : "연결된 Notion 계정을 찾지 못했습니다."}{" "}
            <Link href={"#/notion-mapping?user_id=" + encodeURIComponent(id)} target="_blank" rel="noreferrer noopener" underline="hover">‘Notion 사용자 연결’ 화면에서 확인하기</Link>(새 탭)
          </Callout>
        </Box>
      ) : null}
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
        ) : (sessionsQ.data ? <Typography variant="caption" color="text.secondary">활성 세션이 없습니다.</Typography> : null)}
      </Box>
    </Modal>
    <FormModal open={resetting} title="비밀번호 재설정"
      fields={[{ name: "password", label: "새 비밀번호(선택)", type: "password", help: pwHelp || "비우면 임시 비밀번호가 자동 생성되어 화면에 한 번만 표시됩니다." }]}
      submitLabel="재설정" onClose={() => setResetting(false)} onSubmit={submitReset} />
    </>
  );
}
