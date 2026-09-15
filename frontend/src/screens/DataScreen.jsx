import React, { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { diffFields } from "../lib/diffFields.js";
import { kstLocalToApi } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ActionFooter, PageHeader, Card, Button, DataTable, DetailGrid, DetailRow, FormDrawer, ListCard, Modal, OverflowMenu, Skeleton, EmptyState, ErrorState, Callout, useConfirm, useToast } from "../ui/kit.jsx";
import { StatusSummaryCard } from "../ui/StatusKpi.jsx";
import { SummaryView } from "./data-screen/SummaryView.jsx";
/* 검색 입력은 `ui/filters.jsx` 의 `SearchBox` 다 — **자기 상태를 자기가 든다**(PF4).
 *
 * 예전에는 그 부품이 이 파일 안에 있었다. 사용자 콘솔의 티켓·문서 목록도 같은 것이 필요해
 * 지면서 올렸다: 같은 뜻의 검색창이 세 벌이면 한쪽만 고쳐지는 날이 오고, 그때 증상은
 * "이 화면 검색만 느리다" 라서 원인이 안 보인다. */
import { DebouncedTextField, EMPTYABLE_SELECT, EntityCombobox, FilterSelect, SearchBox, kindSx, normalizeOptions, unmatchedLabel } from "../ui/filters.jsx";
import { DateField } from "../ui/DateField.jsx";
/* 탐색 줄 — 필터 바 조합 부품(ui/FilterBar.jsx). **판이 아니다**(지시 80).
   폭은 격자 트랙이 아니라 컨트롤의 종류가 정한다(C2 «폭 배분»). */
import { FILTER_GROUP_ORDER, FilterBar, filterGroupOf } from "../ui/FilterBar.jsx";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { CHUNK, useInfiniteList, useResetScrollOnKeyChange } from "../lib/useInfiniteList.js";
import { SavedViews } from "../ui/SavedViews.jsx";
/* 탭 그릇 안에서 머리 동작을 그릇의 머리로 보낸다(D-454). 그릇이 없으면 제자리에 그린다. */
import { HeaderActions } from "../ui/HeaderSlot.jsx";
/* `?` 도움말과 절차 안내의 정본 — 단독 화면과 탭 그릇이 같은 함수를 부른다(D-453 · D-456). */
import { buildScreenHelp, canOnboardFor } from "./data-screen/screenHelp.jsx";
import { SHELL_QUERY_KEYS, buildViewQuery, describeView, hashPath, hashQuery, keepQueryKeys, ownedQueryKeys, parseView, withHashQuery, withQuery } from "./datascreen-view.js";
import { loginUrl } from "../lib/sessionRedirect.js";
// 아래 네 갈래는 원래 이 파일 안에 있던 것을 data-screen/ 로 옮긴 것이다(800줄 규칙, §23).
// 이 파일이 그 뜻(설정 주도 목록 화면의 본체)을 그대로 갖고, 조각들은 여기서만 조립한다.
import { JsonBlock } from "./data-screen/JsonBlock.jsx";
import { CROSS_SCREEN_KEYS } from "./data-screen/crossScreenKeys.js";
import { handleApiError } from "./data-screen/apiError.js";
import { expireSession } from "../lib/sessionRedirect.js";
import { mergeDetailFields, detailTitle } from "./data-screen/detailFields.js";
import { SubListDrawer } from "./data-screen/SubListDrawer.jsx";
import { successMessageFor } from "./data-screen/successMessages.js";

// 열/필드 렌더 헬퍼(badgeCol 등)의 실제 구현은 data-screen/columnHelpers.jsx로 옮겼다.
// registry/shared.js가 `from "../DataScreen.jsx"`로 이 이름들을 그대로 가져다 쓰므로
// (수십 개 화면의 registry.js가 그 재수출에 기댄다) import 계약이 깨지지 않게 여기서 재수출한다.
export {
  badgeCol, boolCol, mapCol, dateCol, activeCol, enabledCol, linkCol, truncateCol, readCol,
  jsonField, objectField, listField, previewField,
} from "./data-screen/columnHelpers.jsx";


/* 설정 주도 목록 화면 — 여러 관리자 화면이 같은 읽기+상세+생성/수정/작업 패턴을 공유한다(§23).
 * 각 화면은 registry.js의 config만 다르다. 행 클릭 → 상세 모달(열 + config.detailFields 전체 필드).
 * 생성·수정은 공통 중앙 모달 폼. headerActions=폼 없는 즉시 실행/입력폼. 액션에 subList가 있으면
 * 하위 리소스(버전·실행 이력 등)를 별도 드로어로 조회한다. config.paginated면 서버 페이지네이션. */
/* `embedded` — 탭 그릇 안이라 **그릇이 제목을 그린다**(아래 렌더 분기).
 *
 * `inSplitView` — 분할 뷰의 **상세 판**이라 바깥 navigator 가 검색을 갖는다 (S18 · W8).
 *
 *   둘은 다른 사실이다. 탭 그릇 안에서는 그 탭 본문이 곧 화면이라 검색은 여기 있는 것이
 *   맞다. 분할 뷰에서는 왼쪽 트리가 같은 엔티티를 이미 찾고 있어서, 이 셸이 자기 검색
 *   상자를 그리면 한 화면에 **같은 것을 찾는 상자가 둘**이 된다 — 계획서가 `/organizations`
 *   의 결함으로 이름을 대어 적어 둔 상태이고, 분할 뷰 원형의 계약도 «상세 pane 은 자체
 *   Filter bar·SavedViews 금지» 다. 저장된 뷰도 같은 이유로 내린다: 조건 조합을 재사용할
 *   가치는 «그 조건으로 목록을 여는 화면» 에 있지, 트리에서 고른 마디를 보는 판에 없다.
 *
 *   W8 은 «공유 파일 무변경» 이 원칙이고 필요한 공유 변경은 W4~W7 의 결함으로 본다 —
 *   이것이 그 결함이다. 이 셸에는 「나는 navigator 가 딸린 판이다」를 말할 방법이 아예
 *   없었고, 그래서 어떤 분할 뷰도 자기 도구 줄을 두 번 그리게 돼 있었다. 목록·조건 축·
 *   폼·액션은 그대로다 — 내리는 것은 **바깥이 이미 가진 것** 둘뿐이다.
 */
export function DataScreen({ config, embedded = false, inSplitView = false }) {
  /* 첫 렌더에서 주소의 쿼리(#/audit?action=user.login)를 그대로 읽어 초기 상태로 삼는다.
   * 마운트 후에 setState 로 넣으면 기본 필터로 한 번 조회한 뒤 다시 조회해 목록이 두 번
   * 깜빡이고, 그 사이 사용자는 자기가 연 링크와 다른 화면을 본다. 게으른 초기화가 그
   * 왕복을 없앤다. (저장된 뷰를 부르는 일 = 이 주소로 가는 일 — datascreen-view.js) */
  const initialView = React.useMemo(
    () => parseView(hashQuery(window.location.hash), config),
    // config.key 가 바뀌면(=다른 화면) 다시 읽는다. 같은 화면 안에서는 한 번만.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [config.key]
  );
  const [q, setQ] = useState(initialView.q);           // 실제 쿼리에 쓰이는(디바운스된) 검색어
  /* 🔴 쪽 번호는 **상태가 아니다.** 목록은 쪽을 넘기지 않고 묶음을 이어 받는다.
     옛 주소·저장된 뷰는 여전히 `page=3` 을 들고 오므로 그만큼 미리 받아 대략 그 자리에
     떨어뜨린다(`useInfiniteList` 의 `resume`). 주소에서 `page` 는 첫 되쓰기에 사라진다. */
  const resumeChunks = initialView.page;
  // 검색 디바운스 — 서버 검색 화면(searchable, 특히 Notion 조회처럼 요청당 최대 30초 걸리는 화면)에서
  // 매 키 입력마다 새 요청을 쏘지 않는다(예전엔 한 글자씩 칠 때마다 retry:false 요청이 겹쳐 나가
  // 응답이 뒤죽박죽 도착했다).
  //
  // 검색 확정은 `SearchBox` 가 디바운스해서 부른다. 이 함수는 **참조가 고정**돼야 한다 —
  // 매 렌더마다 새로 만들면 `React.memo` 가 매번 깨져 이 수정이 무효가 된다.
  // 조건이 바뀌면 받아 둔 묶음은 질의 키가 바뀌면서 함께 버려진다 — 되돌릴 쪽 번호가 없다.
  const commitSearch = React.useCallback((next) => { setQ(next); }, []);
  const [sel, setSel] = useState(null);
  // PA-RC-0033: :id 라우트로 들어왔는데 그 레코드가 없으면(삭제됨/권한 밖) 지금까지
  // 토스트 하나만 뜨고(몇 초 뒤 사라짐) 화면은 조용히 목록으로 남았다 — 사용자는 잘못
  // 온 것인지 삭제된 것인지 알 방법이 없었다. sel과 별개로 들고 있다가 아래 Modal
  // 자리에 기존 ErrorState를 그린다(새 컴포넌트를 만들지 않는다).
  const [routeIdNotFound, setRouteIdNotFound] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [actionForm, setActionForm] = useState(null); // 입력이 필요한 액션(예: 수동 연결)
  const [createInitial, setCreateInitial] = useState(null); // 다른 화면에서 넘어온 생성 폼 프리필 값
  const [subView, setSubView] = useState(null);        // 하위 리소스 조회(버전·실행 이력)
  const [infoView, setInfoView] = useState(null);      // 결과 안내 모달(예: 복원 안내)
  /* 동작 결과 중 **남아야 하는 것** — 실패 · 경고 결과 · 끝나지 않은 작업. 토스트는 사라지므로 목록 동작은
     목록 위(`where: "list"`), 상세에서 누른 동작은 상세 안(`where: "detail"`)에 선다. 다음 동작을 누르면
     걷힌다. 문구는 토스트 때와 같다. */
  const [actionNotice, setActionNotice] = useState(null);
  // f.value(필터 정의의 기본값) — 예: 정책 화면의 상태 필터를 'published'로 기본 스코프한다
  // (지정 안 하면 draft/test/review/published/archived가 첫 방문부터 뒤섞여 보였다). 여전히
  // 사용자가 '전체'로 바꿀 수 있다(select의 빈 옵션이 그대로 남아 있음).
  const [filters, setFilters] = useState(() => {
    // 주소에 필터가 하나라도 실려 있으면(딥링크) 그 의도를 화면 기본값 **전체**보다 우선한다
    // (UB-13/RG-08) — 예전엔 키 단위로만 병합해서, "이 이름 버전 보기" 딥링크가 `name`만
    // 실어도 지정 안 한 `status` 기본값(`published`)이 살아남았다. 발행 버전이 없는(=이
    // 화면이 정리 대상으로 드러내려는) 이름을 누르면 "검색 결과 없음"이 뜬 이유가 그것이다.
    // 정말 아무 필터도 안 실린 첫 방문(주소창 직접 입력, 사이드바 메뉴 클릭)일 때만 화면
    // 기본값을 채운다 — `buildViewQuery`가 기본값을 주소에 안 싣는 것과 대칭이다.
    if (Object.keys(initialView.filters).length > 0) return { ...initialView.filters };
    const d = {};
    (config.filters || []).forEach((f) => { if (f.value != null && f.value !== "") d[f.key] = f.value; });
    return d;
  });          // 서버측 필터(감사·사용자 등)
  // 액션 실행 중(중복 클릭·느린 동기 호출 방지) — 어떤 특정 액션이 실행 중인지 key로 구분한다.
  // 예전엔 단순 boolean이라 하나를 누르면 이 화면의 모든 헤더/상세 드로어 버튼이 동시에 '처리
  // 중…'으로 바뀌어, 클릭하지 않은 다른 버튼도 마치 같이 실행 중인 것처럼 보였다(prompts/policies의
  // 초안→테스트→검토→발행처럼 액션이 여러 개인 화면일수록 혼란스러웠다). 이제 클릭한 버튼만
  // 라벨이 바뀌고, 나머지는 비활성화만 된다(중복 제출 방지는 그대로 유지).
  const [busyKey, setBusyKey] = useState(null);
  const busy = busyKey != null;
  const qc = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const { id: routeId } = useParams();
  const role = (auth && auth.data && auth.data.role) || null;
  const userId = (auth && auth.data && auth.data.id) || null;   // 본인 요청 자기승인 차단 등 행 게이트에 쓴다.
  /* 관리 **범위**는 역할과 다른 축이다 (xa-07).
   *
   * `role` 은 「무엇을 할 수 있는가」이고 관리 범위는 「누구에게 할 수 있는가」다. 서버는
   * 공지·전체 AI 상한·조직 정지 같은 **포털 전체가 주인인 자원**을 이미 범위로 거절하는데
   * (`app.core.scope.require_global_management`) 이 셸은 역할 축만 봤다 — 그래서 부서 범위
   * 관리자에게도 전역 자원의 '추가'·'수정'이 그려지고, 눌러 403 을 받고 나서야 못 한다는
   * 것을 알았다.
   *
   * 🔴 **`admin_scope` 열을 그대로 읽지 않는다.**
   *
   * 서버는 그 열을 그대로 쓰지 않는다. `app/core/scope.py::management_scope` 가 두 번
   * 깎아 낸다 — 운영자·감사자의 'global'(0024 마이그레이션이 그 열을 전부 'global' 로
   * 채워 놨다)은 조직 범위로 내려가고, 관리할 부서가 하나도 없는 'dept' 는 아무것도
   * 관리하지 못하는 범위가 된다. 열을 그대로 읽으면 그 둘이 전부 「전역」으로 읽혀서,
   * 단추를 보여 준 다음 403 을 받는 **이 게이트가 없애려던 바로 그 증상**이 남는다.
   *
   * 서버는 자기 판정을 이미 실어 보낸다 — `/api/me` 의 `user.management.kind`
   * (`app/profiles/router.py::_identity_context`, 판정에 쓰는 함수가 같다). ScopeBar·
   * UserMenu·OrgConsole 이 읽는 축이 그것이고, 여기서도 그 축을 읽는다.
   *
   * 값이 아예 없을 때만 전역으로 본다(OrgConsole 과 같은 판정). 두 방향의 대가가 다르기
   * 때문이다: 잘못된 「예」는 눌러서 403 을 받는 단추 하나이고, 잘못된 「아니오」는 할 수
   * 있는 사람에게서 단추를 통째로 뺏는다. 이 필드는 `/api/me` 가 언제나 싣고, 못 실었다면
   * 그것은 배선 사고이지 「이 사람이 부서 범위다」라는 사실이 아니다 — 어느 쪽이든 서버가
   * 마지막 문지기로 남는다.
   *
   * 범위는 두 갈래로 쓴다 — 선언이 `requiresGlobalScope: true` 한 줄로 말하면 이 셸이 직접
   * 가리고, 그보다 세밀한 조건(예: 행의 범위가 '전체'인 것만)은 registry 가 `when(row, ctx)`·
   * `when(ctx)` 에서 `ctx.managementScope` 를 읽어 스스로 판단한다. 이름을 `adminScope` 라
   * 하지 않는 이유가 위 그대로다 — 그 이름은 서버가 깎기 **전** 열의 이름이다. */
  const managementScope = (auth && auth.data && auth.data.management && auth.data.management.kind) || null;
  const isGlobalAdmin = !managementScope || managementScope === "global";
  const inScope = (decl) => !decl || !decl.requiresGlobalScope || isGlobalAdmin;
  // 액션 role 게이트 — a.roles가 지정된 액션은 현재 역할이 포함될 때만 노출(백엔드 RBAC와 일치시켜 403 사전 차단).
  const canDo = (a) => (!a.roles || (role != null && a.roles.includes(role))) && inScope(a);
  // 생성/수정 버튼도 액션과 같은 방식으로 role 게이트한다(create.roles / edit.roles) — 읽기 전용
  // 역할(operator/auditor)이 항상 403이 되는 '추가'·'수정' 버튼을 애초에 숨긴다.
  const canCreate = config.create
    ? ((!config.create.roles || (role != null && config.create.roles.includes(role))) && inScope(config.create))
    : false;
  const editRoles = (config.edit && config.edit.roles) || (config.create && config.create.roles) || null;
  const editScopeDecl = (config.edit && config.edit.requiresGlobalScope != null) ? config.edit : config.create;
  const canEditRole = (!editRoles || (role != null && editRoles.includes(role))) && inScope(editScopeDecl);
  // create/edit의 fields는 정적 배열이거나, role에 따라 달라지는 함수일 수 있다(예: 연동 생성 폼의
  // 인증 옵션을 admin에겐 '없음'만, system_admin에겐 전체로 좁힌다 — 어차피 백엔드가 403 낼 조합은
  // 애초에 고를 수 없게 한다).
  // row(선택)를 두 번째 인자로 넘긴다 — 편집 폼의 옵션이 '지금 편집 중인 행의 현재 값'에 따라
  // 달라져야 하는 경우를 지원한다(예: 템플릿 target_type — 신규로는 못 고르지만 기존 값이
  // 'runner'인 행은 그 값을 유지할 수 있는 옵션을 끼워 넣어야 한다). 기존처럼 (role)만 받는
  // 함수도 그대로 동작한다(두 번째 인자를 무시할 뿐).
  const resolveFields = (fields, row) => (typeof fields === "function" ? fields(role, row) : fields);
  const editFields = config.edit ? resolveFields(config.edit.fields, editing) : (config.create ? resolveFields(config.create.fields, null) : null);
  // f.optionsFrom(row) — 옵션이 '지금 편집/생성 중인 행'에 따라 달라지는 select 필드(예: notion-mapping의
  // '충돌 해결' 후보 목록). 예전엔 actionForm(행 액션의 입력 폼)에만 이 정규화가 있었고 create/edit
  // FormDrawer에는 없어서, 같은 f.optionsFrom을 쓰는 필드가 create/edit 폼에서는 그냥 빈 select로 떴다.
  // 두 번째 인자(rows)는 지금 화면에 로드된 목록이다. '상위 부서'처럼 후보가 **같은 목록의 다른
  // 행들**인 필드에 필요하다(자기 자신은 후보에서 빠져야 하므로 row 도 함께 받는다).
  // items 는 아래(282줄)에서 선언되지만 이 함수는 렌더 시점에 호출되므로 그때는 이미 값이 있다.
  // f.optionsFromRefList: "workflows" — 옵션이 **다른 화면의 리소스**(예: 워크플로 목록)인 select
  // 필드(DGEN-01/USE-04/SCHD-02: 워크플로/템플릿 ID를 손으로 옮겨 적던 것). config.refLists로
  // 선언한 목록을 아래(refListOptions)에서 미리 받아 두고 이름표를 붙인다. optionsFrom과 달리
  // '지금 화면의 데이터'가 아니라 '전혀 다른 화면의 데이터'라 별도 훅이 필요하다. f.extraOptions로
  // 고정 선택지(예: 스케줄의 '시스템(noop)')를 뒤에 덧붙일 수 있다.
  /* W5: 선언이 `kind: "entity"` 라고 말하면 **검색형 Combobox** 로 그린다.
   * 후보가 «다른 화면의 리소스»(사용자·부서·조직·워크플로·일정)면 그 목록은 데이터가
   * 쌓이는 만큼 자란다 — 닫힌 열거형과 같은 부품으로 그리면 후보가 200개가 되는 날
   * 사용자는 이름을 알면서도 목록을 눈으로 훑는다(R-5). 선언이 말하지 않으면 예전 그대로다. */
  const entityType = (f) => (f.kind === "entity" ? "entity" : "select");
  /* 🔴 `optionsFrom(row, items)` 갈래는 **없앴다.**
   *
   * 후보를 「지금 화면에 받아 둔 행」에서 뽑는 방식이었는데, 그 `items` 는 지금 걸린 조건의
   * 결과다 — 목록에 필터를 건 채 폼을 열면 후보가 그만큼 좁아진다. 조용하고 오류가 안 난다.
   * 유일한 사용처(상위 부서)는 `optionsFromRefList` 로 옮겼고, 그 축은 조건과 무관한 별도
   * 질의다. 되살리지 않는다 — `registry-filter-axes.test.js` 가 이것을 금지한다. */
  const withOptionsFrom = (fields, row) => (fields || []).map((f) => {
    if (f.optionsFromRefList) {
      const base = refListOptions[f.optionsFromRefList] || [];
      /* 폼 칸도 조건 축과 같은 규칙이다 (R7-05) — 후보를 못 받았으면 그 이유를 칸 아래에
         적는다. 빈 select 만 남기면 「고를 것이 없다」로 읽히고, 그건 사실이 아니다. */
      const help = refListFailedKeys.has(f.optionsFromRefList) ? REF_LIST_FAILED_TEXT : f.help;
      return { ...f, type: entityType(f), options: [...base, ...(f.extraOptions || [])], help };
    }
    return f;
  });

  // f.clientFilter:true — 이 필터는 백엔드가 쿼리 파라미터로 지원하지 않는 화면(예: 워크플로 목록은
  // page/검색 파라미터가 아예 없다)에서 이미 받아 온 전체 목록을 화면에서 직접 거른다. 서버로 보내면
  // 백엔드가 조용히 무시해 '골랐는데 아무 효과 없는' 필터가 되므로, 그런 화면은 이 표시를 쓴다
  // (부서/직책의 active 필터처럼 백엔드가 실제 지원하는 필터는 clientFilter 없이 그대로 서버로 간다).
  /* 이 화면의 **캐시 주소**. 기본은 화면 키 하나지만, 설정이 `cacheKey` 를 주면 그것을 쓴다.
   *
   * 왜 화면 키와 나누는가 (PF9): `config.key` 는 경로·저장된 뷰의 이름이고, 캐시 주소는
   * "같은 데이터를 보는 다른 부품들과 무엇을 공유하는가" 다. 알림이 그 예다 — 벨과 팝오버
   * 목록이 같은 알림을 보는데, 화면 키를 그대로 캐시 주소로 쓰면 접두어가 달라 한 번의
   * 무효화로 함께 갱신할 수가 없다. 화면 키를 바꾸면 캐시가 조용히 갈라지기도 한다. */
  const cacheRoot = React.useMemo(
    () => (Array.isArray(config.cacheKey) ? config.cacheKey : [config.key]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [config.key, config.cacheKey]
  );

  /* 정렬 상태는 **질의보다 위**에 있어야 한다 — 아래 목록 질의가 이 값을 질의 키와 URL 에
     함께 싣는다(`config.serverSort` 인 화면). 밑에 두면 TDZ 로 첫 렌더가 죽는다.
     세 번째 클릭이 `key` 를 비우면 서버가 정한 원래 순서로 돌아간다. */
  const [sort, setSort] = useState({ key: "", dir: "asc" });
  const toggleSort = (key) => setSort((cur) => {
    if (cur.key !== key) return { key, dir: "asc" };
    if (cur.dir === "asc") return { key, dir: "desc" };
    return { key: "", dir: "asc" };
  });

  const serverFilterDefs = (config.filters || []).filter((f) => !f.clientFilter);
  const clientFilterDefs = (config.filters || []).filter((f) => f.clientFilter);
  const listPageSize = config.pageSize || CHUNK;
  function buildUrl(pageParams) {
    const p = [];
    if (config.searchable && q) p.push("q=" + encodeURIComponent(q));
    serverFilterDefs.forEach((f) => {
      const v = filters[f.key];
      if (!v) return;
      // datetime-local 입력값("YYYY-MM-DDTHH:mm")은 시간대 정보가 없다 — 이 앱의 표시 규약(Asia/Seoul)에
      // 맞춰 KST(+09:00)로 해석해 백엔드 _parse_boundary가 기대하는 오프셋 포함 ISO-8601로 보낸다.
      // 변환은 lib/format.js 한 곳이 정본이다 — 폼(kit FormModal)이 같은 규칙을 써야 필터로 찾은
      // 시각과 폼에 적은 시각이 같은 뜻이 된다(F14: 폼 경로만 빠져 9시간 밀렸다).
      const sendVal = f.type === "datetime-local" ? kstLocalToApi(v) : v;
      p.push(f.key + "=" + encodeURIComponent(sendVal));
    });
    if (config.paginated && pageParams) {
      p.push("page=" + pageParams.page);
      p.push("page_size=" + pageParams.page_size);
    }
    /* 정렬도 조건과 같이 서버로 나간다. 세 번째 클릭이 `key` 를 비우면 두 파라미터가 함께
       빠지고, 그것이 곧 「서버가 정한 원래 순서로 되돌리기」다. */
    if (config.serverSort && sort.key) {
      p.push("sort=" + encodeURIComponent(sort.key));
      p.push("order=" + encodeURIComponent(sort.dir || "asc"));
    }
    return withQuery(config.endpoint, p);
  }
  // queryKey는 서버로 실제 전송되는 필터만 반영한다 — clientFilter 값이 바뀌어도 같은 데이터를 다시
  // 받아올 필요가 없다(그 값은 아래 filtered 계산에서만 쓰인다).
  const serverFiltersKey = JSON.stringify(Object.fromEntries(serverFilterDefs.map((f) => [f.key, filters[f.key]])));
  /* 🔴 **폴링과 무한 목록은 같이 못 간다.** react-query 는 무한 질의를 다시 받을 때 받아 둔
     묶음을 **전부** 순서대로 다시 부른다 — 작업 큐처럼 4초마다 도는 화면에서 다섯 묶음을
     받아 뒀으면 4초마다 요청이 다섯 번이다. 그래서 폴링은 **첫 묶음만 받은 동안**에만 켠다.
     더 받기 시작한 사람은 스스로 새로 받는다(조건을 건드리거나 목록을 다시 연다). */
  const list = useInfiniteList({
    /* 정렬이 질의 키에 들어간다 — 안 들어가면 정렬을 바꿔도 앞 조건의 캐시를 그대로 재사용한다. */
    key: [...cacheRoot, config.searchable ? q : "", serverFiltersKey,
      config.serverSort && sort.key ? `${sort.key}:${sort.dir}` : ""],
    size: listPageSize,
    enabled: true,
    resume: config.paginated ? resumeChunks : 1,
    fetch: (pageParams) => api(buildUrl(config.paginated ? pageParams : null)),
    itemsKey: config.itemsKey || "items",
    rowId: (r) => (r && r.id) || undefined,
    refetchInterval: config.pollWhile
      ? (qy) => {
        const pages = (qy.state.data && qy.state.data.pages) || [];
        if (pages.length !== 1) return false;
        const its = (pages[0] && pages[0][config.itemsKey || "items"]) || [];
        return its.some(config.pollWhile) ? 4000 : false;
      }
      : false,
  });
  /* 조건이 바뀌면 목록 머리로 되돌린다 — 한참 내려간 자리에서 걸러 놓고 빈 화면을 보면 안 된다.
     첫 마운트에는 안 돈다(그 순간은 `listReturn` 이 스크롤을 복원하는 자리다). */
  useResetScrollOnKeyChange(`${config.key}\u0000${q}\u0000${serverFiltersKey}`);
  /* 아래 코드가 `query.data` 로 읽던 것은 **첫 묶음 원본**이다 — `columnsFrom`(rbac 매트릭스)과
     `unreadCountKey`(알림)처럼 목록 밖의 값을 함께 싣는 응답이 있고, 그 값은 묶음마다 같다. */
  const query = { ...list, data: list.first };
  // 요약 통계(선택) — 목록과 별도 엔드포인트(예: 작업 큐 stats)를 받아 상단 판독 줄로 보여준다.
  // queryKey가 cacheRoot로 시작하므로 refresh()의 무효화에 함께 갱신된다.
  const summaryQuery = useQuery({
    queryKey: [...cacheRoot, "summary"],
    queryFn: () => api(config.summary.endpoint),
    enabled: !!config.summary,
    retry: false,
    // 진행 중 작업이 있는 화면(작업 큐 등)은 요약 카드도 목록과 함께 주기적으로 갱신한다
    // (예전엔 목록만 4초마다 갱신되고 카운트 카드는 마운트 시점 값에 얼어 있었다).
    refetchInterval: (config.summary && config.summary.poll) ? 4000 : false,
  });
  // 참조 목록(선택) — config.refLists: [{key, endpoint, valueKey="id", labelKey="name"}]로 선언한
  // **다른 화면의 리소스**(예: 워크플로/템플릿)를 하나의 쿼리로 함께 받아 위 withOptionsFrom이
  // 이름표 붙은 select로 바꾼다(DGEN-01/USE-04/SCHD-02). 선언한 화면만 켠다 — 대부분의 registry
  // 화면은 필요 없다. 각 목록은 그 화면의 own 페이지네이션 없이 전체를 한 번에 받는다(워크플로/
  // 템플릿 둘 다 list_workflows/list_templates가 이미 그렇게 준다 — 페이지네이션 없음).
  /* 🔴 목록 하나가 실패해도 나머지는 산다. 예전에는 `Promise.all` 이라 한 목록의 403 이
   * 이 화면의 **모든** 후보 목록을 비웠다 — 운영자·감사자가 여는 화면의 사람 후보가
   * 관리자 전용 경로를 부르던 동안 그 화면의 다른 후보까지 함께 사라졌다.
   *
   * 🔴 그런데 실패를 **빈 배열로만** 접어 두면 두 번째 거짓말이 남는다 (R7-05).
   * 이 질의는 언제나 이행되므로 `isError` 로 흐를 길이 없고, 후보가 0개인 축은 화면에서
   * 「고를 것이 없다」와 똑같이 보인다 — 「실패인데 '데이터가 없다'고 말하는 것보다 나쁜
   * 게 없다」(`lib/api.js` FAIL-01)가 그대로 재현된다. 실패한 키를 함께 들고 나와서, 그
   * 축만 왜 비었는지 말하게 한다. 나머지 축은 아무 영향이 없다. */
  const refListsQuery = useQuery({
    queryKey: [...cacheRoot, "refLists", (config.refLists || []).map((r) => r.key).join(",")],
    queryFn: async () => {
      const lists = config.refLists || [];
      const settled = await Promise.allSettled(
        lists.map(async (rl) => (await api(rl.endpoint))[rl.itemsKey || "items"] || [])
      );
      return {
        items: Object.fromEntries(lists.map((rl, i) => [rl.key, settled[i].status === "fulfilled" ? settled[i].value : []])),
        failed: lists.filter((rl, i) => settled[i].status === "rejected").map((rl) => rl.key),
      };
    },
    enabled: !!(config.refLists && config.refLists.length),
    retry: false,
  });
  /* 후보를 못 받은 축 — 위 질의가 남긴 키 집합. `has()` 하나로 묻는다. */
  const refListFailedKeys = React.useMemo(
    () => new Set((refListsQuery.data && refListsQuery.data.failed) || []),
    [refListsQuery.data],
  );
  /* 후보를 못 받은 축이 하는 말. **왜 비었는지**를 말하지 않으면 「없다」로 읽힌다. */
  const REF_LIST_FAILED_TEXT = "후보 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
  const refListOptions = React.useMemo(() => {
    const data = (refListsQuery.data && refListsQuery.data.items) || {};
    const out = {};
    (config.refLists || []).forEach((rl) => {
      out[rl.key] = (data[rl.key] || []).map((row) => ({
        value: row[rl.valueKey || "id"],
        label: String(row[rl.labelKey || "name"] ?? row[rl.valueKey || "id"] ?? ""),
        /* 보조 식별자 — 앞부분이 같은 후보를 가르는 유일한 수단이다(C2 «Dropdown 목록»).
           사람 목록이 특히 그렇다: 동명이인은 이메일이나 소속으로만 갈린다. 라벨 꼬리에
           붙이지 않는 이유는 그러면 이름이 길 때 식별자가 먼저 잘리기 때문이다. */
        secondary: [
          rl.secondaryKey ? row[rl.secondaryKey] : null,
          row.enabled === false ? "비활성" : null,
        ].filter(Boolean).join(", "),
      }));
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refListsQuery.data, config.refLists]);
  /* 정렬 상태. 같은 열을 다시 누르면 방향이 뒤집히고 **세 번째에 해제된다** — 서버가 정한
     원래 순서로 돌아갈 길이 없으면 정렬은 되돌릴 수 없는 조작이 된다. */

  function setFilter(key, val) { setFilters((s) => ({ ...s, [key]: val })); }
  /* 화면 밖에서도 같은 값을 보여 주는 곳이 있으면 함께 갱신한다 (X10).
   *
   * 알림 화면에서 '모두 읽음' 을 눌러도 **상단 벨은 최대 60초 동안 옛 숫자**를 들고 있었다.
   * 이 화면은 자기 키만 무효화하고, 벨은 접두어가 다른 키로 폴링했기 때문이다 — 코드
   * 주석이 이 결함을 예고해 놓고 그대로 남아 있었다(PF9 에서 뿌리를 합쳤다).
   *
   * 지도를 **한 곳에** 둔다. 무효화를 부르는 자리마다 손으로 적으면 새 화면에서 빠뜨리고,
   * 그때 증상은 "숫자가 안 맞는다" 라 원인을 찾기 어렵다. */
  const refresh = () => {
    qc.invalidateQueries({ queryKey: cacheRoot });
    for (const key of CROSS_SCREEN_KEYS[config.key] || []) {
      qc.invalidateQueries({ queryKey: key });
    }
  };
  const noticeWhere = (row) => (row && sel && (row === sel || (row.id != null && row.id === sel.id)) ? "detail" : "list");
  const reportFailure = (row) => (message) => setActionNotice({ tone: "danger", text: message, where: noticeWhere(row) });
  function announce(res, okMsg) {
    if (res && (res.status === "approval_pending" || res.approval_pending)) toast("승인 요청이 접수되었습니다. 관리자 승인 후 반영됩니다.", "info");
    else toast(okMsg, "success");
  }
  // 큐 작업(202)을 낸 뒤 종료 상태까지 폴링한다, 완료되면 목록을 갱신하고 결과를 알린다
  // (예: Notion 자동 동기화. 예전엔 즉시 한 번만 refresh해 아직 큐 상태인 옛 데이터를 보여줬다).
  async function pollJobUntilDone(jobId, opts) {
    const terminal = ["succeeded", "failed", "cancelled"];
    const interval = opts.interval || 2000;
    const maxTries = opts.maxTries || 20;
    for (let i = 0; i < maxTries; i++) {
      await new Promise((r) => setTimeout(r, interval));
      let job = null;
      // 세션 만료(401)는 폴링을 조용히 계속하면 안 된다 — 다른 API 경로처럼 로그인 화면으로
      // 보내고 폴링을 끝낸다(예전엔 401도 삼키고 maxTries까지 돌다 거짓 '진행 중' 토스트를 냈다).
      try { const j = await api("/api/admin/jobs/" + jobId); job = (j && j.job) || j; } catch (e) { if (e && e.status === 401) { expireSession(); return; } continue; }
      if (job && terminal.includes(job.status)) {
        refresh();
        if (job.status === "succeeded") toast(opts.doneMsg || "완료되었습니다.", "success");
        /* 백엔드 예외 원문(`job.last_error`)을 토스트에 붙이지 않는다 (지시 20 · 36). 토스트는
           사라지고, 사라지는 자리에 유일한 단서를 두면 안 된다 - 원문은 작업 큐의 그 작업
           상세에 그대로 남아 있고 거기가 기술 정보를 읽는 자리다. */
        else setActionNotice({ tone: "danger", text: opts.failMsg || "작업이 실패했습니다. 작업 큐에서 실패 원인을 확인하세요.", where: "list" });
        return;
      }
    }
    refresh();
    setActionNotice({ tone: "info", text: opts.timeoutMsg || "작업이 아직 진행 중입니다. 잠시 후 목록을 새로고침하세요.", where: "list" });
  }
  // 액션 실행 성공 결과를 공통 처리한다 — result/announce(+선택 상태 갱신)/pollJob 로직을 한 곳에
  // 모아 runAction·runHeaderAction·actionForm 제출(입력 폼이 먼저 열리는 액션)이 모두 같은 방식으로
  // 처리하게 한다. 예전엔 이 로직이 runAction/runHeaderAction에만 있고 actionForm 제출 경로(a.fields가
  // 있는 액션 — 예: 문서 재시도, Notion 자동 동기화 이후 입력이 필요한 케이스)에는 없어, 그 경로를
  // 타는 액션은 pollJob·keepSelection·localPatch가 조용히 무시되고 항상 드로어가 닫혔다.
  // row가 없으면(헤더 작업) 상세 드로어 선택 상태를 건드리지 않는다.
  function finishAction(a, res, row) {
    refresh();
    if (a.result) {
      // 액션 결과가 성공/실패를 담고 있는 경우(헬스체크·백업 검증 등) 실제 결과를 알린다.
      // rr.kind가 있으면 그 톤(info/warn 등)을 쓴다 — 실패는 아니지만 성공도 아닌 상태(예: 충돌)용.
      const rr = a.result(res);
      const rrKind = rr.kind || (rr.ok ? "success" : "error");
      /* 잘 됐다는 결과만 토스트다. 실패 · 주의 결과(헬스체크 실패 · 검증 충돌)는 사람이 읽고 다음 일을 해야
         하므로 그 자리에 남긴다. */
      if (rrKind === "success" || rrKind === "info") toast(rr.msg, rrKind);
      else setActionNotice({ tone: rrKind === "warn" ? "warn" : "danger", text: rr.msg, where: noticeWhere(row) });
      if (row) {
        if (rr.ok) setSel(null);              // 실패면 드로어 유지(원인 확인)
        else if (res && res.mapping) setSel(res.mapping);  // 검증→충돌 등: 최신 엔티티로 드로어 갱신(상태·후보 반영)
      }
    } else {
      announce(res, successMessageFor(a.label));
      if (row) {
        // keepSelection — 응답이 새 항목(item)을 돌려주면 드로어를 닫지 않고 그 항목으로 갱신한다
        // (예: 프롬프트 '새 버전' 후 새 초안을 바로 편집할 수 있게 — 목록으로 튕겨 나가지 않는다).
        // localPatch(row) — 응답이 갱신된 항목을 돌려주지 않는 액션(예: 알림 읽음 처리, {ok:true}뿐)도
        // 드로어를 곧장 닫지 않고 로컬에서 계산한 값으로 갱신한다(보다가 곧장 닫히는 문제 방지).
        if (a.keepSelection && res && res.item) setSel(res.item);
        else if (a.localPatch) setSel(a.localPatch(row));
        else setSel(null);
      }
    }
    // 큐 작업(job_id 반환)을 낸 액션은 종료까지 폴링해 완료 시점에 다시 갱신·안내한다.
    if (a.pollJob) { const jid = a.pollJob.getId ? a.pollJob.getId(res) : (res && res.job_id); if (jid) pollJobUntilDone(jid, a.pollJob); }
    // 내가 '누구인지'가 바뀌는 액션(대리 보기 시작)은 한 화면만 다시 받아서는 안 된다 —
    // 역할·메뉴·상단 배너가 전부 달라지므로 부분 갱신은 관리자 사이드바에 사용자 데이터가
    // 섞인 화면을 만든다. 토스트가 보일 만큼만 두고 통째로 다시 읽는다.
    if (a.reloadAfter) window.setTimeout(() => window.location.reload(), 900);
  }
  /* 내려받기는 **화면을 떠나지 않는다** (xe-07 · ops-03).
   *
   * 예전에는 `window.location.href = a.download(...)` 로 그 주소에 최상위 이동을 했다.
   * 성공 응답은 `Content-Disposition: attachment` 가 붙어 있어 문서가 유지되지만, 404·403·409
   * 는 브라우저가 그대로 그려서 **관리 콘솔이 통째로 사라지고** 날 JSON 한 줄이 화면을
   * 대체했다 — 돌아갈 단추도 없다(백업 파일이 디스크에서 사라진 흔한 운영 사건에서 실측).
   *
   * 그래서 먼저 응답을 받아 상태를 본다. 실패면 다른 액션과 같은 길(`handleApiError`)로
   * 서버 문구를 토스트에 내고 화면은 그대로 남는다. 성공이면 받은 내용을 Blob 으로 저장한다
   * — 파일 이름은 서버가 `Content-Disposition` 에 실어 준 것을 그대로 쓴다.
   *
   * `api()` 를 쓰지 않는 이유: 그 공용 클라이언트는 본문을 JSON 으로 읽어 CSV·덤프를
   * "해석하지 못했습니다"로 만든다. 오류 봉투 해석만 그쪽과 같은 규칙으로 맞춘다 —
   * 상관 id(`err.requestId`)까지 같은 자리에서 같은 규칙으로 싣는다(Z8).
   *
   * ## 그런데 **데이터베이스 덤프는 CSV 가 아니다** (R7-03)
   *
   * 받은 것을 Blob 으로 만들려면 본문이 **전부 도착할 때까지** 탭이 들고 있어야 한다.
   * 감사 CSV(내보내기 상한이 걸린 한 응답)에는 아무 대가가 아니지만, 백업 덤프는
   * 데이터베이스 전체다 — GB 단위 전송이 탭 메모리를 지나고, 그동안 단추는 「처리 중…」
   * 하나뿐이라 몇 %인지 알 길이 없고, 탭을 닫거나 다른 화면으로 가면 받던 것이 통째로
   * 버려진다. 브라우저의 내려받기 관리자는 그 셋을 전부 제자리에서 해 준다.
   *
   * 그래서 **행이 자기 크기를 말하면 그 값으로 갈래를 정한다**(`row.size_bytes` —
   * 백업 목록이 이미 「크기」 열에 그리는 그 값이다). 임계 위는 브라우저에게 넘기고,
   * 임계 아래(그리고 크기를 말하지 않는 모든 산출물 — 감사 CSV 같은 머리 동작)는
   * 지금처럼 받아서 확인하고 저장한다.
   *
   * 넘기는 쪽도 **최상위 이동이 아니다.** `<a download>` 클릭이라 실패해도 문서는 그대로
   * 남는다 — xe-07 이 없앤 「콘솔이 날 JSON 페이지로 바뀐다」는 어느 갈래에서도 안 돌아온다.
   * 대신 그 갈래는 오류를 토스트로 말하지 못한다(응답 코드를 볼 자리가 없다). 그것이
   * 이 거래의 값이다: 임계 위의 파일에서는 「받는 중인 것을 잃지 않는다」가 더 크다.
   *
   * 선언(`registry`)에 깃발을 새로 두지 않은 이유: 선언을 아무도 안 붙이면 그 장치는
   * 화면에서 아무 일도 하지 않는 채로 남는다(같은 회차에서 `requiresGlobalScope` 가 정확히
   * 그렇게 됐다). 크기는 이미 응답에 실려 오므로 아무도 무엇을 선언하지 않아도 맞게 돈다. */
  //: 이 위로는 브라우저 내려받기 관리자에게 넘긴다. 감사 CSV 내보내기(상한 20만 행 남짓)와
  //: 어떤 소형 산출물도 여기 닿지 않고, 실제 pg 덤프는 이 아래인 적이 드물다.
  const NATIVE_DOWNLOAD_MIN_BYTES = 32 * 1024 * 1024;
  function filenameFromDisposition(header, url) {
    const raw = String(header || "");
    /* RFC 5987 형식(`filename*=UTF-8''…`)이 있으면 그쪽이 정본이다. 한글 파일명이 여기 온다.
       작은따옴표를 \x27 이스케이프로 적는 이유는 뜻이 아니라 도구다 — 사용자 문구 검사기
       (`scripts/check_user_text.py`)는 정규식 리터럴을 추적하지 않는다고 스스로 적어 두었고,
       날 따옴표가 들어가면 그 뒤 파일 전체가 「문자열 안」으로 읽혀 주석이 사용자 문구로
       오인된다. 정규식의 뜻은 그대로다. */
    const star = /filename\*\s*=\s*[^\x27]*\x27\x27([^;]+)/i.exec(raw);
    if (star) { try { return decodeURIComponent(star[1].trim()); } catch (e) { /* 깨진 인코딩은 아래로 */ } }
    const plain = /filename\s*=\s*\x22?([^\x22;]+)\x22?/i.exec(raw);
    if (plain) return plain[1].trim();
    // 헤더가 없으면 주소의 마지막 조각 — 그것도 이름 같지 않으면 사람이 알아볼 기본 이름을 준다.
    const path = String(url || "").split("?")[0];
    const last = path.slice(path.lastIndexOf("/") + 1);
    return last && last.includes(".") ? last : "download";
  }
  /** 임시 `<a>` 하나를 눌러 저장을 시작한다. `href` 는 Blob 주소일 수도, 그 API 주소
   *  자체일 수도 있다 — 어느 쪽이든 **문서는 그 자리에 남는다**. */
  function clickDownloadLink(href, filename) {
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    // 문서에 붙였다 떼는 것이 Firefox 에서 클릭이 먹는 유일한 형태다.
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
  function saveBlob(blob, filename) {
    const objectUrl = URL.createObjectURL(blob);
    clickDownloadLink(objectUrl, filename);
    // 저장이 시작된 뒤에 풀어 준다 — 곧바로 revoke 하면 브라우저가 빈 파일을 저장한다.
    window.setTimeout(() => { try { URL.revokeObjectURL(objectUrl); } catch (e) { /* ignore */ } }, 60000);
  }
  /** 큰 산출물 — 브라우저 내려받기 관리자가 받는다(위 주석 「데이터베이스 덤프는 CSV 가
   *  아니다」). 이름은 서버의 `Content-Disposition` 이 이긴다: `download` 에 준 이름은
   *  그 헤더가 없을 때만 쓰인다(HTML 명세). 그래서 여기서는 주소에서 뽑은 이름을 준다. */
  function nativeDownload(url) {
    clickDownloadLink(url, filenameFromDisposition(null, url));
  }
  async function fetchDownload(url) {
    let res;
    try {
      res = await fetch(url, { credentials: "same-origin" });
    } catch (e) {
      /* 연결 자체가 안 됐다. 브라우저가 주는 문구는 영어 기술 문자열("Failed to fetch")이라
         그대로 토스트에 올리면 안 된다 — `lib/api.js` 가 같은 자리에서 쓰는 문장을 쓴다. */
      const err = new Error("서버에 연결할 수 없습니다. 네트워크 연결을 확인한 뒤 다시 시도해 주세요.");
      err.kind = "network";
      throw err;
    }
    if (!res.ok) {
      let body = null;
      try { body = await res.json(); } catch (e) { /* 봉투가 아닌 실패(프록시·게이트웨이)도 있다 */ }
      const err = new Error((body && body.error && body.error.message)
        || "파일을 내려받지 못했습니다. 잠시 후 다시 시도해 주세요.");
      err.status = res.status;
      /* 상관 id 도 **같은 규칙으로** 싣는다 (Z8 · R7-04). `lib/api.js` 를 지나는 오류는
         전부 이 값을 들고 다니는데 이 갈래만 안 들었다 — 그러면 「이 화면의 오류는 문의
         번호가 있고 내려받기 오류만 없다」가 되고, 그 차이는 사고 난 날에야 드러난다.
         봉투가 없는 실패(nginx 의 HTML 403·504)는 헤더 쪽에 값이 있다. */
      err.requestId = (body && body.error && body.error.request_id)
        || res.headers.get("X-Request-ID") || null;
      throw err;
    }
    saveBlob(await res.blob(), filenameFromDisposition(res.headers.get("Content-Disposition"), url));
  }
  async function runDownload(a, row, key) {
    /* **지금 화면의 서버 필터를 그대로 넘긴다**(buildUrl 이 만든 질의 문자열) — 화면에서
       좁혀 놓고 눌렀는데 전체가 내려오면 받은 파일은 화면에서 본 것과 다른 데이터이고,
       그 차이는 열어 보기 전까지 아무도 모른다. */
    const listUrl = buildUrl();
    const qs = listUrl.includes("?") ? listUrl.slice(listUrl.indexOf("?") + 1) : "";
    const url = a.download(qs, row);
    /* 큰 산출물은 브라우저에게 넘긴다 (R7-03 — 위 `NATIVE_DOWNLOAD_MIN_BYTES` 주석).
       크기를 말하지 않는 행과 머리 동작(`row` 자체가 없다)은 지금까지와 같은 갈래다. */
    const sizeBytes = Number(row && row.size_bytes);
    if (Number.isFinite(sizeBytes) && sizeBytes >= NATIVE_DOWNLOAD_MIN_BYTES) {
      nativeDownload(url);
      /* 이 갈래는 **언제 다 받았는지 모른다.** 그래도 다시 읽어야 하는 이유는 그대로다 —
         서버는 요청을 **받는 순간** `downloaded_at` 을 남기므로(`mark_downloaded` 는 본문을
         흘려보내기 전에 돈다), 요청이 서버에 닿을 만큼만 두고 한 번 읽으면 「서버에서
         삭제」 단추가 제자리에 선다. 「다 받았는지」를 재는 타이머가 아니다. */
      window.setTimeout(refresh, 2000);
      return;
    }
    setBusyKey(key);
    setActionNotice(null);
    try {
      await fetchDownload(url);
      /* 🔴 **내려받기는 행을 바꾼다** (2026-09-01). 백업 내려받기는 서버에서
         `downloaded_at` 을 남기고(`mark_downloaded`), 그 값이 다음 행동의 조건이다 —
         「서버에서 삭제」는 **내려받은 적이 있는 행에만** 뜬다(D-204: 다 받았다고 답할 수
         있는 것은 사람뿐이다). 그런데 예전 갈래는 목록을 다시 받지 않고 그대로 빠져나가서,
         받은 직후의 화면에는 그 단추가 여전히 없었다.

         이제는 그 GET 이 **끝난 것을 알고** 다시 읽는다 — 어림 타이머가 필요 없다. */
      refresh();
    } catch (e) {
      handleApiError(e, reportFailure(row));
    } finally { setBusyKey(null); }
  }
  /* 이동과 내려받기는 **행 액션과 머리 액션이 같은 계약**이다 (audit-01 · S21).
   *
   * 예전에는 두 함수가 각자 앞머리에 자기 가지를 뒀다 — `runAction` 에는 navigate·download 이
   * 있고 `runHeaderAction` 에는 navigate 만 있었다. 그래서 registry 가 머리에 선언한 download
   * (감사 로그 「CSV 내보내기」)는 맨 아래 쓰기 가지까지 떨어져 `a.path()` 를 불렀고, 내려받기
   * 액션에는 `path` 가 없으므로 그 자리에서 TypeError 가 났다. 잡히는 곳이 `handleApiError` 라
   * 화면에는 원시 예외 문구(«s.path is not a function»)가 토스트로 떴고 요청은 한 건도 나가지
   * 않았다 — 감사 로그 내보내기가 화면에서 통째로 죽어 있었다.
   *
   * 두 경로가 이 함수 하나를 같은 순서로 읽는다. 다음에 새 액션 종류가 생겨도 한쪽만 아는
   * 일이 없다. 머리 액션에는 행이 없으므로 `row` 는 undefined 이고, registry 의 머리 선언도
   * 인자를 받지 않는다(`navigate: () => "#/backup"`, `download: (qs) => …`). */
  function runNavigateOrDownload(a, row, key) {
    if (a.navigate) { setSel(null); window.location.hash = a.navigate(row); return true; }  // 다른 화면으로 이동(HashRouter)
    if (a.download) { runDownload(a, row, key); return true; }
    return false;
  }
  async function runAction(a, row, key) {
    setActionNotice(null);
    if (runNavigateOrDownload(a, row, key)) return;
    if (a.subList) { setSubView({ a, row }); return; }        // 하위 리소스 드로어
    // confirm은 고정 문자열 또는 (row)=>문자열 함수 둘 다 지원한다(행 데이터에 따라 경고 문구를 바꿔야
    // 하는 액션용 — 예: 수동 지정된 연결을 자동 검증으로 덮어쓸 때만 추가 경고).
    const confirmMsg = typeof a.confirm === "function" ? a.confirm(row) : a.confirm;
    // 확정 버튼에 **그 액션의 이름**을 쓴다 (E7). 기본값 "확인" 은 무엇이 일어나는지
    // 말하지 않는다 — 빨간색 말고는 단서가 없어서 유지보수 모드 켜기도, 삭제도, 롤백도
    // 전부 같은 한 단어였다. 액션은 자기 라벨을 이미 갖고 있으므로 그걸 그대로 쓴다.
    //
    // 확인은 **입력 폼(a.fields)보다 먼저** 묻는다. 예전에는 fields 분기가 여기보다 위에서
    // return 해 버려서, confirm과 fields를 함께 단 액션의 경고가 통째로 죽은 코드가 됐다
    // (설정 파일에 문구를 적어 두면 화면에 뜬다고 믿게 되는, 조용한 실패다). 폼은 '무엇을
    // 적을지'를 묻고 확인은 '무슨 일이 일어나는지'를 알린다 — 둘은 대체재가 아니다.
    if (confirmMsg && !(await confirm(confirmMsg, { danger: a.variant === "danger", confirmLabel: a.label }))) return;
    // 입력 폼 액션 — a.initial(row)이 있으면 행 데이터로 폼을 프리필한다(예: 실패한 문서 재시도).
    if (a.fields) { setActionForm({ a, row, initial: a.initial ? a.initial(row) : null }); return; }
    setBusyKey(key);
    try {
      // RG-01 — method가 GET이면 body를 아예 안 보낸다. lib/api.js는 GET일 때 body를
      // JSON.stringify하지 않고 원시 객체 그대로 fetch에 넘기는데, fetch 스펙 자체가
      // "GET/HEAD 요청은 body를 가질 수 없다"고 못 박아 TypeError를 던진다 — 그 예외가
      // "서버에 연결할 수 없습니다."로 둔갑해, 멀쩡한 엔드포인트가 죽은 것처럼 보였다
      // (같은 파일의 runHeaderAction은 애초에 body를 안 실어 이 문제를 안 겪는다).
      const method = a.method || "POST";
      const opts = method === "GET" ? { method } : { method, body: a.body || {} };
      const res = await api(a.path(row), opts);
      // 조회형 액션(미리보기/드라이런 등) — 목록 갱신·드로어 닫기 없이 결과를 안내 모달로 보여준다.
      if (a.info) { setInfoView({ title: a.label, body: a.info(res) }); return; }
      finishAction(a, res, row);
    } catch (e) {
      handleApiError(e, reportFailure(row));
      // 결과 담지 액션(a.result — 헬스체크·백업 검증 등)이 실패해도, 서버가 이미 결과를 기록했을 수
      // 있다(예: 러너 '테스트'의 RunnerUnavailableError는 record_runner_result 이후 발생) — 성공 경로만
      // refresh하면 그 실패 기록이 목록에 반영되지 않는다.
      if (a.result) refresh();
    }
    finally { setBusyKey(null); }
  }
  async function runHeaderAction(a, key) {
    setActionNotice(null);
    /* 🔴 머리의 이동·내려받기 버튼도 **행 액션과 같은 것을 한다** (S21 · audit-01).
     *
     * 예전에는 이 함수가 자기 앞머리에 `navigate` 가지 하나만 갖고 있었다. registry 가 머리에
     * 선언한 이동은 그것으로 살았지만 내려받기는 여전히 쓰기 분기로 떨어져 죽었다 — 갈래를
     * 두 곳에 손으로 적으면 늘 한쪽이 늦는다. 이제 위 `runNavigateOrDownload` 하나가 둘 다
     * 판정한다. 확인 문구도 폼도 필요 없는 동작이라 자리는 그대로 맨 앞이다. */
    if (runNavigateOrDownload(a, undefined, key)) return;
    if (a.info) {
      // 조회형 헤더 작업(예: 복원 안내) — 결과를 안내 모달로 보여준다. busy를 걸어 완료 전 중복 클릭을 막는다
      // (그 아래 쓰기 액션 분기와 동일한 패턴 — 예전엔 이 분기만 setBusy가 빠져 있었다).
      setBusyKey(key);
      try { const res = await api(a.path(), { method: a.method || "GET" }); setInfoView({ title: a.label, body: a.info(res) }); }
      catch (e) { handleApiError(e, reportFailure(null)); }
      finally { setBusyKey(null); }
      return;
    }
    // confirm은 고정 문자열 또는 (ctx)=>문자열 함수 둘 다 지원한다(runAction의 confirmMsg 패턴과
    // 동일) — 헤더 작업도 a.when(ctx)와 같은 headerActionCtx를 받아 동적 확인 문구를 만들 수 있다.
    const confirmMsg = typeof a.confirm === "function" ? a.confirm(headerActionCtx) : a.confirm;
    if (confirmMsg && !(await confirm(confirmMsg, { danger: a.variant === "danger", confirmLabel: a.label }))) return;
    // 행 액션(runAction)과 같은 순서 — 확인을 폼보다 먼저 묻는다. 한쪽만 고치면 같은 설정을
    // 헤더로 옮기는 순간 경고가 조용히 사라진다.
    if (a.fields) { setActionForm({ a, row: null }); return; }
    setBusyKey(key);
    try {
      const res = await api(a.path(), { method: a.method || "POST", body: a.body || {} });
      finishAction(a, res, null);
    } catch (e) { handleApiError(e, reportFailure(null)); }
    finally { setBusyKey(null); }
  }
  /* 지금까지 받아 둔 행 전부 — 한 쪽이 아니다. 아래 계산(상세 드로어 동기화·클라이언트
     필터·빈 상태 판정)이 전부 이 배열을 본다. */
  const items = list.rows;
  // config.columnsFrom(응답) — 열이 **서버 응답에서 결정되는** 화면용(권한 매트릭스: 역할이
  // 곧 열이다). 화면에 역할 목록을 한 벌 더 적으면 백엔드에서 규칙을 고쳐도 표는 옛 열을
  // 계속 보여 준다 — 그리고 그때 사람은 화면을 믿는다(app/core/authz.py가 유일한 출처).
  // 응답이 아직 없을 때는 빈 배열이 아니라 config.columns로 떨어져 로딩 중 크래시를 막는다.
  const columns = config.columnsFrom
    ? (query.data ? config.columnsFrom(query.data) : (config.columns || []))
    : config.columns;
  /* 「목록에서 실제로 본 적 있는 행」을 **id 로** 기억한다 (ai-03).
   *
   * 아래 효과는 «지금 조건의 결과에 없는 sel» 을 닫는다. 그 규칙 자체는 옳다 — 다른 관리자가
   * 지운 행을 계속 붙들고 있으면 안 된다. 문제는 그 판정이 **방금 내가 만든 행**과 **남이
   * 지운 행**을 구별하지 못했다는 것이다: 표식이 참/거짓 하나뿐이라, 발행본을 보다가 「새
   * 버전」을 눌러 `keepSelection` 이 새 초안을 드로어에 넣으면 앞 행에서 세워 둔 참이 그대로
   * 남아 «사라진 행» 으로 읽혔다. 기본 상태 필터가 '발행됨'인 화면에서 초안은 구조적으로
   * 목록에 없으므로, 초안→테스트→검토→발행 흐름이 첫 걸음에서 끊겼다(드로어가 닫히고 방금
   * 만든 초안은 목록 어디에도 없다).
   *
   * id 로 기억하면 두 사실이 갈린다: 표식이 지금 sel 의 id 와 같을 때만 「봤던 행이 사라졌다」
   * 이고, 아직 본 적 없는 새 행은 닫지 않는다. */
  const sawFreshIdRef = useRef(null);
  // 열린 상세 드로어를 백그라운드 refetch(pollWhile)와 동기화 — 캡처된 stale sel이 아니라 최신 행을 보여준다.
  // fetching 도중(예: 필터가 막 바뀌어 아직 새 페이지가 안 온 순간)엔 items가 일시적으로 비거나 옛
  // 페이지일 수 있어 판단을 보류한다 — 완료된 refetch에서 이미 한 번 확인됐던 sel.id가 더 이상 없으면
  // (다른 관리자가 지웠거나, 페이지네이션/필터에 걸려 빠졌거나) 그 낡은 항목을 계속 보여주는 대신 드로어를 닫는다.
  useEffect(() => {
    if (!sel || sel.id == null) { sawFreshIdRef.current = null; return; }
    if (query.isFetching) return;
    const fresh = items.find((r) => r.id === sel.id);
    if (fresh) {
      sawFreshIdRef.current = sel.id;
      if (fresh !== sel) setSel(fresh);
    } else if (sawFreshIdRef.current === sel.id) {
      sawFreshIdRef.current = null;
      setSel(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, query.isFetching]);
  /* 지금 보고 있는 뷰의 쿼리 문자열. **아래 두 효과가 같은 값을 본다** — 하나는 이 값을
     주소에 되쓰고(아래 '뷰를 주소에 되쓴다'), 하나는 주소가 이 값과 달라졌는지 본다(바로
     다음). 되쓰기 효과는 `onQuery` 청소보다 뒤에 있어야 하지만(그쪽 주석), 이 값 자체는
     순수 계산이라 여기서 한 번 만든다. */
  const viewQuery = buildViewQuery({ q, filters }, config);

  /* 주소가 바뀌면 화면도 따라 바뀐다 — **주소가 이 화면 뷰의 정본이다** (audit-03).
   *
   * 지금까지 읽기는 마운트 한 번(`initialView`)뿐이고 그 뒤로는 화면 → 주소 한 방향으로만
   * 되썼다. 그래서 **같은 라우트로 다시 들어오는 길** — 사이드바 메뉴를 다시 누르기, 뒤로
   * 가기 — 에서는 주소만 비고 화면은 앞 조건을 그대로 들고 있었다(react-router 가 같은
   * 라우트를 리마운트하지 않으므로 `initialView` 도 다시 안 읽는다). 그 상태의 화면은
   * 「조건 1개, 결과 22건」인데 주소는 조건이 없다고 말한다: 주소를 복사해 주면 상대는 다른
   * 화면을 보고, 새로고침 한 번이면 조사 중이던 조건이 사라진다.
   *
   * 무엇을 볼 것인가 — **react-router 의 location 이 바뀔 때만** 본다. 아래 되쓰기 효과는
   * raw `replaceState` 라 location 을 건드리지 않으므로 이 둘은 서로를 깨우지 않는다.
   * 마운트 첫 회는 건너뛴다(그 자리는 `initialView` 가 이미 읽었다).
   *
   * 무엇으로 비교하는가 — 양쪽 다 `buildViewQuery` 가 만든 **정규형**이다. 주소의 키 순서나
   * 남의 규약 키(`?id=` 같은 딥링크 의도)에 흔들리지 않는다.
   *
   * 어디에 두는가 — `onQuery` 효과보다 **앞**이다. 딥링크가 `open:"filter"` 의도로 얹는 값은
   * 그쪽이 마지막에 합쳐야 이긴다(그 값들은 전부 이 화면의 필터 키라 실제로는 같은 결과가
   * 되지만, 순서를 뒤집으면 그 합치기가 조용히 지워진다). */
  const urlSyncMountedRef = useRef(false);
  useEffect(() => {
    if (!urlSyncMountedRef.current) { urlSyncMountedRef.current = true; return; }
    const view = parseView(hashQuery(window.location.hash), config);
    // 쪽 번호는 조건이 아니다(위 `resumeChunks` 주석) — 비교에서도 뺀다.
    if (buildViewQuery({ q: view.q, filters: view.filters }, config) === viewQuery) return;
    /* 마운트와 **같은 규칙**으로 세운다: 주소가 조건을 하나라도 실었으면 그 의도가 화면
       기본값을 이기고(UB-13/RG-08), 아무것도 안 실렸으면 첫 방문과 같은 기본값으로 돌아간다. */
    const defaults = {};
    (config.filters || []).forEach((f) => { if (f.value != null && f.value !== "") defaults[f.key] = f.value; });
    setFilters(Object.keys(view.filters).length > 0 ? { ...view.filters } : defaults);
    setQ(view.q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key, location.search]);

  // 다른 화면에서 넘어온 해시 쿼리(예: 템플릿 → 문서 생성 프리필)를 소비한다. config.onQuery(params)가
  // 의도({open:'header'|'create', label?, initial})를 돌려주면 해당 폼을 프리필로 연다. 소비 후 해시에서
  // 쿼리를 지워(프래그먼트 경로는 유지) 재렌더 때 다시 열리지 않게 한다. HashRouter 경로는 그대로다.
  useEffect(() => {
    const hash = window.location.hash || "";
    const qi = hash.indexOf("?");
    if (qi < 0 || !config.onQuery) return;
    const params = {};
    try { new URLSearchParams(hash.slice(qi + 1)).forEach((v, k) => { params[k] = v; }); } catch (e) { return; }
    if (!Object.keys(params).length) return;
    const intent = config.onQuery(params);
    /* 딥링크 쿼리는 한 번 쓰고 지운다 — 다만 **남의 키만** 지운다.
       그릇(탭 셸)이 소유한 `?tab=` 은 예전부터 남겼다(안 남기면 딥링크로 들어오는 순간
       첫 탭으로 튕긴다). 여기에 **이 화면 자신의 뷰 키**(q·page·필터)를 더한다.
       그것까지 지우면 `#/jobs?status=succeeded` 로 들어온 순간 조건이 주소에서 사라져,
       링크를 공유해도 다른 화면이 열리고 뒤로가기가 조건을 잃는다 — `onQuery` 를 가진
       화면 전부가 그랬다(S18 이 `admin_jobs` 의 뒤로가기 축에서 실측). 소비 대상은
       `job_id` 같은 **의도 키**이고, 뷰 키는 어차피 바로 아래에서 이 화면이 다시 쓴다. */
    const keptShell = keepQueryKeys(hash.slice(qi + 1),
      SHELL_QUERY_KEYS.concat(ownedQueryKeys(config)));
    const cleaned = (hash.slice(0, qi) || "#") + (keptShell ? "?" + keptShell : "");
    try { window.history.replaceState(null, "", cleaned); } catch (e) { /* ignore */ }
    if (!intent) return;
    if (intent.open === "header") {
      const a = (config.headerActions || []).find((x) => x.label === intent.label);
      if (a && canDo(a)) setActionForm({ a, row: null, initial: intent.initial || null });
    } else if (intent.open === "create" && config.create && canCreate) {
      setCreateInitial(intent.initial || null); setCreating(true);
    } else if (intent.open === "filter" && intent.values) {
      // 다른 화면에서 넘어온 필터 프리필(예: 사용자 상세 → 감사 로그를 그 사용자로 필터).
      // 빈 값(undefined/null/"")은 걸러 filters 상태를 오염시키지 않는다.
      const values = {};
      Object.keys(intent.values).forEach((k) => { const v = intent.values[k]; if (v != null && v !== "") values[k] = v; });
      if (Object.keys(values).length) { setFilters((s) => ({ ...s, ...values })); }
    } else if (intent.open === "select" && intent.id != null) {
      // 목록 필터가 아니라 특정 id 하나를 곧바로 상세 드로어로 연다(예: 감사/알림에서 특정 작업·
      // 러너로 딥링크). config.endpoint + "/" + id를 그대로 조회한다(이미 다른 곳에서 쓰는 GET
      // 단건 엔드포인트 — pollJobUntilDone과 동일한 호출 형태). 응답이 {resource: {...}}로 감싸져
      // 오든(config.selectKey) 원시 객체로 오든 둘 다 지원한다.
      api(config.endpoint + "/" + intent.id).then((res) => {
        const item = (config.selectKey && res && res[config.selectKey]) || res;
        if (item) setSel(item);
      }).catch(() => {
        // 대상이 삭제됐거나(404) 권한이 없는 등 조회가 실패해도 목록 자체는 그대로 보여준다 — 다만
        // 예전엔 아무 안내 없이 조용히 실패해, 클릭해서 들어온 특정 항목을 못 찾았다는 사실을 사용자가
        // 전혀 알 수 없었다(그냥 빈 필터 목록에 떨어진 것처럼 보였다). 이제는 이유를 알려준다.
        setActionNotice({ tone: "danger", text: "연결된 항목을 열지 못했습니다(삭제되었거나 접근 권한이 없을 수 있습니다).", where: "list" });
      });
    }
    // location.search도 의존성에 넣는다 — 같은 라우트(config.key 불변)에 해시 쿼리만 바뀐 채로 다시
    // 오는 경우(예: 알림/감사에서 같은 화면으로 다른 object_id를 연달아 딥링크) React Router가 이
    // 컴포넌트를 리마운트하지 않아 config.key만 보면 새 쿼리를 영영 소비하지 못했다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.key, location.search]);

  /* PA-RC-0024: 이 화면 "자신의" 주소가 상세를 가리키는 경우(/audit/:id, /departments/:id)
   * — 위 onQuery 효과(다른 화면이 보낸 ?id= 프리필)와는 다른 경로다. config.hasIdRoute가
   * 있는 화면만 켠다(AdminRoutes.jsx에 실제로 그 :id 라우트가 등록된 화면만 — 없는 화면에서
   * 이 효과가 돌면 useParams().id가 항상 undefined라 아무 일도 안 하지만, 명시적으로 플래그를
   * 요구해 두 배선이 어긋날 여지를 아예 없앤다).
   *
   * routeIdSettledRef: :id로 막 들어온 마운트 첫 렌더에서는 sel이 아직 null이다(아래 GET이
   * 안 끝났다) — 그 순간 아래 "반대 방향" 효과가 그걸 "닫혔다"로 오해해 주소를 목록으로
   * 지웠다가 GET이 끝나면 다시 :id로 되돌리는 깜빡임이 실제로 있었다(Users.jsx에서 같은
   * 버그를 시험이 잡아서 여기도 같은 방식으로 막는다). */
  const routeIdSettledRef = React.useRef(!config.hasIdRoute || !routeId);
  useEffect(() => {
    if (!config.hasIdRoute || !routeId) { routeIdSettledRef.current = true; return; }
    if (sel && String(sel.id) === String(routeId)) { routeIdSettledRef.current = true; return; }
    setRouteIdNotFound(false);
    api(config.endpoint + "/" + routeId).then((res) => {
      const item = (config.selectKey && res && res[config.selectKey]) || res;
      if (item) setSel(item);
      else setRouteIdNotFound(true);
    }).catch(() => {
      // PA-RC-0033: 이전에는 여기서 토스트만 띄우고 끝냈다 — 몇 초 뒤 사라지면 화면에는
      // "왜 없는지"의 흔적이 남지 않았다. 서버가 이미 없는 레코드와 권한 밖 레코드를
      // 구분해 두지 않고 둘 다 404로 접어 준다(IDOR 정보 누출 방지) — 여기서도 그
      // 판단을 그대로 표현만 한다, 새로 구분하지 않는다.
      setRouteIdNotFound(true);
    }).finally(() => { routeIdSettledRef.current = true; });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.key, routeId]);

  /* 위 효과의 반대 방향 — sel이 바뀌면(행 클릭으로 열림, 닫기로 사라짐) 주소를 따라가게
   * 한다. replace를 써 방향키(뒤로가기) 한 번에 상세만 닫히고 목록까지 나가지 않게 한다.
   * routeId와 이미 같으면(방금 위 효과가 그 값으로 sel을 채운 직후 등) 쓰지 않는다 —
   * 안 그러면 새로고침 직후 같은 주소를 자기 자신에게 다시 쓰는 불필요한 replaceState가 돈다.
   * 지금 쿼리 문자열(검색어·필터·페이지)을 함께 실어야 아래 "뷰를 주소에 되쓴다" 효과가
   * 관리하는 값이 상세를 여는 순간 사라지지 않는다 — react-router의 location이 아니라
   * window.location.hash를 직접 읽는다(그 효과도 raw replaceState라 값이 거기 있다). */
  useEffect(() => {
    if (!config.hasIdRoute || !routeIdSettledRef.current) return;
    /* 🔴 **이 화면을 이미 떠났으면 주소를 되쓰지 않는다** (audit-02).
     *
     * 상세의 이동 액션(「관련 항목 보기」)은 `setSel(null)` 을 하고 해시를 목적지로 바꾼다.
     * 해시 대입은 그 자리에서 주소를 바꾸지만 `hashchange` 는 다음 차례에 온다 — 그 사이
     * React 가 sel 변화를 흘리면서 이 효과를 깨웠고, 효과는 «지금 주소의 질의»(이미 목적지의
     * 것)를 들고 경로만 이 화면으로 되돌려 놨다. 그래서 이동은 늘 `#/audit` 으로 튕겼고,
     * 이어서 `onQuery` 청소가 남의 키를 지워 걸어 둔 필터까지 잃었다.
     *
     * 규칙은 하나다: 주소가 아직 이 화면의 것일 때만 이 화면이 주소를 쓴다. 주소가 이미
     * 다른 화면을 가리키면 이동이 이긴다 — 이 컴포넌트는 곧 언마운트된다.
     *
     * 해시가 비어 있는 경우(HashRouter 가 없는 시험·임베드)는 겨루는 상대가 없으므로 그대로
     * 쓴다 — 그때는 react-router 가 주소의 정본이다. */
    /* 🔴 「이 화면의 것」은 **지금 올라와 있는 라우트**이지 `config.key` 가 아니다 (R7-06).
     *
     * 화면 키와 경로가 늘 같지는 않다. 감사 로그는 탭 그릇 안에 있고, 그릇은 탭마다 옛
     * 경로를 하나씩 더 등록한다(`AdminRoutes.jsx` 의 `old = "/" + t.key`) — `#/audit-anomalies`
     * 에서 「감사 로그」 탭을 누르면 `?tab=audit` 만 바뀌고 경로는 그 별칭 그대로다. 키로
     * 비교하면 그 순간 `here`("#/audit-anomalies") 와 `mine`("#/audit") 이 갈라져서, 열 때도
     * 닫을 때도 이 효과가 통째로 빠져나갔다 — 행을 눌러도 주소가 `/audit/:id` 가 되지 않아
     * 상세를 링크로 줄 수도, F5 로 되찾을 수도 없었다.
     *
     * `location.pathname` 은 react-router 가 **이 컴포넌트를 그리고 있는** 경로다. 그래서
     * 위 audit-02 의 겨룸에서도 여전히 옳다: 해시 대입은 그 자리에서 `window.location` 을
     * 바꾸지만 react-router 의 location 은 다음 차례에 따라오므로, 이동이 시작된 순간
     * `here`(목적지) 와 `mine`(아직 이 화면) 이 갈라지고 이 효과는 물러난다. */
    const here = hashPath(window.location.hash);
    const mine = "#" + location.pathname;
    if (here && here !== mine && here.indexOf(mine + "/") !== 0) return;
    const nextId = sel ? String(sel.id) : null;
    if (nextId === (routeId || null)) return;
    const qs = hashQuery(window.location.hash);
    const base = "/" + config.key + (nextId ? "/" + nextId : "");
    navigate(qs ? base + "?" + qs : base, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.key, sel]);

  /* 지금 보고 있는 뷰를 주소에 되쓴다 — 저장된 뷰와 링크 공유의 토대다.
   *
   * 이 효과는 **위의 onQuery 효과보다 뒤에 선언되어야 한다.** 그쪽은 딥링크 쿼리(?id=…)를
   * 소비한 뒤 해시에서 지우는데, 우리가 먼저 쓰면 그 삭제가 우리 쿼리까지 함께 지워
   * 주소가 매번 빈 상태로 되돌아간다. 뒤에서 다시 쓰면 그 순서 문제가 사라진다.
   *
   * pushState 가 아니라 replaceState 다 — 필터를 한 칸 고칠 때마다 히스토리가 쌓이면
   * '뒤로 가기'가 화면을 벗어나기까지 열 번을 눌러야 한다.
   *
   * (`viewQuery` 자체는 위에서 만든다 — 주소를 읽는 효과와 같은 값을 봐야 한다.) */
  /* 자기 키만 갈아치운다 — 이 화면이 탭 그릇 안에 있으면 그릇이 쓴 `?tab=…` 이 여기 함께
     실려 있고, 예전처럼 쿼리 전체를 덮으면 필터를 한 칸 건드리는 순간 첫 탭으로 튕긴다. */
  const ownedKeys = React.useMemo(() => ownedQueryKeys(config), [config]);
  useEffect(() => {
    const next = withHashQuery(window.location.hash, viewQuery, ownedKeys);
    if (next !== window.location.hash) {
      try { window.history.replaceState(null, "", next); } catch (e) { /* ignore */ }
    }
  }, [viewQuery, ownedKeys]);

  /* 저장된 뷰를 골랐을 때 — 그 쿼리 문자열로 화면 상태를 통째로 되돌린다.
   * 주소는 위 효과가 따라온다(여기서 두 번 쓰지 않는다). */
  function applyView(savedQuery) {
    const view = parseView(savedQuery, config);
    const defaults = {};
    (config.filters || []).forEach((f) => { if (f.value != null && f.value !== "") defaults[f.key] = f.value; });
    // 저장된 뷰에 없는 필터는 **지운다**(합치지 않는다) — 합치면 지금 걸려 있던 조건이
    // 남아 "부른 뷰와 다른 결과"가 나오고, 사용자는 뷰가 고장 났다고 생각한다.
    setFilters({ ...defaults, ...view.filters });
    // `q` 만 바꾼다 — `SearchBox` 가 그 값을 보고 입력을 맞추면서 `onSearch` 는 부르지 않아
    // 뷰가 복원한 페이지 번호가 1로 되돌아가지 않는다.
    setQ(view.q);
  }

  const total = list.total;
  // 서버 검색(searchable)이면 서버가 이미 필터한 페이지이므로 클라이언트 재필터를 하지 않는다.
  // (예전엔 paginated+searchable(예: notion-mapping)에서 q=를 서버로 보내고도 반환 페이지를 다시
  //  JSON.stringify로 걸러, 서버가 매칭한 행이 화면에서 사라지고 '총 N건'과 어긋났다.)
  // config.searchFields — 클라이언트 검색을 특정 필드만으로 좁힌다(기본은 JSON.stringify(row) 전체,
  // raw UUID·ISO 타임스탬프까지 매칭 대상이 되어 화면에 보이는 값과 무관한 매칭/오탐이 났다).
  const searchText = (r) => config.searchFields
    ? config.searchFields.map((k) => (r[k] == null ? "" : String(r[k]))).join(" ")
    : JSON.stringify(r);
  const searched = config.paginated
    ? ((config.searchable || !q) ? items : items.filter((r) => searchText(r).toLowerCase().includes(q.toLowerCase())))
    : (config.searchable ? items : items.filter((r) => !q || searchText(r).toLowerCase().includes(q.toLowerCase())));
  // clientFilter 필터(위 buildUrl 주석 참고) — 서버로 보내지 않았으니 여기서 직접 값을 비교해 거른다.
  const filteredRows = clientFilterDefs.length
    ? searched.filter((r) => clientFilterDefs.every((f) => { const v = filters[f.key]; return !v || String(r[f.key]) === v; }))
    : searched;

  /* 정렬 (지시 10).
   *
   * 옛 규칙은 「서버가 쪽을 자르는 목록에는 정렬을 아예 안 붙인다」였다. 근거는 옳았다 —
   * 보이는 20건만 정렬해 놓고 화살표를 그리면 사용자는 「가장 오래된 것」을 봤다고 믿는데
   * 실제로는 그 쪽 안에서 가장 오래된 것이다. `clientFilter` 는 결과가 줄어드는 게 눈에 보여
   * 경고 한 줄로 막을 수 있었지만, 정렬은 **틀린 순서가 맞아 보이기 때문에** 경고로 못 막는다.
   *
   * 그 근거는 정렬을 **서버로 넘기는** 순간 사라진다. 그래서 조건이 「paginated 인가」에서
   * **「서버가 그 키를 실제로 받는가」**로 바뀐다:
   *
   *   `config.serverSort: { keys: [...], default: { key, dir } }`
   *
   * 선언이 없으면 예전 그대로 화살표를 감춘다 — 서버가 못 받는 축에 조작기를 그리면 눌러도
   * 서버가 기본 정렬로 조용히 떨어뜨려 「눌렀는데 순서가 그대로」가 된다.
   * 허용 키는 서버에서 뽑아 미러로 고정한다(`frontend/src/generated/sortKeys.json`,
   * `scripts/check_sort_keys_fresh.py`) — 두 벌이 갈라지면 정확히 그 증상이 난다.
   *
   * 클라이언트 정렬(전량을 받는 화면)의 값 비교는 그대로다: 숫자면 숫자로, 아니면 한국어
   * 로케일 문자열로 — `"10" < "9"` 같은 사전순 함정을 피한다. 빈 값은 방향과 무관하게 뒤로
   * 보낸다(정렬은 값이 있는 것을 나란히 놓으려는 것이지 빈 칸을 위로 올리려는 것이 아니다). */
  const serverSort = config.serverSort || null;
  const canSort = !config.paginated || !!serverSort;
  const sortableKeys = React.useMemo(
    () => (serverSort ? new Set(serverSort.keys) : null),
    [serverSort],
  );
  /* 열마다 다시 묻는다 — 화이트리스트 밖 열은 화살표를 **안 그린다**. */
  const tableColumns = React.useMemo(
    () => (columns || []).map((c) => ({
      ...c,
      sortable: !!c.sortable && canSort && (!sortableKeys || sortableKeys.has(c.sortKey || c.key)),
    })),
    [columns, canSort, sortableKeys],
  );
  const sortedRows = React.useMemo(() => {
    /* 서버가 정렬했으면 **다시 정렬하지 않는다** — 다른 비교자로 재정렬하면 묶음 경계에서
       순서가 어긋나고, 그 어긋남이 곧 누락·중복이다. */
    if (serverSort) return filteredRows;
    if (!canSort || !sort.key) return filteredRows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return filteredRows;
    const sign = sort.dir === "desc" ? -1 : 1;
    const valueOf = (row) => (typeof col.sortValue === "function" ? col.sortValue(row) : row[sort.key]);
    return [...filteredRows].sort((a, b) => {
      const av = valueOf(a);
      const bv = valueOf(b);
      const aEmpty = av == null || av === "";
      const bEmpty = bv == null || bv === "";
      if (aEmpty || bEmpty) return aEmpty === bEmpty ? 0 : (aEmpty ? 1 : -1);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sign;
      return String(av).localeCompare(String(bv), "ko") * sign;
    });
  }, [serverSort, canSort, sort.key, sort.dir, filteredRows, columns]);

  const filtered = sortedRows;
  /* 예전에 여기 있던 것: 「total 이 줄어 현재 쪽이 사라지면 쪽 번호를 되돌린다」. 쪽 번호가
     없어지면서 그 되돌리기가 필요한 상태 자체가 사라졌다 — 마지막 행이 지워지면 목록이
     그만큼 짧아질 뿐이고, 사용자는 여전히 자기가 보던 자리에 있다. */

  // 서버 필터가 하나라도 걸려 있으면 '검색/필터 결과 없음'으로 안내(빈 화면과 구분).
  // PA-RC-0038 이전에는 config가 준 기본값(f.value — 예: 정책 status='published', 승인
  // status='pending')을 '사용자가 능동적으로 건 필터'가 아니라며 hasFilter에서 뺐다 —
  // 그런데 useQueryState는 기본값을 주소에 안 쓰므로(D-024) 주소만 보면 그 필터가
  // 없는 것처럼 보인다. 승인 화면처럼 기본값이 실제로 결과를 0으로 좁히면("대기 중인
  // 승인이 없다") 화면은 "승인 요청이 없습니다"라는 무조건형 문장을 냈다 — 실제로는
  // '대기 중'만 없고 처리된 이력은 있을 수 있는데도 필터를 지울 수단조차 없었다.
  // 기본값도 이제 hasFilter로 센다 — 필터가 전혀 없는 화면(config.filters가 비었거나
  // f.value 기본값이 없는 화면)은 filters가 항상 {}라 이 변경으로 아무것도 안 바뀐다.
  // 필터를 지우면(setFilters({})) '전체'가 되고, 그래도 0건이면(진짜 신규 설치) filters가
  // 다시 {}가 되어 자연히 아래 config.emptyTitle 온보딩 빈 상태로 떨어진다 — 두 빈 상태가
  // 서로 다른 질문(필터 때문인가 vs 정말 없는가)에 스스로 갈라져 답한다.
  const hasFilter = Object.keys(filters).some((k) => {
    const v = filters[k];
    return v != null && v !== "";
  });
  // 페이지네이션되지만 서버 검색이 없는 화면(감사·작업·문서 등)은 클라이언트 부분검색이 오해를 낳으므로 검색창을 숨긴다.
  // `inSplitView` 면 **바깥의 navigator 가 이미 같은 엔티티를 찾는다**(위 prop 주석).
  const showSearch = !inSplitView && (config.searchable || !config.paginated);
  const showToolbar = showSearch || (config.filters || []).length > 0;

  /* ── 탐색 줄이 쓰는 파생값 넷 (W5) ──────────────────────────────────────────
   *
   * **순서.** C2 «그룹 순서 고정» 은 scope(부서) → entity(담당자·프로젝트) → 분류 →
   * 상태 → 기간 이다. 예전에는 선언 순서가 곧 화면 순서라 화면마다 축의 순서가 달랐고,
   * 그 순서는 registry 28곳에 흩어져 있어 한 곳에서 고칠 수 없었다. 정렬은 여기서 한 번 한다.
   * 안정 정렬이라 같은 그룹 안에서는 선언 순서가 유지된다.
   *
   * **Entity 옵션.** `optionsFromRefList` 는 폼 필드만 쓰던 것인데, 필터에도 같은 것이
   * 필요하다 — `/jobs` 의 «연결된 스케줄 ID» 는 사람이 UUID 를 손으로 붙여넣는 자유
   * 텍스트였다. 후보 목록이 이미 있는데 그것을 안 쓰던 자리다.
   */
  const orderedFilters = React.useMemo(() => {
    const rank = (f) => FILTER_GROUP_ORDER.indexOf(filterGroupOf(f));
    const resolved = (config.filters || []).map((f) => {
      if (!f.optionsFromRefList) return f;
      const base = refListOptions[f.optionsFromRefList] || [];
      /* 후보 목록을 못 받은 축은 **왜 비었는지** 말한다 (R7-05) — 그 말이 없으면
         「권한이 없어 못 받았다」와 「후보가 정말 없다」가 화면에서 같은 그림이다. */
      const failed = refListFailedKeys.has(f.optionsFromRefList);
      return {
        ...f, kind: "entity", options: [...base, ...(f.extraOptions || [])],
        loading: refListsQuery.isLoading,
        helperText: failed ? REF_LIST_FAILED_TEXT : f.helperText,
      };
    });
    return resolved
      .map((f, i) => ({ f, i }))
      .sort((a, b) => (rank(a.f) - rank(b.f)) || (a.i - b.i))
      .map((x) => x.f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.filters, refListOptions, refListsQuery.isLoading, refListFailedKeys]);

  /* 저장된 뷰는 **조건 조합을 재사용할 가치가 있을 때만** 뜻이 있다. 후보가 두어 줄뿐인
     화면(정책 2건·통합 4건·기능 플래그 11건)에 붙으면 그것은 기능이 아니라 소음이고,
     C2 는 그런 화면을 «검색만 있는 Toolbar» 로 규정한다. 판단은 화면마다 다르므로
     숫자를 기계 적용하지 않고 registry 가 `smallSet` 한 줄로 선언한다(R-88). */
  const showSavedViews = !config.smallSet && !inSplitView;
  /* 저장된 뷰는 검색창이 있든 없든 필터 바 한 줄의 오른쪽 끝 묶음이다 — 도구 줄과 조건 줄을 나누던 때
     (D-455)처럼 자리가 둘로 갈리지 않는다(조합 계약 C-1). */
  const savedViewsControl = showSavedViews ? (
    <SavedViews
      screenKey={config.key}
      query={viewQuery}
      describe={(saved) => describeView(saved, config)}
      onApply={applyView}
    />
  ) : null;

  /* 결과 건수 — 서버가 total 을 주면 그것이 정본이고, 안 주는 화면은 지금 그려지는 행 수다.
     Pager 안의 «총 N건» 과 같은 값이지만 자리가 다르다: Pager 는 «어디쯤인가» 를 말하고
     결과 줄은 «이 조건에 몇 건인가» 를 말한다. 한 페이지짜리 목록에서 Pager 가 사라져도
     건수는 남아야 한다. */
  const resultTotal = total != null ? total : filtered.length;
  /* 조건 칩 — **모든 조건은 칩을 가진다**(조합 계약 C-1). 검색어도, registry 가 준 기본값(승인 대기 · 게시됨)도
     조건이다: 기본값도 결과를 좁히고 `hasFilter` 가 그것을 센다(PA-RC-0038). 칩의 낱말은 칸이 보이는 낱말과
     같다 — 「이름: 값」, 값은 후보의 이름(없으면 식별자를 드러내지 않는 낱말). 조건 수는 칩 수다. */
  const filterChips = React.useMemo(() => {
    const chips = [];
    if (q) chips.push({ key: "q", label: `검색: ${q}`, onDelete: () => setQ("") });
    for (const f of orderedFilters) {
      const v = filters[f.key];
      if (v == null || v === "") continue;
      const options = normalizeOptions(f.options || []);
      const hit = options.find((o) => String(o.value) === String(v));
      const shown = hit
        ? hit.label
        : (f.type === "datetime-local" ? String(v).replace("T", " ") : unmatchedLabel(v, !!f.loading));
      chips.push({ key: f.key, label: `${f.label}: ${shown}`, onDelete: () => setFilter(f.key, "") });
    }
    return chips;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, filters, orderedFilters]);
  // 빈 화면 CTA: config.create 우선, 없으면 headerActions 중 primary로 표시된 '생성 성격' 작업만.
  // (headerActions[0]을 무조건 CTA로 쓰면 '복원 안내'·'모두 읽음' 같은 비생성 작업이 잘못 노출된다.)
  // role 게이트를 통과한 헤더 작업만 노출한다(권한 없는 버튼이 403 데드엔드가 되지 않도록).
  // 헤더 작업의 when(ctx)은 목록 응답에서 뽑은 약간의 맥락(현재는 unreadCountKey 값)을 받는다 —
  // 알림의 '모두 읽음'처럼 '할 일이 없을 때는 굳이 보여줄 필요 없는' 헤더 버튼을 위한 것이다
  // (예전엔 unread===0이어도 버튼이 항상 떠 있어 눌러도 매번 '0건 처리' 무의미 토스트만 났다).
  // managementScope/isGlobalAdmin — 머리 액션도 범위를 안다(xa-07). 전역 자원의 머리 버튼은
  // `requiresGlobalScope` 로 걸리고, 그보다 세밀한 조건은 이 맥락을 읽어 when 이 판단한다.
  // 실리는 값은 서버가 깎아 낸 관리 범위다(`/api/me` 의 management.kind — 위 주석) —
  // `admin_scope` 열이 아니다.
  const headerActionCtx = {
    unreadCount: (config.unreadCountKey && query.data) ? query.data[config.unreadCountKey] : null,
    managementScope, isGlobalAdmin,
  };
  const visibleHeaderActions = (config.headerActions || []).filter((a) => canDo(a) && (!a.when || a.when(headerActionCtx)));
  const primaryHeaderAction = visibleHeaderActions.find((a) => a.primary);
  const showCreate = config.create && canCreate;   // '추가'는 create.roles를 통과한 역할에만.
  // 헤더 액션, CTA도 드로어 액션과 동일하게 busy로 막는다(중복 클릭, 느린 동기 호출 방지) -
  // 예전엔 드로어 footer 버튼만 막혀 '+ 백업 실행', '자동 동기화', '+ 문서 생성', '지금 실행' 등은
  // 진행 중에도 계속 눌러 중복 제출을 낼 수 있었다.
  const createBtn = showCreate
    ? <Button variant="primary" disabled={busy} onClick={() => setCreating(true)}>{config.createLabel || "추가"}</Button>
    : (primaryHeaderAction ? <Button variant="primary" disabled={busy} loading={busyKey === "h-primary"} onClick={() => runHeaderAction(primaryHeaderAction, "h-primary")}>{primaryHeaderAction.label}</Button> : null);
  /* 머리 액션도 같은 규칙이다 — 주 동작(추가)이 primary 이고, 위험한 것은 그 옆에 나란히
   * 두지 않는다. 예전에는 registry 의 `variant:"danger"` 머리 액션(예: '전체 삭제')이
   * '추가' 바로 왼쪽에 같은 크기로 앉았다. */
  /* 머리 액션의 위험 판정 — 상세 액션(`isRisky`)과 같은 규칙이지만 그쪽은 아래에서
   * 정의된다(sel 이 필요하다). 판정 자체는 한 줄이라 두 번 쓰는 대신 여기 먼저 둔다.
   *
   * 🔴 **`primary` 는 그 화면의 주 동작이라 «...» 뒤로 안 숨긴다** (2026-09-01).
   *
   * 「확인을 한 번 묻는다」와 「파괴적이다」는 다른 사실인데 이 한 줄이 둘을 같은 것으로
   * 읽었다. 그래서 백업 화면의 «백업 실행» — `primary: true` 인 그 화면의 존재 이유 —
   * 이 머리에서 사라지고 «...» 메뉴 안에 **빨간 글씨**로 들어가 있었다. 백업을 지금
   * 한 번 뜨는 것은 되돌릴 수 없는 파괴가 아니라 이 화면이 하라고 있는 일이다.
   * `primary` 를 선언한 액션은 언제나 머리에 선다 — 확인 대화는 그대로 뜬다. */
  const isRiskyHeader = (a) => !a.primary && (a.variant === "danger" || !!a.confirm);
  const inlineHeaderActions = visibleHeaderActions.filter((a) => !isRiskyHeader(a));
  const overflowHeaderActions = visibleHeaderActions.filter(isRiskyHeader);
  const headerKeyOf = (a) => "h" + visibleHeaderActions.indexOf(a);
  const headerActions = (
    <>
      {inlineHeaderActions.map((a) => (
        <Button key={headerKeyOf(a)} variant={a.variant || "default"} disabled={busy}
          loading={busyKey === headerKeyOf(a)}
          onClick={() => runHeaderAction(a, headerKeyOf(a))}>{a.label}</Button>
      ))}
      <OverflowMenu
        ariaLabel={config.title + " 화면 작업 더 보기"}
        items={overflowHeaderActions.map((a) => ({
          key: headerKeyOf(a),
          label: busyKey === headerKeyOf(a) ? "처리 중…" : a.label,
          tone: "danger",
          disabled: busy,
          onClick: () => runHeaderAction(a, headerKeyOf(a)),
        }))}
      />
      {showCreate ? <Button variant="primary" disabled={busy} onClick={() => setCreating(true)}>{config.createLabel || "추가"}</Button> : null}
    </>
  );
  const hasHeaderActions = showCreate || visibleHeaderActions.length > 0;
  // 상세 드로어 하단(수정·액션) 노출 계산 — 실제로 그릴 버튼이 없으면 빈 footer 막대를 렌더하지 않는다.
  // 수정 버튼도 edit.roles/create.roles로 게이트한다(쓰기 권한 없는 역할에겐 숨긴다).
  const canEdit = !!(sel && editFields && canEditRole && (!config.editWhen || config.editWhen(sel)));
  // when(row, ctx) — ctx에 role·userId를 넘겨 본인 요청 자기결정 차단 등 행 단위 게이트를 지원한다.
  // managementScope/isGlobalAdmin 도 함께 넘긴다(xa-07) — 「범위가 '전체'인 행은 부서 범위
  // 관리자가 못 고친다」처럼 **행의 값과 내 범위를 같이 봐야** 정해지는 게이트가 있다.
  const actionCtx = { role, userId, managementScope, isGlobalAdmin };
  const visibleActions = sel ? (config.actions || []).filter((a) => (!a.when || a.when(sel, actionCtx)) && canDo(a)) : [];
  /* 액션 위계 (지시 8 · 11 · 12 · 43).
   *
   * 예전에는 이 목록을 그대로 평평한 버튼 줄로 그렸다 — registry 가 `variant:"danger"` 로
   * 선언한 파괴적 동작이 주 동작 '수정' 옆에 같은 크기로 앉았다. 되돌리기 어려운 일과 가장
   * 자주 하는 일이 시선을 다투면 안 된다.
   *
   * `danger`/`confirm` 을 위험 신호로 본다 — registry 가 확인 대화를 붙였다는 것은 그 동작이
   * 한 번 더 물어봐야 하는 일이라고 이미 판단한 것이다. 판정을 새로 만들지 않고 그 선언을 쓴다. */
  const isRisky = (a) => a.variant === "danger" || !!a.confirm;
  const safeActions = visibleActions.filter((a) => !isRisky(a));
  const riskyActions = visibleActions.filter(isRisky);
  /* 무해한 액션은 둘까지 버튼으로 남긴다 — 자주 쓰는 것을 한 번에 누를 수 있어야 한다.
     그 이상은 세로 목록이 훑기 쉽다. */
  const INLINE_ACTION_LIMIT = 2;
  const inlineActions = safeActions.slice(0, INLINE_ACTION_LIMIT);
  const overflowActions = [...safeActions.slice(INLINE_ACTION_LIMIT), ...riskyActions];
  /* 넘침 메뉴 항목은 원래 인덱스를 그대로 들고 가야 `busyKey`("a"+i) 가 어긋나지 않는다. */
  const actionKeyOf = (a) => "a" + visibleActions.indexOf(a);
  // 온보딩 안내(situation/steps 등)는 실제로 '생성' 성격 CTA를 볼 수 있는 역할에만 보여준다 -
  // create.roles(canCreate)뿐 아니라 primary 헤더 작업('+ 백업 실행', '+ 문서 생성', '자동 동기화')을
  // CTA로 쓰는 화면도 포함한다(그렇지 않으면 create 없는 화면의 온보딩 단계가 영영 렌더되지 않았다).
  // RG-06: 이 게이트는 "안내가 가리키는 버튼을 이 역할이 볼 수 있는가"를 묻는데, 안내 자체가
  // 웹 버튼이 아니라 **서버 CLI 단계**를 설명하는 화면(복구 리허설)은 create도 primary
  // headerAction도 없어 canOnboard가 항상 거짓이었다 — 화면 접근 자체가 이미 역할로 걸려 있으니
  // (App.jsx SCREEN_ROLES) 그런 화면은 config.forceOnboarding으로 이 게이트를 우회한다.
  // 정본은 `screenHelp.jsx::canOnboardFor` 하나다 — `?` 도움말의 절차 안내와 빈 상태의 CTA 가
  // 같은 게이트를 봐야 한쪽에만 나오는 일이 없다. 주 머리 동작의 `when(ctx)` 도 같은 맥락
  // (`headerActionCtx`)으로 본다 — 머리에 없는 단추를 안내가 가리키지 않게 (P-88).
  const canOnboard = canOnboardFor(config, role, headerActionCtx);
  /* 목록 끝 줄 — 받은 건수와 「더 보기」. 두 자리에서 쓴다: 목록 카드 안, 그리고
     clientFilter 로 지금 받아 둔 것이 통째로 걸러진 빈 상태(더 받으면 일치 항목이 나올 수 있다).
     🔴 「몇 건을 받았는가」는 **서버가 준 원본**(`items`)으로 센다 — clientFilter 로 걸러진
     `filtered` 로 세면 걸러진 화면에서 「더 보기」가 조용히 꺼진다(옛 페이저가 겪은 결함). */
  const listFooter = config.paginated ? (
    <ListFooter
      total={total}
      loaded={items.length}
      hasNext={list.hasNext}
      isFetchingNext={list.isFetchingNext}
      onMore={list.fetchNext}
    />
  ) : null;
  /* VIS-117 이 「목록 위에도 페이저를 하나 더」로 고쳤던 것 — 100행짜리 화면에서 다음 쪽으로
     넘기려고 매번 6,186px 를 굴러 내려가야 했다 — 은 이제 결함 자체가 없다. 굴러 내려가는 그
     행동이 곧 다음 묶음을 부른다. 그래서 위쪽 조작기를 두지 않는다. */

  return (
    <div className="c-screen">
      {/* config.help는 고정 문자열 또는 (role)=>문자열 함수, emptyHelp와 동일한 role-aware 패턴.
       * 화면이 역할별로 다른 컨트롤을 노출할 때(예: 러너의 '수정'에서만 가능한 점검 상태 전환) 그
       * 컨트롤이 없는 역할에게까지 그 안내를 그대로 보여주지 않을 수 있게 한다.
       * WF1 단독 결함(admin_policies) — 이 배너는 항상 기본(info) 톤이었다. 아래 capWarning 등
       * 다른 Callout은 이미 tone="warn"을 쓰는데, 위험도가 다른 화면(예: 정책의 "발행하면 즉시
       * 실사용된다")이 프롬프트의 일반 안내와 똑같은 파란 상자로 보였다 — config.helpTone으로
       * 화면별 위험도를 반영할 수 있게 한다(기본값 info라 기존 화면은 전부 그대로).
       * PA-RC-0022: 이 안내는 registry 28개 화면 전부가 이 자리 하나를 같이 쓴다 — 예전엔
       * PageHeader 바로 아래 상시 Callout으로 그렸는데, 그러면 화면을 열 때마다 매번 문단을
       * 지나쳐야 했다(8+ 화면 실측). PageHeader의 `help`/`helpTone` prop으로 옮겨 제목 옆
       * 도움말 토글 + 기본 접힘으로 바꾼다 — 문구는 한 글자도 안 바꾼다, 보이는 방식만 바뀐다. */}
      {/* 탭 그릇 안에서는 제목을 그리지 않는다 — 그릇이 제목·`?`·머리 동작 자리를 그린다.
          제목을 두 번 그리면 한 탭에 페이지가 둘 겹쳐 있는 것처럼 읽힌다(SettingsShell 이
          `embedded` 로 같은 문제를 먼저 풀었다).

          🔴 여기 오른쪽 정렬 줄에 `Callout variant="inline"` 로 도움말을 그렸다 — 탭 그릇
          안의 목록 화면만 도움말이 제목 옆 `?` 가 아니라 **오른쪽 끝의 안내 상자**였다.
          도움말은 그릇이 `?` 로 그리고(`AdminRoutes` 가 `buildScreenHelp` 를 탭 정의에
          싣는다, D-453), 머리 동작은 그릇 머리의 오른쪽 자리에 그린다(D-454). 그릇이 없으면
          (시험·단독 임베드) 예전 자리에 동작 줄만 남긴다. */}
      {embedded ? (
        hasHeaderActions ? (
          <HeaderActions
            fallback={
              <Box sx={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 2 }}>
                {headerActions}
              </Box>
            }
          >
            {headerActions}
          </HeaderActions>
        ) : null
      ) : (
        <PageHeader area={config.area} title={config.title} size={config.compact ? "section" : "page"}
          actions={hasHeaderActions ? headerActions : null}
          help={buildScreenHelp(config, role, headerActionCtx)}
          helpTone={config.helpTone || "info"} />
      )}
      {/* 서버가 개수 제한(예: 500건)만 걸고 total/페이지네이션을 주지 않는 목록에서, 항목 수가 그
       * 한도에 닿으면 '더 있을 수 있음'을 알린다(자를 뿐 안 알리면 데이터가 조용히 사라진 것처럼 보인다).
       * paginated:true + 서버가 실제 total을 주는 화면(프롬프트/정책 등)은 페이저가 이미 '총 N건'을
       * 정확히 보여주므로, 이 경고를 함께 띄우면 마치 데이터가 숨겨진 것처럼 오해를 준다 — 그런
       * 화면에서는 억제한다(진짜로 total 없이 자르기만 하는 화면에서만 뜬다). */}
      {config.capWarning && items.length >= config.capWarning && !(config.paginated && total != null) ? (
        <Callout tone="warn">{"결과가 " + config.capWarning + "건으로 제한되어 일부 항목이 보이지 않을 수 있습니다. 검색, 필터로 좁혀 보세요."}</Callout>
      ) : null}
      {/* clientFilter는 이미 받아 온 현재 페이지만 거른다, paginated 화면에서 함께 쓰면 다른 페이지의
       * 일치 항목이 안 보여 '골랐는데 결과가 잘못된' 오해를 준다(예: Notion 연결의 '출처' 필터).
       * 그 한계를 분명히 알리고, 아래 빈 상태에서도 페이저를 남겨 다른 페이지를 넘겨 볼 수 있게 한다. */}
      {/* 어떤 필터가 페이지 안에서만 도는지 **이름으로** 말한다. 예전에는 "(예: 출처, 모드)"를
       * 손으로 박아 뒀는데, 그 사이 '출처'는 서버 필터로 옮겨 갔다 — 안내가 화면보다 늦게
       * 늙는다. 목록을 clientFilterDefs에서 만들면 설정이 바뀌는 순간 문구도 함께 바뀐다. */}
      {config.paginated && clientFilterDefs.length ? (
        <Callout tone="warn">{"‘" + clientFilterDefs.map((f) => f.label).join("’, ‘") + "’ 필터는 지금 보고 있는 페이지에만 적용됩니다. 다른 페이지의 일치 항목은 ‘다음’으로 페이지를 넘겨 확인하세요."}</Callout>
      ) : null}
      {/* 목록 응답에 이미 실려 오는 카운트(예: 알림의 unread)를 별도 요약 엔드포인트 없이 바로 보여준다. */}
      {config.unreadCountKey && query.data && query.data[config.unreadCountKey] != null ? (
        /* 값 하나는 큰 숫자 하나다 — 상태 요약 카드의 값 하나 갈래(계획 P-30 · 핸드오프 RULES §10). */
        <StatusSummaryCard
          ariaLabel="안 읽음"
          sx={{ mb: 2.5 }}
          total={query.data[config.unreadCountKey]}
          totalLabel="안 읽음"
          totalKind={query.data[config.unreadCountKey] > 0 ? "warn" : undefined}
        />
      ) : null}
      {config.summary ? (
        summaryQuery.isLoading ? (
          <Card><Skeleton lines={1} /></Card>
        ) : summaryQuery.isError ? (
          // 401(세션 만료)이면 '다시 시도'를 눌러도 같은 401만 반복된다, 메인 목록의 ErrorState는
          // 이 경우 '로그인 화면으로' 링크를 보여주는데, 요약 카드만 별도 쿼리라 여기선 늘 일반
          // '다시 시도' 버튼을 보여줘 실제로 회복 안 되는 재시도를 계속 제안했다(거짓 희망).
          summaryQuery.error && summaryQuery.error.status === 401 ? (
            <Callout tone="warn">요약 통계를 불러오지 못했습니다(로그인이 필요합니다). <a href={loginUrl()}>로그인 화면으로</a></Callout>
          ) : summaryQuery.error && (summaryQuery.error.status === 403 || summaryQuery.error.status === 404) ? (
            /* 403/404도 401과 같은 이유로 재시도해도 회복되지 않는다(ErrorState의 판단과 동일) -
               영원히 실패할 '다시 시도' 버튼 대신 이유만 알린다(거짓 희망 방지).
               403 은 오류가 아니라 **권한 상태**다 - 고칠 것이 아니라 알 것이라 조용히 알린다.
               404 는 있어야 할 것이 없는 것이라 오류로 말한다(지시 35). */
            <Callout tone={summaryQuery.error.status === 403 ? "info" : "danger"}>{"요약 통계를 불러오지 못했습니다(" + (summaryQuery.error.status === 403 ? "권한이 없습니다" : "찾을 수 없습니다") + ")." + (summaryQuery.error.status === 403 ? " 관리자에게 문의하세요." : " 이미 삭제되었거나 이동했을 수 있습니다.")}</Callout>
          ) : (
            <Callout tone="danger">요약 통계를 불러오지 못했습니다. <Button size="sm" onClick={() => summaryQuery.refetch()}>다시 시도</Button></Callout>
          )
        ) : summaryQuery.data ? (
          <>
            {/* 요약의 그릇은 데이터의 뜻이 정한다 — `summary.kind`(상태 구성 · 측정값 · 속성, 계획 표 7). */}
            <SummaryView
              summary={config.summary}
              data={summaryQuery.data}
              ctx={{ setFilter }}
              sx={{ mb: config.summary.notes ? 1.5 : 2.5 }}
            />
            {/* 🔴 **경고는 개수가 아니라 문장이다** (2026-09-01). 요약 줄은 「N건」밖에 못
                말하는데, 이 자리에 오는 것들(「백업이 앱과 같은 디스크에만 있습니다」)은
                읽는 순간 할 일이 정해지는 문장이라 세어 봐야 아무 소용이 없다. 화면이
                `notes(data)` 로 문장 목록을 주면 그대로 낸다. 빈 배열이면 아무것도 안 그린다 —
                할 말이 없을 때 빈 상자를 남기지 않는다. */}
            {(config.summary.notes ? config.summary.notes(summaryQuery.data) : []).map((note, i) => (
              <Callout key={i} tone="warn">{note}</Callout>
            ))}
          </>
        ) : null
      ) : null}
      {showToolbar ? (
        /* 탐색 줄 — **판이 아니다**(지시 80). 검색과 필터가 한 줄에 서고 저장된 뷰가 그 줄 오른쪽 끝이다(조합 계약 C-1).
         * 예전에는 검색만 한 줄을 쓰고 필터를 다음 줄로 내렸다(1920 에서도 두 줄) — 도구 줄과 조건 줄이 한 질문을
         * 둘로 나눠 답했다. 걸린 조건은 같은 면 안 조건 줄이 칩으로 말하고, 「필터 지우기」는 그 줄의 것이다.
         * SEM-02(PA-F-031): DataScreen 이 registry 목록 화면 다수가 공유하는 셸이라 여기 한 번 제목을 더하면 그 전부가
         * 한꺼번에 해결된다. 시각은 그대로(.sr-only) — PageHeader 가 compact(h2)로 쓰이는 자리에선 한 단계 낮춘다. */
        <>
          <Typography component={config.compact ? "h3" : "h2"} className="sr-only">필터</Typography>
          <FilterBar
            search={showSearch ? (
              <SearchBox
                value={q}
                onSearch={commitSearch}
                placeholder={config.searchPlaceholder || "검색"}
                ariaLabel={config.searchPlaceholder || (config.title + " 검색")}
              />
            ) : null}
            /* 저장된 뷰는 «어떻게 볼지» 쪽이다 — 조건 칸이 아니라 줄 끝 묶음에 붙는다. 후보가 몇 줄 안 되는 화면에는
               아예 그리지 않는다(C2 · registry 의 `smallSet`). */
            end={savedViewsControl}
            conditions={{
              chips: filterChips,
              total: !query.isLoading && !query.isError ? resultTotal : null,
              /* 필터가 여러 개 걸려 있을 때 하나씩 지우지 않고 한 번에 지운다. */
              onClearAll: (q || hasFilter) ? () => { setQ(""); setFilters({}); } : null,
              clearLabel: "필터 지우기",
            }}
          >
            {orderedFilters.map((f) => {
              // `key` 는 spread 에 섞지 않는다 — React 가 spread 안의 key 를 경고한다. 키는 요소에 직접 준다.
              const common = {
                label: f.label,
                value: filters[f.key] || "",
                onChange: (v) => setFilter(f.key, v),
              };
              /* Entity(프로젝트·사용자·워크플로처럼 **데이터가 쌓이는 만큼 후보가 자라는** 축)는 검색형 Combobox 다.
                 닫힌 열거형(상태·유형)은 select 그대로다 — R-5 가 "모든 Select 를 무조건 검색형으로 바꾸지 않는다" 고 못박는다. */
              if (f.kind === "entity") {
                return (
                  <EntityCombobox
                    key={f.key}
                    {...common}
                    loading={f.loading}
                    options={f.options || []}
                    /* 후보를 못 받은 축은 빈 상자가 아니라 이유를 단다 (R7-05). */
                    helperText={f.helperText}
                  />
                );
              }
              if (f.type === "select") {
                return (
                  <FilterSelect
                    key={f.key}
                    {...common}
                    options={f.options || []}
                    /* 어법은 **한 벌**이다. 예외는 **「전체」가 서버에 없는 축**이다(감사 이상 징후의 기간 — 서버는
                       언제나 창을 두고 센다). 그런 축은 registry 가 빈 값의 이름을 직접 준다. */
                    allLabel={f.allLabel}
                  />
                );
              }
              if (f.type === "date") {
                // REAUDIT §15.5 — 기간 필터도 적용 대상이다. `common.onChange` 는 값 하나만 받는 계약이라 `DateField` 와 맞는다.
                return (
                  <DateField
                    key={f.key}
                    {...common} id={f.key} size="small"
                    data-filter-kind="date"
                    sx={kindSx("date")}
                  />
                );
              }
              if (f.type === "datetime-local") {
                // 날짜만 다루는 `DateField` 와 계약이 다르다(시각 포함, KST 경계). 브라우저는 datetime 입력의 placeholder 를
                // 무시한다 — 칸 안 이름(접두)이 나란히 놓인 시작/종료 두 칸을 가른다. 폭은 날짜시각(18rem) 칸이다.
                return (
                  <DebouncedTextField
                    key={f.key} type={f.type} kind="datetime" label={f.label}
                    value={filters[f.key] || ""}
                    onCommit={(v) => setFilter(f.key, v)}
                  />
                );
              }
              /* 🔴 `datalistFrom` 갈래는 없앴다 — 서버가 목록을 자르는 화면에서 「받아 둔 것 안의 값」만 제안하면
               * 사용자는 그것을 「이 시스템에 있는 값이 이게 전부」로 읽는다. `registry-filter-axes.test.js` 가 부활을 막는다.
               * 라벨은 **항상 칸 안**이고 타자는 **디바운스**된다 — 둘 다 이 부품이 든다(F-W5D-115). */
              return (
                <DebouncedTextField
                  key={f.key}
                  label={f.label}
                  value={filters[f.key] || ""}
                  onCommit={(v) => setFilter(f.key, v)}
                  freeTextReason={f.freeTextReason}
                />
              );
            })}
          </FilterBar>
        </>
      ) : null}
      {/* 결과 수는 조건이 걸리면 필터 바 안 조건 줄이, 늘 목록 판 발이 말한다 — 목록 위 단독 결과 줄은 없다(조합 계약 C-1). */}
      {actionNotice && (actionNotice.where === "list" || !sel) ? (
        <Callout tone={actionNotice.tone} compact sx={{ mb: 2 }}>{actionNotice.text}</Callout>
      ) : null}
      {/* SEM-02: 로딩·오류·빈 상태·정상 목록 네 갈래 전부를 아우르는 자리에 한 번만 둔다
          (갈래마다 넣으면 하나는 반드시 빠뜨린다). */}
      <Typography component={config.compact ? "h3" : "h2"} className="sr-only">목록</Typography>
      {query.isLoading ? (
        /* 표가 들어올 자리에는 표 모양을 그린다 (지시 20). 회색 줄 다섯 개는 "곧 목록이 온다"가
           아니라 "무언가 온다"라는 뜻이고, 실제 표가 도착하면 배치가 통째로 튄다. */
        <ListCard><DataTable columns={columns} rows={[]} loading /></ListCard>
      ) : query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : filtered.length === 0 ? (
        <>
        {(q || hasFilter) ? (
          /* 목록 화면에서 이 상태는 **화면 전체**다 — 표도 Pager 도 없다. 그래서 가운데
             구성으로 선다(`kit.jsx::EmptyState` 의 `layout`). 판 안의 빈 칸과 같은 부품을
             쓰되 자리가 다르면 다르게 그린다. */
          <EmptyState layout="page" title="검색 결과가 없습니다" art="search"
            help="조건에 맞는 항목이 없습니다. 검색어나 필터를 지워보세요."
            action={<Button variant="primary" onClick={() => { setQ(""); setFilters({}); }}>검색, 필터 지우기</Button>} />
        ) : (
          <EmptyState layout="page" title={config.emptyTitle || "표시할 항목이 없습니다"}
            help={typeof config.emptyHelp === "function" ? config.emptyHelp(role, createBtn) : config.emptyHelp}
            // situation 은 '추가'·'활성화' 같은 쓰기 전용 버튼을 가리킨다 — 그 CTA 를 볼 수 있는
            // role(canOnboard)에만 보여준다. 준비물·절차·기대 결과는 빈 상태가 아니라 제목 옆
            // `?` 도움말이 든다(D-456, `screenHelp.jsx`) — 빈 상태는 제목 + 한 문장 + 동작이다.
            situation={canOnboard ? config.emptySituation : undefined}
            relatedLink={config.emptyRelatedLink}
            action={createBtn} />
        )}
        {/* paginated+clientFilter 화면에서 현재 페이지가 필터로 통째로 비어도, 다른 페이지에 일치
         * 항목이 있을 수 있으므로 페이저를 남긴다(위 경고 Callout과 짝을 이룬다). */}
        {config.paginated && clientFilterDefs.length ? <ListCard>{listFooter}</ListCard> : null}
        </>
      ) : (
        <ListCard>
          {/* 표에게 **자기 질의 계약**을 알려 준다 (R-91). 이것 없이는 표가 어떤 열도
              없애지 않는다 — 서버가 페이지를 자르는 목록에서 이번 페이지의 값이 우연히
              같다고 열을 빼면, 페이지를 넘길 때마다 열이 생겼다 사라진다.
              `activeFilters` 는 **사용자가 직접 건 조건**만이다: 그 조건의 열이 사라지는
              것은 사용자가 유발한 변화라 예측 가능하고, 조건을 풀면 열이 돌아온다.
              `fixedColumns` 는 안 넘긴다 — 「이 질의에서 이 값은 구조적으로 불변이다」는
              화면마다 다른 사실이라 registry 가 스스로 선언해야 하고, 그 선언은 아직 없다.
              추측으로 채우면 그 순간 이 계약이 뜻을 잃는다. */}
          <DataTable
            columns={tableColumns} rows={filtered} onRow={setSel} total={total}
            /* 목록 화면은 **전부** 열 이름을 고정한다. 예전에는 registry 가 화면마다 켰고
               (실제로 켠 것은 감사 로그 하나였다) 그나마도 안 돌았다 — 표를 감싼 판의
               `overflow:hidden` 이 sticky 의 스크롤 창이 되어 열 이름이 그 판 안에 붙박였다
               (`kit.jsx::ListCard`). 굴려서 다음 묶음을 받는 목록에서 열 이름이 사라지면
               스무 줄만 지나도 어느 값이 어느 열인지 알 수 없다. */
            stickyHeader
            rowKey={(r) => r.id || (columns[0] ? r[columns[0].key] : JSON.stringify(r).slice(0, 24))}
            sort={canSort ? sort : undefined} onSort={canSort ? toggleSort : undefined}
            resultScope={{
              serverPaged: !!config.paginated,
              activeFilters: Object.keys(filters).filter((k) => filters[k] !== "" && filters[k] != null),
              fixedColumns: config.fixedColumns || [],
            }}
            /* §15.1 재검수 — registry 마다 손으로 켜지 않는다(정책 2건짜리와 감사 로그
               몇백 건짜리가 같은 화면을 쓴다). 행이 실제로 많을 때만 켠다.
               🔴 판정 기준이 **받은 행 수가 아니라 전체 건수**다. 받은 수로 재면 묶음이
               붙다가 60을 넘는 순간 가상화가 켜지면서 `<tbody>` 가 통째로 다시 마운트된다 —
               굴리던 자리가 튄다. 전체 건수는 묶음이 붙어도 안 변한다.
               `stickyHeader` 와의 상호배타는 없어졌다 — 둘 다 윈도를 스크롤 창으로 본다. */
            virtualize={(total ?? filtered.length) > 60 ? {} : undefined}
          />
          {listFooter}
        </ListCard>
      )}
      {/* 상세는 넓은(lg) 폭 — 액션 버튼이 많은 화면(러너 등)에서 좁은(md) 폭이면 푸터 버튼이 3줄로
          접혀 화면 맨 아래 뭉치가 됐다. lg 폭 + 작은 버튼으로 한두 줄에 담아 깔끔하게 만든다.

          VIS-162 — 상세 안에서 여는 수정/액션 폼(FormDrawer)이 필드 6개 이상이면 똑같이 lg(992px)
          라 상세를 픽셀 하나 안 남기고 완전히 덮었다(제목은 겹치니 남지만 방금 보던 값들은
          사라진다). sel은 그대로 두고(취소하면 이 값으로 되돌아온다 — 아래 각 onClose가 sel을
          안 건드리는 이유) 화면에서만 잠깐 숨긴다. navigate 액션(위 runAction)이 이미 하던
          setSel(null)과 같은 발상을 나머지 중첩 오버레이 셋(actionForm/subView/infoView)에도
          일관되게 적용한다. */}
      <Modal open={(!!sel || routeIdNotFound) && !editing && !actionForm && !subView && !infoView}
        onClose={() => {
          // PA-RC-0033: 없는 id 오류는 sel이 애초에 null이라 아래 "반대 방향" 효과(sel 변화
          // 감지)가 안 걸린다 — 여기서 직접 목록 주소로 되돌린다(같은 element라 목록
          // 인스턴스는 그대로, PA-RC-0024 계약 유지).
          if (routeIdNotFound) {
            setRouteIdNotFound(false);
            const qs = hashQuery(window.location.hash);
            navigate(qs ? "/" + config.key + "?" + qs : "/" + config.key, { replace: true });
          } else {
            setSel(null);
          }
        }}
        title={sel ? detailTitle(sel, columns) : ""} size="lg"
        footer={(sel && (canEdit || visibleActions.length)) ? (
          /* 모달 발은 `ActionFooter` 하나다 — 면 · 위 선 · 여백의 주인이 하나이고, 발의 단추는 34 다(핸드오프 RULES §3 · 계획 B-7). 발에 ghost 를 두지 않는다. */
          <ActionFooter
            placement="modal"
            extra={(
              <>
                {inlineActions.map((a) => (
                  <Button key={actionKeyOf(a)} variant={a.variant || "default"} disabled={busy}
                    loading={busyKey === actionKeyOf(a)}
                    onClick={() => runAction(a, sel, actionKeyOf(a))}>{a.label}</Button>
                ))}
                {/* 파괴적 동작과 저빈도 액션은 세로 목록으로 내린다 — 실선이 손이 미끄러지는
                    거리를 준다(kit.jsx::OverflowMenu). 이웃 단추와 같은 높이(34)다. */}
                <OverflowMenu
                  ariaLabel={config.title + " 작업 더 보기"}
                  items={overflowActions.map((a) => ({
                    key: actionKeyOf(a),
                    label: busyKey === actionKeyOf(a) ? "처리 중…" : a.label,
                    tone: isRisky(a) ? "danger" : undefined,
                    disabled: busy,
                    onClick: () => runAction(a, sel, actionKeyOf(a)),
                  }))}
                />
              </>
            )}
          >
            {canEdit ? <Button variant="primary" disabled={busy} onClick={() => setEditing(sel)}>수정</Button> : null}
          </ActionFooter>
        ) : null}>
        {/* 상세는 라벨/값 쌍이 20개 넘는 화면(러너·워크플로)이 있다. 좁은 화면은 한 열, 넓은
            화면은 두세 열로 접어 스크롤을 줄인다 — 4K에서 한 열로 길게 늘어놓으면 오른쪽이
            통째로 비고 눈은 위아래로만 움직인다. */}
        {sel && actionNotice && actionNotice.where === "detail" ? (
          <Callout tone={actionNotice.tone} compact sx={{ mb: 2 }}>{actionNotice.text}</Callout>
        ) : null}
        {sel ? (
          <DetailGrid>
            {mergeDetailFields(config, columns).map((c, i) => (
              <DetailRow key={c.key || "d" + i} label={c.label}>
                {c.render ? c.render(sel) : (sel[c.key] == null || sel[c.key] === "" ? "-" : String(sel[c.key]))}
              </DetailRow>
            ))}
          </DetailGrid>
        ) : routeIdNotFound ? (
          <ErrorState layout="region" error={{ status: 404 }} />
        ) : null}
      </Modal>

      {config.create ? (
        <FormDrawer open={creating} title={config.createLabel || (config.title + " 추가")} fields={withOptionsFrom(resolveFields(config.create.fields), null)}
          screenKey={config.key} formKind="create"
          initial={createInitial || {}} submitLabel="추가" onClose={() => { setCreating(false); setCreateInitial(null); }}
          onSubmit={async (body) => {
            // toApiBody — 폼이 보여주는 필드 이름(예: 체크박스 하나)과 백엔드가 받는 계약 형태(예:
            // {approval_policy:{required:bool}})가 다를 때 전송 직전에 변환한다(템플릿의 승인 정책 등).
            const apiBody = config.toApiBody ? config.toApiBody(body) : body;
            const res = await api(config.endpoint, { method: "POST", body: apiBody });
            setCreating(false); setCreateInitial(null); refresh(); (config.onCreated ? config.onCreated(res, { toast }) : announce(res, "추가했습니다."));
          }} />
      ) : null}
      {editFields ? (
        <FormDrawer open={!!editing} title={(editing ? detailTitle(editing, columns) : "") + " 수정"} fields={withOptionsFrom(editFields, editing)}
          screenKey={config.key} formKind="edit"
          // fromRow — 서버가 돌려주는 행 모양(예: {approval_policy:{required:bool}})을 폼 필드 이름
          // (예: 체크박스 하나)으로 되돌려 편집 폼을 올바른 초기값으로 연다.
          initial={editing ? (config.fromRow ? config.fromRow(editing) : editing) : {}} submitLabel="저장" onClose={() => setEditing(null)}
          onSubmit={async (body) => {
            const prev = editing;
            const editMethod = config.editMethod || "PATCH";
            const initialFormValues = editing ? (config.fromRow ? config.fromRow(editing) : editing) : {};
            const fullApiBody = config.toApiBody ? config.toApiBody(body) : body;
            // CONC-01: PATCH 화면은 전체 스냅샷이 아니라 실제로 바뀐 필드만 보낸다(diffFields,
            // Users.jsx의 수정 폼과 같은 방식을 등록 화면 전체로 확장) — 안 그러면 이 폼이 열려
            // 있는 사이 다른 관리자가 바꾼 필드(예: 서킷 브레이커가 자동으로 내린
            // maintenance_state)를 조용히 원래 값으로 되돌려 버릴 수 있다. toApiBody 변환 **뒤**의
            // 값으로 비교한다 — 그 전 값(폼 필드 이름)으로 비교하면 여러 폼 필드가 객체 하나로
            // 합쳐지는 화면(예: 승인 정책 체크박스 → {required:bool})에서 무관한 필드만 바뀌어도
            // diff가 그 객체 전체를 "바뀜"으로 잘못 잡을 수 있다.
            // editMethod가 PUT인 화면(schedules·templates)은 백엔드가 전체 표현을 요구하는 진짜
            // REST PUT이다(app/schedules/router.py의 ScheduleRequest는 부분 스키마가 아니다) —
            // 부분 body를 보내면 "나머지는 그대로"가 아니라 검증 실패나 기본값 초기화로 이어질 수
            // 있어 그대로 전체를 보낸다(이 화면들은 CONC-01의 남은 범위로 문서에 남긴다).
            const apiBody = editMethod === "PATCH"
              ? diffFields(fullApiBody, config.toApiBody ? config.toApiBody(initialFormValues) : initialFormValues)
              : fullApiBody;
            if (editMethod === "PATCH" && Object.keys(apiBody).length === 0) {
              setEditing(null); setSel(null);
              toast("변경된 내용이 없습니다.", "info");
              return;
            }
            const res = await api(config.endpoint + "/" + editing.id, { method: editMethod, body: apiBody });
            setEditing(null); setSel(null); refresh();
            // 저장 후 훅(예: 스케줄 정의 변경으로 자동 비활성화됨)이 경고를 직접 알린 경우 기본 성공 토스트는 생략한다.
            /* `notice` — 저장 뒤 사람이 알아야 할 결과(정의 변경으로 비활성화됨 등)를 상세 안에 남긴다. */
            const handled = config.onSaved
              ? config.onSaved(res, { toast, prev, notice: (text, tone) => setActionNotice({ tone: tone || "warn", text, where: "detail" }) })
              : false;
            if (!handled) announce(res, "저장했습니다.");
          }} />
      ) : null}
      {actionForm ? (
        <FormDrawer open={!!actionForm} title={actionForm.a.label}
          fields={withOptionsFrom(actionForm.a.fields, actionForm.row)}
          initial={actionForm.initial || {}}
          submitLabel={actionForm.a.label} onClose={() => setActionForm(null)}
          onSubmit={async (body) => {
            // 액션에 고정 body(예: 롤백의 name)가 있으면 폼 값과 합쳐 보낸다(폼 값이 우선).
            const fixed = actionForm.a.body ? (typeof actionForm.a.body === "function" ? actionForm.a.body(actionForm.row) : actionForm.a.body) : null;
            const merged = fixed ? { ...fixed, ...body } : body;
            // transform — 폼이 보여주는 명명 필드(예: 문서 생성의 template_id·source_database…)를 백엔드
            // 계약 형태(config dict)로 조립한다(create의 toApiBody와 같은 역할, 액션 폼 버전).
            const finalBody = actionForm.a.transform ? actionForm.a.transform(merged) : merged;
            const res = await api(actionForm.a.path(actionForm.row), { method: actionForm.a.method || "POST", body: finalBody });
            setActionForm(null);
            // runAction/runHeaderAction과 동일한 공용 결과 처리(result/announce/keepSelection/
            // localPatch/pollJob) — 입력 폼을 먼저 여는 액션도 다른 액션과 같은 방식으로 다룬다.
            finishAction(actionForm.a, res, actionForm.row);
          }} />
      ) : null}
      {subView ? (
        <SubListDrawer view={subView} onClose={() => setSubView(null)} onActed={() => { refresh(); }} />
      ) : null}
      {infoView ? (
        <Modal open onClose={() => setInfoView(null)} title={infoView.title} size="md"
          footer={<ActionFooter placement="modal"><Button variant="primary" onClick={() => setInfoView(null)}>확인</Button></ActionFooter>}>
          <JsonBlock>{infoView.body}</JsonBlock>
        </Modal>
      ) : null}
    </div>
  );
}

