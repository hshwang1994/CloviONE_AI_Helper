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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { PageHeader, Card, Button, DataTable, FormDrawer, Modal, Skeleton, EmptyState, ErrorState, StatCard, Callout, useConfirm, useToast } from "../ui/kit.jsx";
/* 검색 입력은 `ui/filters.jsx` 의 `SearchBox` 다 — **자기 상태를 자기가 든다**(PF4).
 *
 * 예전에는 그 부품이 이 파일 안에 있었다. 사용자 콘솔의 티켓·문서 목록도 같은 것이 필요해
 * 지면서 올렸다: 같은 뜻의 검색창이 세 벌이면 한쪽만 고쳐지는 날이 오고, 그때 증상은
 * "이 화면 검색만 느리다" 라서 원인이 안 보인다. */
import { SearchBox } from "../ui/filters.jsx";
// 필터 줄 격자 — TicketFilterBar.jsx 와 공유(ui/FilterBar.jsx). 트랙 상한을 포함해 한 곳에서만 정한다.
import { FilterBarGrid } from "../ui/FilterBar.jsx";
import { SavedViews } from "../ui/SavedViews.jsx";
import { buildViewQuery, describeView, hashQuery, parseView, withHashQuery } from "./datascreen-view.js";
// 아래 네 갈래는 원래 이 파일 안에 있던 것을 data-screen/ 로 옮긴 것이다(800줄 규칙, §23).
// 이 파일이 그 뜻(설정 주도 목록 화면의 본체)을 그대로 갖고, 조각들은 여기서만 조립한다.
import { JsonBlock } from "./data-screen/JsonBlock.jsx";
import { CROSS_SCREEN_KEYS } from "./data-screen/crossScreenKeys.js";
import { handleApiError } from "./data-screen/apiError.js";
import { mergeDetailFields, detailTitle } from "./data-screen/detailFields.js";
import { SubListDrawer } from "./data-screen/SubListDrawer.jsx";
import { successMessageFor } from "./data-screen/successMessages.js";

// 열/필드 렌더 헬퍼(badgeCol 등)의 실제 구현은 data-screen/columnHelpers.jsx로 옮겼다.
// registry/shared.js가 `from "../DataScreen.jsx"`로 이 이름들을 그대로 가져다 쓰므로
// (수십 개 화면의 registry.js가 그 재수출에 기댄다) import 계약이 깨지지 않게 여기서 재수출한다.
export {
  badgeCol, mapCol, dateCol, activeCol, linkCol, truncateCol, readCol,
  jsonField, objectField, listField, previewField,
} from "./data-screen/columnHelpers.jsx";

/* 요약 카드 줄(config.summary.cards / config.unreadCountKey) 격자 — 카드 수가 화면마다 다르다
 * (/notifications 1장 · /ai-quotas 2장 · /restore-drills 4장 · /jobs 6~7장). 예전엔 고정
 * `repeat(4,...)`(더 넓은 화면에서 5·6)라 카드 수가 그 열 수의 약수가 아니면 마지막 줄이
 * 어중간하게 남았다 — 4장 폭에 6장이 4+2로 접혀 둘째 줄에 ~1,100px 빈 칸(VIS-119/137),
 * /notifications는 1장 뒤로 ~1,300px(VIS-151). Home.jsx의 STAT_GRID는 카드가 "항상 정확히
 * 6장"이라 고정 열 수가 맞지만, 이 요약 줄은 화면마다 카드 수 자체가 다르므로 같은 해법이
 * 안 맞는다 — `auto-fit`은 카드 수와 무관하게 매번 그 줄을 꽉 채운다(적게 있으면 남은 폭을
 * 나눠 갖고, 많으면 다음 줄로 넘어갈 뿐 빈 칸을 안 남긴다). 최소 폭(14rem)은 이 줄의 가장 긴
 * 라벨(예: "가장 오래된 대기", "자동 백업 (Asia/Seoul)")이 줄바꿈 없이 들어가는 값이다. */
const SUMMARY_CARD_GRID = "repeat(auto-fit, minmax(14rem, 18rem))";

/* 설정 주도 목록 화면 — 여러 관리자 화면이 같은 읽기+상세+생성/수정/작업 패턴을 공유한다(§23).
 * 각 화면은 registry.js의 config만 다르다. 행 클릭 → 상세 모달(열 + config.detailFields 전체 필드).
 * 생성·수정은 공통 중앙 모달 폼. headerActions=폼 없는 즉시 실행/입력폼. 액션에 subList가 있으면
 * 하위 리소스(버전·실행 이력 등)를 별도 드로어로 조회한다. config.paginated면 서버 페이지네이션. */
export function DataScreen({ config }) {
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
  const [page, setPage] = useState(initialView.page);
  // 검색 디바운스 — 서버 검색 화면(searchable, 특히 Notion 조회처럼 요청당 최대 30초 걸리는 화면)에서
  // 매 키 입력마다 새 요청을 쏘지 않는다(예전엔 한 글자씩 칠 때마다 retry:false 요청이 겹쳐 나가
  // 응답이 뒤죽박죽 도착했다).
  //
  // **검색어가 실제로 바뀐 경우에만** 돈다. 예전엔 마운트 때도 무조건 한 번 돌아 `setPage(1)`을
  // 했는데, 이제 주소(#/audit?…&page=3)와 저장된 뷰가 페이지 번호를 복원하므로 그 한 번이
  // 복원한 페이지를 300ms 뒤에 조용히 1로 되돌린다 — 사용자는 링크를 열었는데 다른 화면을 본다.
  // 검색 확정은 `SearchBox` 가 디바운스해서 부른다. 이 함수는 **참조가 고정**돼야 한다 —
  // 매 렌더마다 새로 만들면 `React.memo` 가 매번 깨져 이 수정이 무효가 된다.
  const commitSearch = React.useCallback((next) => { setQ(next); setPage(1); }, []);
  const [sel, setSel] = useState(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [actionForm, setActionForm] = useState(null); // 입력이 필요한 액션(예: 수동 연결)
  const [createInitial, setCreateInitial] = useState(null); // 다른 화면에서 넘어온 생성 폼 프리필 값
  const [subView, setSubView] = useState(null);        // 하위 리소스 조회(버전·실행 이력)
  const [infoView, setInfoView] = useState(null);      // 결과 안내 모달(예: 복원 안내)
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
  // 액션 role 게이트 — a.roles가 지정된 액션은 현재 역할이 포함될 때만 노출(백엔드 RBAC와 일치시켜 403 사전 차단).
  const canDo = (a) => !a.roles || (role != null && a.roles.includes(role));
  // 생성/수정 버튼도 액션과 같은 방식으로 role 게이트한다(create.roles / edit.roles) — 읽기 전용
  // 역할(operator/auditor)이 항상 403이 되는 '+ 추가'·'수정' 버튼을 애초에 숨긴다.
  const canCreate = config.create ? (!config.create.roles || (role != null && config.create.roles.includes(role))) : false;
  const editRoles = (config.edit && config.edit.roles) || (config.create && config.create.roles) || null;
  const canEditRole = !editRoles || (role != null && editRoles.includes(role));
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
  const withOptionsFrom = (fields, row) => (fields || []).map((f) => {
    if (f.optionsFrom) return { ...f, type: "select", options: f.optionsFrom(row, items) };
    if (f.optionsFromRefList) {
      const base = refListOptions[f.optionsFromRefList] || [];
      return { ...f, type: "select", options: [...base, ...(f.extraOptions || [])] };
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

  const serverFilterDefs = (config.filters || []).filter((f) => !f.clientFilter);
  const clientFilterDefs = (config.filters || []).filter((f) => f.clientFilter);
  function buildUrl() {
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
    if (config.paginated) { p.push("page=" + page); if (config.pageSize) p.push("page_size=" + config.pageSize); }
    return config.endpoint + (p.length ? "?" + p.join("&") : "");
  }
  // queryKey는 서버로 실제 전송되는 필터만 반영한다 — clientFilter 값이 바뀌어도 같은 데이터를 다시
  // 받아올 필요가 없다(그 값은 아래 filtered 계산에서만 쓰인다).
  const serverFiltersKey = JSON.stringify(Object.fromEntries(serverFilterDefs.map((f) => [f.key, filters[f.key]])));
  const query = useQuery({
    queryKey: [...cacheRoot, config.searchable ? q : "", config.paginated ? page : 0, serverFiltersKey],
    queryFn: () => api(buildUrl()),
    retry: false,
    // 페이지네이션/필터/검색이 바뀌면 queryKey도 바뀌어 캐시가 없다 — placeholderData로 이전 페이지
    // 결과를 유지한 채 백그라운드로 새 페이지를 받아온다(예전엔 매 클릭·키 입력마다 목록+페이저
    // 전체가 Skeleton으로 사라졌다가 다시 나타났다).
    placeholderData: keepPreviousData,
    // 진행 중(pending 등) 행이 있으면 자동 새로고침(비동기 상태 전이를 화면이 따라간다).
    refetchInterval: config.pollWhile
      ? (qy) => { const d = qy.state.data; const its = (d && d[config.itemsKey || "items"]) || []; return its.some(config.pollWhile) ? 4000 : false; }
      : false,
  });
  // 요약 통계(선택) — 목록과 별도 엔드포인트(예: 작업 큐 stats)를 받아 상단 StatCard 줄로 보여준다.
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
  const refListsQuery = useQuery({
    queryKey: [...cacheRoot, "refLists", (config.refLists || []).map((r) => r.key).join(",")],
    queryFn: async () => {
      const pairs = await Promise.all(
        (config.refLists || []).map(async (rl) => [rl.key, (await api(rl.endpoint))[rl.itemsKey || "items"] || []])
      );
      return Object.fromEntries(pairs);
    },
    enabled: !!(config.refLists && config.refLists.length),
    retry: false,
  });
  const refListOptions = React.useMemo(() => {
    const data = refListsQuery.data || {};
    const out = {};
    (config.refLists || []).forEach((rl) => {
      out[rl.key] = (data[rl.key] || []).map((row) => ({
        value: row[rl.valueKey || "id"],
        label: row[rl.labelKey || "name"] + (row.enabled === false ? " (비활성)" : ""),
      }));
    });
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refListsQuery.data, config.refLists]);
  function setFilter(key, val) { setFilters((s) => ({ ...s, [key]: val })); setPage(1); }
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
      try { const j = await api("/api/admin/jobs/" + jobId); job = (j && j.job) || j; } catch (e) { if (e && e.status === 401) { handleApiError(e, toast); return; } continue; }
      if (job && terminal.includes(job.status)) {
        refresh();
        if (job.status === "succeeded") toast(opts.doneMsg || "완료되었습니다.", "success");
        else toast((opts.failMsg || "작업이 실패했습니다. 잠시 후 다시 시도해 주세요.") + (job.last_error ? ": " + job.last_error : ""), "error");
        return;
      }
    }
    refresh();
    toast(opts.timeoutMsg || "작업이 아직 진행 중입니다. 잠시 후 목록을 새로고침하세요.", "info");
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
      toast(rr.msg, rr.kind || (rr.ok ? "success" : "error"));
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
  async function runAction(a, row, key) {
    if (a.navigate) { setSel(null); window.location.hash = a.navigate(row); return; }  // 다른 화면으로 이동(HashRouter)
    // 파일 내려받기 — `api()`(fetch)로는 브라우저 저장 대화상자가 뜨지 않는다. 브라우저가
    // 직접 그 주소로 가야 Content-Disposition 이 먹는다. **지금 화면의 서버 필터를 그대로
    // 넘긴다**(buildUrl 이 만든 질의 문자열) — 화면에서 좁혀 놓고 눌렀는데 전체가 내려오면
    // 받은 파일은 화면에서 본 것과 다른 데이터이고, 그 차이는 열어 보기 전까지 아무도 모른다.
    if (a.download) {
      const listUrl = buildUrl();
      const qs = listUrl.includes("?") ? listUrl.slice(listUrl.indexOf("?") + 1) : "";
      window.location.href = a.download(qs, row);
      return;
    }
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
      handleApiError(e, toast);
      // 결과 담지 액션(a.result — 헬스체크·백업 검증 등)이 실패해도, 서버가 이미 결과를 기록했을 수
      // 있다(예: 러너 '테스트'의 RunnerUnavailableError는 record_runner_result 이후 발생) — 성공 경로만
      // refresh하면 그 실패 기록이 목록에 반영되지 않는다.
      if (a.result) refresh();
    }
    finally { setBusyKey(null); }
  }
  async function runHeaderAction(a, key) {
    if (a.info) {
      // 조회형 헤더 작업(예: 복원 안내) — 결과를 안내 모달로 보여준다. busy를 걸어 완료 전 중복 클릭을 막는다
      // (그 아래 쓰기 액션 분기와 동일한 패턴 — 예전엔 이 분기만 setBusy가 빠져 있었다).
      setBusyKey(key);
      try { const res = await api(a.path(), { method: a.method || "GET" }); setInfoView({ title: a.label, body: a.info(res) }); }
      catch (e) { handleApiError(e, toast); }
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
    } catch (e) { handleApiError(e, toast); }
    finally { setBusyKey(null); }
  }
  const items = (query.data && query.data[config.itemsKey || "items"]) || [];
  // config.columnsFrom(응답) — 열이 **서버 응답에서 결정되는** 화면용(권한 매트릭스: 역할이
  // 곧 열이다). 화면에 역할 목록을 한 벌 더 적으면 백엔드에서 규칙을 고쳐도 표는 옛 열을
  // 계속 보여 준다 — 그리고 그때 사람은 화면을 믿는다(app/core/authz.py가 유일한 출처).
  // 응답이 아직 없을 때는 빈 배열이 아니라 config.columns로 떨어져 로딩 중 크래시를 막는다.
  const columns = config.columnsFrom
    ? (query.data ? config.columnsFrom(query.data) : (config.columns || []))
    : config.columns;
  // sel.id가 이번 드로어 세션에서 한 번이라도 items 안에서 실제로 확인됐는지 — 액션이 res.item으로
  // (예: 프롬프트 '새 버전') 아직 목록에 반영되지 않은 새 행을 곧바로 sel에 넣는 경우, 그 행이
  // 아직 items에 없다고 곧장 드로어를 닫아 버리면 안 되므로 '한 번이라도 봤던 적 있는지'로 구분한다.
  const sawFreshRef = useRef(false);
  // 열린 상세 드로어를 백그라운드 refetch(pollWhile)와 동기화 — 캡처된 stale sel이 아니라 최신 행을 보여준다.
  // fetching 도중(예: 필터가 막 바뀌어 아직 새 페이지가 안 온 순간)엔 items가 일시적으로 비거나 옛
  // 페이지일 수 있어 판단을 보류한다 — 완료된 refetch에서 이미 한 번 확인됐던 sel.id가 더 이상 없으면
  // (다른 관리자가 지웠거나, 페이지네이션/필터에 걸려 빠졌거나) 그 낡은 항목을 계속 보여주는 대신 드로어를 닫는다.
  useEffect(() => {
    if (!sel || sel.id == null) { sawFreshRef.current = false; return; }
    if (query.isFetching) return;
    const fresh = items.find((r) => r.id === sel.id);
    if (fresh) {
      sawFreshRef.current = true;
      if (fresh !== sel) setSel(fresh);
    } else if (sawFreshRef.current) {
      sawFreshRef.current = false;
      setSel(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, query.isFetching]);
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
    try { window.history.replaceState(null, "", hash.slice(0, qi) || "#"); } catch (e) { /* ignore */ }
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
      if (Object.keys(values).length) { setFilters((s) => ({ ...s, ...values })); setPage(1); }
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
        toast("연결된 항목을 열지 못했습니다(삭제되었거나 접근 권한이 없을 수 있습니다).", "error");
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
    api(config.endpoint + "/" + routeId).then((res) => {
      const item = (config.selectKey && res && res[config.selectKey]) || res;
      if (item) setSel(item);
    }).catch(() => {
      toast("연결된 항목을 열지 못했습니다(삭제되었거나 접근 권한이 없을 수 있습니다).", "error");
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
   * '뒤로 가기'가 화면을 벗어나기까지 열 번을 눌러야 한다. */
  const viewQuery = buildViewQuery({ q, page, filters }, config);
  useEffect(() => {
    const next = withHashQuery(window.location.hash, viewQuery);
    if (next !== window.location.hash) {
      try { window.history.replaceState(null, "", next); } catch (e) { /* ignore */ }
    }
  }, [viewQuery]);

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
    setQ(view.q); setPage(view.page);
  }

  const total = query.data && query.data.total;
  const pageSize = (query.data && query.data.page_size) || config.pageSize || 20;
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
  const filtered = clientFilterDefs.length
    ? searched.filter((r) => clientFilterDefs.every((f) => { const v = filters[f.key]; return !v || String(r[f.key]) === v; }))
    : searched;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / pageSize)) : null;
  // 마지막 페이지의 마지막 행이 사라지는 변경(예: 마지막 대기 승인 처리) 후 total이 줄어 현재 페이지가
  // 더 이상 존재하지 않게 되면, '필터 지우기'로 검색/필터까지 통째로 지우지 않고 페이지 번호만
  // 유효한 값으로 되돌린다(그 상태로는 영영 빈 화면만 보였다).
  useEffect(() => {
    if (config.paginated && totalPages != null && page > totalPages) setPage(totalPages);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalPages]);

  // 서버 필터가 하나라도 걸려 있으면 '검색/필터 결과 없음'으로 안내(빈 화면과 구분).
  // 단, config에서 준 기본값(f.value — 예: 정책 status='published', 승인 status='pending')은
  // '사용자가 능동적으로 건 필터'가 아니다 — 그 값과 같은 필터는 hasFilter로 치지 않는다.
  // 그렇지 않으면 신규 설치(0건)에서도 항상 '검색 결과가 없습니다'만 떠서, 정성껏 만든 온보딩
  // 빈 상태(config.emptyTitle/steps)가 사실상 죽은 코드가 됐다.
  const defaultFilterVals = {};
  (config.filters || []).forEach((f) => { if (f.value != null && f.value !== "") defaultFilterVals[f.key] = f.value; });
  const hasFilter = Object.keys(filters).some((k) => {
    const v = filters[k];
    if (v == null || v === "") return false;
    return String(v) !== String(defaultFilterVals[k] == null ? "" : defaultFilterVals[k]);
  });
  // 페이지네이션되지만 서버 검색이 없는 화면(감사·작업·문서 등)은 클라이언트 부분검색이 오해를 낳으므로 검색창을 숨긴다.
  const showSearch = config.searchable || !config.paginated;
  const showToolbar = showSearch || (config.filters || []).length > 0;
  // 빈 화면 CTA: config.create 우선, 없으면 headerActions 중 primary로 표시된 '생성 성격' 작업만.
  // (headerActions[0]을 무조건 CTA로 쓰면 '복원 안내'·'모두 읽음' 같은 비생성 작업이 잘못 노출된다.)
  // role 게이트를 통과한 헤더 작업만 노출한다(권한 없는 버튼이 403 데드엔드가 되지 않도록).
  // 헤더 작업의 when(ctx)은 목록 응답에서 뽑은 약간의 맥락(현재는 unreadCountKey 값)을 받는다 —
  // 알림의 '모두 읽음'처럼 '할 일이 없을 때는 굳이 보여줄 필요 없는' 헤더 버튼을 위한 것이다
  // (예전엔 unread===0이어도 버튼이 항상 떠 있어 눌러도 매번 '0건 처리' 무의미 토스트만 났다).
  const headerActionCtx = { unreadCount: (config.unreadCountKey && query.data) ? query.data[config.unreadCountKey] : null };
  const visibleHeaderActions = (config.headerActions || []).filter((a) => canDo(a) && (!a.when || a.when(headerActionCtx)));
  const primaryHeaderAction = visibleHeaderActions.find((a) => a.primary);
  const showCreate = config.create && canCreate;   // '+ 추가'는 create.roles를 통과한 역할에만.
  // 헤더 액션, CTA도 드로어 액션과 동일하게 busy로 막는다(중복 클릭, 느린 동기 호출 방지) -
  // 예전엔 드로어 footer 버튼만 막혀 '+ 백업 실행', '자동 동기화', '+ 문서 생성', '지금 실행' 등은
  // 진행 중에도 계속 눌러 중복 제출을 낼 수 있었다.
  const createBtn = showCreate
    ? <Button variant="primary" disabled={busy} onClick={() => setCreating(true)}>{config.createLabel || "+ 추가"}</Button>
    : (primaryHeaderAction ? <Button variant="primary" disabled={busy} onClick={() => runHeaderAction(primaryHeaderAction, "h-primary")}>{busyKey === "h-primary" ? "처리 중…" : primaryHeaderAction.label}</Button> : null);
  const headerActions = (
    <>
      {visibleHeaderActions.map((a, i) => (
        <Button key={"h" + i} variant={a.variant || "default"} disabled={busy} onClick={() => runHeaderAction(a, "h" + i)}>{busyKey === ("h" + i) ? "처리 중…" : a.label}</Button>
      ))}
      {showCreate ? <Button variant="primary" disabled={busy} onClick={() => setCreating(true)}>{config.createLabel || "+ 추가"}</Button> : null}
    </>
  );
  const hasHeaderActions = showCreate || visibleHeaderActions.length > 0;
  // 상세 드로어 하단(수정·액션) 노출 계산 — 실제로 그릴 버튼이 없으면 빈 footer 막대를 렌더하지 않는다.
  // 수정 버튼도 edit.roles/create.roles로 게이트한다(쓰기 권한 없는 역할에겐 숨긴다).
  const canEdit = !!(sel && editFields && canEditRole && (!config.editWhen || config.editWhen(sel)));
  // when(row, ctx) — ctx에 role·userId를 넘겨 본인 요청 자기결정 차단 등 행 단위 게이트를 지원한다.
  const actionCtx = { role, userId };
  const visibleActions = sel ? (config.actions || []).filter((a) => (!a.when || a.when(sel, actionCtx)) && canDo(a)) : [];
  // 온보딩 안내(situation/steps 등)는 실제로 '생성' 성격 CTA를 볼 수 있는 역할에만 보여준다 -
  // create.roles(canCreate)뿐 아니라 primary 헤더 작업('+ 백업 실행', '+ 문서 생성', '자동 동기화')을
  // CTA로 쓰는 화면도 포함한다(그렇지 않으면 create 없는 화면의 온보딩 단계가 영영 렌더되지 않았다).
  // RG-06: 이 게이트는 "안내가 가리키는 버튼을 이 역할이 볼 수 있는가"를 묻는데, 안내 자체가
  // 웹 버튼이 아니라 **서버 CLI 단계**를 설명하는 화면(복구 리허설)은 create도 primary
  // headerAction도 없어 canOnboard가 항상 거짓이었다 — 화면 접근 자체가 이미 역할로 걸려 있으니
  // (App.jsx SCREEN_ROLES) 그런 화면은 config.forceOnboarding으로 이 게이트를 우회한다.
  const canOnboard = config.forceOnboarding || canCreate || !!primaryHeaderAction;
  // 페이저는 목록 카드와, clientFilter로 현재 페이지가 통째로 걸러진 빈 상태 두 곳에서 함께 쓴다
  // (paginated+clientFilter 화면에서 현재 페이지가 필터로 비어도 다른 페이지로 넘어갈 수 있게).
  const renderPager = (edge) => (
    <Box component="nav" aria-label={edge === "top" ? "페이지 이동(목록 위)" : "페이지 이동"}
      sx={{
        display: "flex", alignItems: "center", justifyContent: "center", gap: 2,
        ...(edge === "top"
          ? { pb: 2, mb: 1, borderBottom: 1, borderColor: "divider" }
          : { pt: 2, mt: 1, borderTop: 1, borderColor: "divider" }),
      }}>
      <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>이전</Button>
      <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ minWidth: "8rem", textAlign: "center" }}>
        {totalPages != null ? `${page} / ${totalPages}${total != null ? `, 총 ${total}건` : ""}` : `${page}페이지`}
      </Typography>
      <Button size="sm" disabled={totalPages != null ? page >= totalPages : items.length < pageSize} onClick={() => setPage((p) => p + 1)}>다음</Button>
    </Box>
  );
  const pager = config.paginated ? renderPager("bottom") : null;
  // VIS-117: 100행짜리 화면(예: /jobs, 6,186px)에서 페이지 이동이 맨 아래에만 있으면 다음 페이지로
  // 넘기려고 매번 화면 끝까지 스크롤해야 한다 — 목록 위에도 같은 컨트롤을 하나 더 둔다(총
  // 페이지가 2 이상일 때만, 1페이지짜리 화면에 안 쓰는 컨트롤을 얹지 않는다). 버튼 하나로
  // 로직을 공유하므로 동작은 항상 아래 페이저와 같다.
  const topPager = config.paginated && (totalPages != null ? totalPages > 1 : items.length >= pageSize)
    ? renderPager("top") : null;

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
      <PageHeader area={config.area} title={config.title} size={config.compact ? "section" : "page"}
        actions={hasHeaderActions ? headerActions : null}
        help={config.help ? (typeof config.help === "function" ? config.help(role) : config.help) : null}
        helpTone={config.helpTone || "info"} />
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
        <Box sx={{ display: "grid", gap: 2, mb: 2.5, gridTemplateColumns: SUMMARY_CARD_GRID }}>
          <StatCard value={query.data[config.unreadCountKey]} label="안 읽음" kind={query.data[config.unreadCountKey] > 0 ? "warn" : undefined} />
        </Box>
      ) : null}
      {config.summary ? (
        summaryQuery.isLoading ? (
          <Card><Skeleton lines={1} /></Card>
        ) : summaryQuery.isError ? (
          // 401(세션 만료)이면 '다시 시도'를 눌러도 같은 401만 반복된다, 메인 목록의 ErrorState는
          // 이 경우 '로그인 화면으로' 링크를 보여주는데, 요약 카드만 별도 쿼리라 여기선 늘 일반
          // '다시 시도' 버튼을 보여줘 실제로 회복 안 되는 재시도를 계속 제안했다(거짓 희망).
          summaryQuery.error && summaryQuery.error.status === 401 ? (
            <Callout tone="warn">요약 통계를 불러오지 못했습니다(로그인이 필요합니다). <a href="/login">로그인 화면으로</a></Callout>
          ) : summaryQuery.error && (summaryQuery.error.status === 403 || summaryQuery.error.status === 404) ? (
            // 403/404도 401과 같은 이유로 재시도해도 회복되지 않는다(ErrorState의 판단과 동일) -
            // 영원히 실패할 '다시 시도' 버튼 대신 이유만 알린다(거짓 희망 방지).
            <Callout tone="warn">{"요약 통계를 불러오지 못했습니다(" + (summaryQuery.error.status === 403 ? "권한이 없습니다" : "찾을 수 없습니다") + ")." + (summaryQuery.error.status === 403 ? " 관리자에게 문의하세요." : " 이미 삭제되었거나 이동했을 수 있습니다.")}</Callout>
          ) : (
            <Callout tone="warn">요약 통계를 불러오지 못했습니다. <Button size="sm" onClick={() => summaryQuery.refetch()}>다시 시도</Button></Callout>
          )
        ) : summaryQuery.data ? (
          <Box sx={{ display: "grid", gap: 2, mb: 2.5, gridTemplateColumns: SUMMARY_CARD_GRID }}>
            {config.summary.cards(summaryQuery.data, { setFilter }).map((c, i) => <StatCard key={i} value={c.value} label={c.label} kind={c.kind} onClick={c.onClick} />)}
          </Box>
        ) : null
      ) : null}
      {showToolbar ? (
        /* 필터 바 — 감사 로그처럼 필터가 6개 넘게 붙는 화면이 있어서 한 줄에 밀어 넣지 않고
         * 자동 줄바꿈 그리드로 둔다(TicketFilterBar 와 같은 트랙, ui/FilterBar.jsx 공유).
         * 화면이 넓어지면 열이 늘어 한 줄에 담긴다.
         * SEM-02(PA-F-031): DataScreen이 registry.js 기반 목록 화면(/jobs·/audit·/prompts·
         * /notifications 등) 다수가 공유하는 셸이라, 여기 한 번 h2를 더하면 그 전부가
         * 한꺼번에 해결된다. 시각은 그대로(.sr-only) — PageHeader가 compact(h2)로 쓰이는
         * 자리에선 한 단계 낮춰 h3을 쓴다(같은 화면에 h2가 둘 나란히 있는 것처럼 안 보이게). */
        <Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>
          <Typography component={config.compact ? "h3" : "h2"} className="sr-only">필터</Typography>
          <FilterBarGrid>
            {showSearch ? (
              <SearchBox
                value={q}
                onSearch={commitSearch}
                placeholder={config.searchPlaceholder || "검색"}
                ariaLabel={config.searchPlaceholder || (config.title + " 검색")}
              />
            ) : null}
            {(config.filters || []).map((f) => f.type === "select" ? (
              <TextField
                key={f.key} select size="small" label={f.label}
                /* MUI는 value=""를 '아직 고르지 않음'으로 보고 라벨을 필드 안에 띄운 채
                   선택 항목을 그리지 않는다 — 필터의 기본 상태가 바로 그 빈 값이라
                   관리자 화면 필터가 전부 '빈 상자'로 보였다. 빈 값도 항목으로 그리고
                   라벨은 항상 위로 올린다. */
                SelectProps={{ displayEmpty: true }}
                InputLabelProps={{ shrink: true }}
                value={filters[f.key] || ""}
                onChange={(e) => setFilter(f.key, e.target.value)}
              >
                <MenuItem value="">{f.label}: 전체</MenuItem>
                {(f.options || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </TextField>
            ) : (f.type === "date" || f.type === "datetime-local") ? (
              // 브라우저는 date/datetime 입력의 placeholder를 무시한다 — 라벨을 항상 띄워 둬야
              // 나란히 놓인 시작/종료 두 상자를 구분할 수 있다.
              <TextField
                key={f.key} type={f.type} size="small" label={f.label}
                InputLabelProps={{ shrink: true }}
                value={filters[f.key] || ""}
                onChange={(e) => setFilter(f.key, e.target.value)}
              />
            ) : f.datalistFrom ? (
              // 이미 불러온 목록에서 뽑은 값으로 자동완성 제안을 준다 — 이름을 미리 알아야만 쓸 수
              // 있던 자유 입력 필터를 완화한다. 제안일 뿐 입력을 강제하지 않는다.
              <React.Fragment key={f.key}>
                <TextField
                  size="small" label={f.label}
                  value={filters[f.key] || ""}
                  onChange={(e) => setFilter(f.key, e.target.value)}
                  inputProps={{ list: "dl-" + f.key }}
                />
                <datalist id={"dl-" + f.key}>
                  {Array.from(new Set(f.datalistFrom(items).filter((v) => v != null && v !== ""))).map((v) => <option key={v} value={v} />)}
                </datalist>
              </React.Fragment>
            ) : (
              <TextField
                key={f.key} size="small" label={f.label}
                value={filters[f.key] || ""}
                onChange={(e) => setFilter(f.key, e.target.value)}
              />
            ))}
            {/* 필터가 여러 개 걸려 있을 때 하나씩 지우지 않고 한 번에 지운다. 예전엔 이 초기화가
             * 결과 0건일 때만 있어, 0건은 아니지만 기대와 다른 결과일 때 되돌릴 방법이 없었다. */}
            {(q || hasFilter) ? (
              <Button size="sm" onClick={() => { setQ(""); setFilters({}); setPage(1); }}>필터 지우기</Button>
            ) : null}
          </FilterBarGrid>
          {/* 저장된 뷰 — 지금 걸어 둔 필터에 이름을 붙여 두고 다시 부른다. 실제로 저장되는 것은
              위에서 주소에 되쓴 쿼리 문자열이라, 뷰를 부르는 일과 링크를 여는 일이 같은 일이 된다. */}
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: "divider" }}>
            <SavedViews
              screenKey={config.key}
              query={viewQuery}
              describe={(saved) => describeView(saved, config)}
              onApply={applyView}
            />
          </Box>
        </Card>
      ) : null}
      {/* SEM-02: 로딩·오류·빈 상태·정상 목록 네 갈래 전부를 아우르는 자리에 한 번만 둔다
          (갈래마다 넣으면 하나는 반드시 빠뜨린다). */}
      <Typography component={config.compact ? "h3" : "h2"} className="sr-only">목록</Typography>
      {query.isLoading ? (
        <Card><Skeleton lines={5} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : filtered.length === 0 ? (
        <>
        {(q || hasFilter) ? (
          <EmptyState title="검색 결과가 없습니다"
            help="조건에 맞는 항목이 없습니다. 검색어나 필터를 지워보세요."
            action={<Button variant="primary" onClick={() => { setQ(""); setFilters({}); setPage(1); }}>검색, 필터 지우기</Button>} />
        ) : (
          <EmptyState title={config.emptyTitle || "표시할 항목이 없습니다"}
            help={typeof config.emptyHelp === "function" ? config.emptyHelp(role, createBtn) : config.emptyHelp}
            // situation/prerequisite/steps/expected는 대부분 '+ 추가'·'활성화' 같은 쓰기 전용 버튼을
            // 클릭하라고 안내한다(help는 이미 canCreate로 role-branch되지만 이 네 필드는 예전엔
            // 무조건 그대로 노출돼, 그 버튼이 안 보이는 읽기 전용 역할(operator/auditor)에게도
            // '이 버튼을 누르세요' 안내가 나갔다) — 실제로 그 CTA를 볼 수 있는 role(canOnboard)에만 보여준다.
            situation={canOnboard ? config.emptySituation : undefined} prerequisite={canOnboard ? config.emptyPrerequisite : undefined}
            steps={canOnboard ? config.emptySteps : undefined} expected={canOnboard ? config.emptyExpected : undefined}
            relatedLink={config.emptyRelatedLink}
            action={createBtn} />
        )}
        {/* paginated+clientFilter 화면에서 현재 페이지가 필터로 통째로 비어도, 다른 페이지에 일치
         * 항목이 있을 수 있으므로 페이저를 남긴다(위 경고 Callout과 짝을 이룬다). */}
        {config.paginated && clientFilterDefs.length ? <Card className="c-list-card">{pager}</Card> : null}
        </>
      ) : (
        <Card className="c-list-card">
          {topPager}
          <DataTable columns={columns} rows={filtered} rowKey={(r) => r.id || (columns[0] ? r[columns[0].key] : JSON.stringify(r).slice(0, 24))} onRow={setSel} stickyHeader={config.stickyHeader} />
          {/* total 없는 응답의 '더 있음' 판정은 서버가 실제로 돌려준 원본 페이지 크기(items)로 해야
           * 한다, clientFilter로 걸러진 filtered를 쓰면 paginated+clientFilter 화면에서 필터 후 행
           * 수가 우연히 pageSize보다 적어져도 서버엔 다음 페이지가 있는데 '다음'이 조용히 꺼졌다(pager 참고). */}
          {pager}
        </Card>
      )}
      {/* 상세는 넓은(lg) 폭 — 액션 버튼이 많은 화면(러너 등)에서 좁은(md) 폭이면 푸터 버튼이 3줄로
          접혀 화면 맨 아래 뭉치가 됐다. lg 폭 + 작은 버튼으로 한두 줄에 담아 깔끔하게 만든다.

          VIS-162 — 상세 안에서 여는 수정/액션 폼(FormDrawer)이 필드 6개 이상이면 똑같이 lg(992px)
          라 상세를 픽셀 하나 안 남기고 완전히 덮었다(제목은 겹치니 남지만 방금 보던 값들은
          사라진다). sel은 그대로 두고(취소하면 이 값으로 되돌아온다 — 아래 각 onClose가 sel을
          안 건드리는 이유) 화면에서만 잠깐 숨긴다. navigate 액션(위 runAction)이 이미 하던
          setSel(null)과 같은 발상을 나머지 중첩 오버레이 셋(actionForm/subView/infoView)에도
          일관되게 적용한다. */}
      <Modal open={!!sel && !editing && !actionForm && !subView && !infoView}
        onClose={() => setSel(null)} title={sel ? detailTitle(sel, columns) : ""} size="lg"
        footer={(sel && (canEdit || visibleActions.length)) ? <>
          {canEdit ? <Button variant="primary" size="sm" disabled={busy} onClick={() => setEditing(sel)}>수정</Button> : null}
          {visibleActions.map((a, i) => <Button key={i} size="sm" variant={a.variant || "default"} disabled={busy} onClick={() => runAction(a, sel, "a" + i)}>{busyKey === ("a" + i) ? "처리 중…" : a.label}</Button>)}
        </> : null}>
        {/* 상세는 라벨/값 쌍이 20개 넘는 화면(러너·워크플로)이 있다. 좁은 화면은 한 열, 넓은
            화면은 두세 열로 접어 스크롤을 줄인다 — 4K에서 한 열로 길게 늘어놓으면 오른쪽이
            통째로 비고 눈은 위아래로만 움직인다. */}
        {sel ? (
          <Box sx={{
            display: "grid", columnGap: 4, rowGap: 0,
            gridTemplateColumns: { xs: "1fr", xxl: "repeat(2, minmax(0,1fr))", uhd: "repeat(3, minmax(0,1fr))" },
          }}>
            {mergeDetailFields(config, columns).map((c, i) => (
              <Box key={c.key || "d" + i} className="c-kv"
                sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "10rem minmax(0,1fr)" }, gap: 1,
                      py: 1.25, borderBottom: 1, borderColor: "divider", minWidth: 0 }}>
                <Typography variant="body2" color="text.secondary">{c.label}</Typography>
                <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
                  {c.render ? c.render(sel) : (sel[c.key] == null || sel[c.key] === "" ? "-" : String(sel[c.key]))}
                </Box>
              </Box>
            ))}
          </Box>
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
            const handled = config.onSaved ? config.onSaved(res, { toast, prev }) : false;
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
          footer={<div className="k-footer-row"><div className="k-footer-main"><Button variant="primary" onClick={() => setInfoView(null)}>확인</Button></div></div>}>
          <JsonBlock>{infoView.body}</JsonBlock>
        </Modal>
      ) : null}
    </div>
  );
}

