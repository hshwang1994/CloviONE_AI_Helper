import React, { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import Box from "@mui/material/Box";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { PageHeader, Card, Badge, Button, DataTable, Drawer, FormDrawer, Modal, Skeleton, EmptyState, ErrorState, StatCard, Callout, useConfirm, useToast } from "../ui/kit.jsx";
import { SavedViews } from "../ui/SavedViews.jsx";
import { buildViewQuery, describeView, hashQuery, parseView, withHashQuery } from "./datascreen-view.js";

/* 설정 주도 목록 화면 — 여러 관리자 화면이 같은 읽기+상세+생성/수정/작업 패턴을 공유한다(§23).
 * 각 화면은 registry.js의 config만 다르다. 행 클릭 → 상세 모달(열 + config.detailFields 전체 필드).
 * 생성·수정은 공통 중앙 모달 폼. headerActions=폼 없는 즉시 실행/입력폼. 액션에 subList가 있으면
 * 하위 리소스(버전·실행 이력 등)를 별도 드로어로 조회한다. config.paginated면 서버 페이지네이션. */
// 401(세션 만료)은 다른 실패와 다르게 다뤄야 한다 — 재시도해도 항상 401이라 일반 오류 토스트만
// 띄우면 사용자가 뭘 해야 하는지 모른 채 막힌다(로그인 화면으로 가는 실제 동작이 없었다). 로그인
// 화면으로 실제로 이동시킨다(UserMenu.logout()과 동일한 이동 방식).
function handleApiError(e, toast) {
  if (e && e.status === 401) {
    toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error");
    // 토스트를 띄운 바로 다음 줄에서 즉시 전체 페이지 이동을 하면 브라우저가 언로드를 시작하면서
    // 방금 띄운 토스트가 사용자가 읽기도 전에 사라질 수 있다(리액트 상태 업데이트가 언마운트로
    // 잘려나감) — 짧게 지연해 안내 문구를 실제로 볼 수 있는 시간을 준다.
    window.setTimeout(() => { window.location.href = "/login"; }, 1200);
    return;
  }
  toast(e.message, "error");
}

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
  const [qInput, setQInput] = useState(initialView.q); // 입력창에 즉시 반영되는 값(타이핑 중)
  const [page, setPage] = useState(initialView.page);
  // 검색 디바운스 — 서버 검색 화면(searchable, 특히 Notion 조회처럼 요청당 최대 30초 걸리는 화면)에서
  // 매 키 입력마다 새 요청을 쏘지 않는다(예전엔 한 글자씩 칠 때마다 retry:false 요청이 겹쳐 나가
  // 응답이 뒤죽박죽 도착했다).
  //
  // **검색어가 실제로 바뀐 경우에만** 돈다. 예전엔 마운트 때도 무조건 한 번 돌아 `setPage(1)`을
  // 했는데, 이제 주소(#/audit?…&page=3)와 저장된 뷰가 페이지 번호를 복원하므로 그 한 번이
  // 복원한 페이지를 300ms 뒤에 조용히 1로 되돌린다 — 사용자는 링크를 열었는데 다른 화면을 본다.
  const lastQRef = useRef(initialView.q);
  useEffect(() => {
    if (qInput === lastQRef.current) return undefined;
    const t = setTimeout(() => { lastQRef.current = qInput; setQ(qInput); setPage(1); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);
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
    const d = {};
    (config.filters || []).forEach((f) => { if (f.value != null && f.value !== "") d[f.key] = f.value; });
    // 주소에 실린 값이 config 기본값을 이긴다 — 링크를 준 사람의 의도가 화면 기본값보다 우선이다.
    return { ...d, ...initialView.filters };
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
  const withOptionsFrom = (fields, row) => (fields || []).map((f) => f.optionsFrom ? { ...f, type: "select", options: f.optionsFrom(row) } : f);

  // f.clientFilter:true — 이 필터는 백엔드가 쿼리 파라미터로 지원하지 않는 화면(예: 워크플로 목록은
  // page/검색 파라미터가 아예 없다)에서 이미 받아 온 전체 목록을 화면에서 직접 거른다. 서버로 보내면
  // 백엔드가 조용히 무시해 '골랐는데 아무 효과 없는' 필터가 되므로, 그런 화면은 이 표시를 쓴다
  // (부서/직책의 active 필터처럼 백엔드가 실제 지원하는 필터는 clientFilter 없이 그대로 서버로 간다).
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
      const sendVal = f.type === "datetime-local" ? v + ":00+09:00" : v;
      p.push(f.key + "=" + encodeURIComponent(sendVal));
    });
    if (config.paginated) { p.push("page=" + page); if (config.pageSize) p.push("page_size=" + config.pageSize); }
    return config.endpoint + (p.length ? "?" + p.join("&") : "");
  }
  // queryKey는 서버로 실제 전송되는 필터만 반영한다 — clientFilter 값이 바뀌어도 같은 데이터를 다시
  // 받아올 필요가 없다(그 값은 아래 filtered 계산에서만 쓰인다).
  const serverFiltersKey = JSON.stringify(Object.fromEntries(serverFilterDefs.map((f) => [f.key, filters[f.key]])));
  const query = useQuery({
    queryKey: [config.key, config.searchable ? q : "", config.paginated ? page : 0, serverFiltersKey],
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
  // queryKey가 config.key로 시작하므로 refresh()의 invalidateQueries([config.key])에 함께 갱신된다.
  const summaryQuery = useQuery({
    queryKey: [config.key, "summary"],
    queryFn: () => api(config.summary.endpoint),
    enabled: !!config.summary,
    retry: false,
    // 진행 중 작업이 있는 화면(작업 큐 등)은 요약 카드도 목록과 함께 주기적으로 갱신한다
    // (예전엔 목록만 4초마다 갱신되고 카운트 카드는 마운트 시점 값에 얼어 있었다).
    refetchInterval: (config.summary && config.summary.poll) ? 4000 : false,
  });
  function setFilter(key, val) { setFilters((s) => ({ ...s, [key]: val })); setPage(1); }
  const refresh = () => qc.invalidateQueries({ queryKey: [config.key] });
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
        else toast((opts.failMsg || "작업이 실패했습니다") + (job.last_error ? ": " + job.last_error : ""), "error");
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
      announce(res, a.label.replace(/^\+\s*/, "") + " 완료");
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
    // 입력 폼 액션 — a.initial(row)이 있으면 행 데이터로 폼을 프리필한다(예: 실패한 문서 재시도).
    if (a.fields) { setActionForm({ a, row, initial: a.initial ? a.initial(row) : null }); return; }
    // confirm은 고정 문자열 또는 (row)=>문자열 함수 둘 다 지원한다(행 데이터에 따라 경고 문구를 바꿔야
    // 하는 액션용 — 예: 수동 지정된 연결을 자동 검증으로 덮어쓸 때만 추가 경고).
    const confirmMsg = typeof a.confirm === "function" ? a.confirm(row) : a.confirm;
    if (confirmMsg && !(await confirm(confirmMsg, { danger: a.variant === "danger" }))) return;
    setBusyKey(key);
    try {
      const res = await api(a.path(row), { method: a.method || "POST", body: a.body || {} });
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
    if (a.fields) { setActionForm({ a, row: null }); return; }
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
    if (confirmMsg && !(await confirm(confirmMsg, { danger: a.variant === "danger" }))) return;
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
    // 디바운스가 300ms 뒤에 page 를 1로 되돌리지 않도록 '이미 반영된 검색어'로 표시해 둔다.
    lastQRef.current = view.q;
    setQ(view.q); setQInput(view.q); setPage(view.page);
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
  const canOnboard = canCreate || !!primaryHeaderAction;
  // 페이저는 목록 카드와, clientFilter로 현재 페이지가 통째로 걸러진 빈 상태 두 곳에서 함께 쓴다
  // (paginated+clientFilter 화면에서 현재 페이지가 필터로 비어도 다른 페이지로 넘어갈 수 있게).
  const pager = config.paginated ? (
    <Box component="nav" aria-label="페이지 이동"
      sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, pt: 2, mt: 1, borderTop: 1, borderColor: "divider" }}>
      <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>이전</Button>
      <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ minWidth: "8rem", textAlign: "center" }}>
        {totalPages != null ? `${page} / ${totalPages}${total != null ? `, 총 ${total}건` : ""}` : `${page}페이지`}
      </Typography>
      <Button size="sm" disabled={totalPages != null ? page >= totalPages : items.length < pageSize} onClick={() => setPage((p) => p + 1)}>다음</Button>
    </Box>
  ) : null;

  return (
    <div className="c-screen">
      <PageHeader area={config.area} title={config.title}
        actions={hasHeaderActions ? headerActions : null} />
      {/* config.help는 고정 문자열 또는 (role)=>문자열 함수, emptyHelp와 동일한 role-aware 패턴.
       * 화면이 역할별로 다른 컨트롤을 노출할 때(예: 러너의 '수정'에서만 가능한 점검 상태 전환) 그
       * 컨트롤이 없는 역할에게까지 그 안내를 그대로 보여주지 않을 수 있게 한다. */}
      {config.help ? <Callout>{typeof config.help === "function" ? config.help(role) : config.help}</Callout> : null}
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
      {config.paginated && clientFilterDefs.length ? (
        <Callout tone="warn">선택한 일부 필터(예: 출처, 모드)는 지금 보고 있는 페이지에만 적용됩니다, 다른 페이지의 일치 항목은 ‘다음’으로 페이지를 넘겨 확인하세요.</Callout>
      ) : null}
      {/* 목록 응답에 이미 실려 오는 카운트(예: 알림의 unread)를 별도 요약 엔드포인트 없이 바로 보여준다. */}
      {config.unreadCountKey && query.data && query.data[config.unreadCountKey] != null ? (
        <Box sx={{ display: "grid", gap: 2, mb: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", lg: "repeat(4, minmax(0,1fr))", xxl: "repeat(5, minmax(0,1fr))", uhd: "repeat(6, minmax(0,1fr))" } }}>
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
            <Callout tone="warn">{"요약 통계를 불러오지 못했습니다(" + (summaryQuery.error.status === 403 ? "권한이 없습니다" : "찾을 수 없습니다") + ")."}</Callout>
          ) : (
            <Callout tone="warn">요약 통계를 불러오지 못했습니다. <Button size="sm" onClick={() => summaryQuery.refetch()}>다시 시도</Button></Callout>
          )
        ) : summaryQuery.data ? (
          <Box sx={{ display: "grid", gap: 2, mb: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", lg: "repeat(4, minmax(0,1fr))", xxl: "repeat(5, minmax(0,1fr))", uhd: "repeat(6, minmax(0,1fr))" } }}>
            {config.summary.cards(summaryQuery.data, { setFilter }).map((c, i) => <StatCard key={i} value={c.value} label={c.label} kind={c.kind} onClick={c.onClick} />)}
          </Box>
        ) : null
      ) : null}
      {showToolbar ? (
        /* 필터 바 — 감사 로그처럼 필터가 6개 넘게 붙는 화면이 있어서 한 줄에 밀어 넣지 않고
         * 자동 줄바꿈 그리드로 둔다. 화면이 넓어지면 열이 늘어 한 줄에 담긴다. */
        <Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>
          <Box sx={{
            display: "grid", gap: 1.5, alignItems: "center",
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(auto-fit, minmax(11rem, 1fr))",
              xxl: "repeat(auto-fit, minmax(13rem, 1fr))",
            },
          }}>
            {showSearch ? (
              <TextField
                type="search"
                size="small"
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder={config.searchPlaceholder || "검색"}
                inputProps={{ "aria-label": config.searchPlaceholder || (config.title + " 검색") }}
                InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
                sx={{ gridColumn: { sm: "span 2" } }}
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
              <Button size="sm" onClick={() => { setQInput(""); setQ(""); setFilters({}); setPage(1); }}>필터 지우기</Button>
            ) : null}
          </Box>
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
      {query.isLoading ? (
        <Card><Skeleton lines={5} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : filtered.length === 0 ? (
        <>
        {(q || hasFilter) ? (
          <EmptyState title="검색 결과가 없습니다"
            help="조건에 맞는 항목이 없습니다. 검색어나 필터를 지워보세요."
            action={<Button variant="primary" onClick={() => { setQInput(""); setQ(""); setFilters({}); setPage(1); }}>검색, 필터 지우기</Button>} />
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
          <DataTable columns={columns} rows={filtered} rowKey={(r) => r.id || (columns[0] ? r[columns[0].key] : JSON.stringify(r).slice(0, 24))} onRow={setSel} />
          {/* total 없는 응답의 '더 있음' 판정은 서버가 실제로 돌려준 원본 페이지 크기(items)로 해야
           * 한다, clientFilter로 걸러진 filtered를 쓰면 paginated+clientFilter 화면에서 필터 후 행
           * 수가 우연히 pageSize보다 적어져도 서버엔 다음 페이지가 있는데 '다음'이 조용히 꺼졌다(pager 참고). */}
          {pager}
        </Card>
      )}
      {/* 상세는 넓은(lg) 폭 — 액션 버튼이 많은 화면(러너 등)에서 좁은(md) 폭이면 푸터 버튼이 3줄로
          접혀 화면 맨 아래 뭉치가 됐다. lg 폭 + 작은 버튼으로 한두 줄에 담아 깔끔하게 만든다. */}
      <Drawer open={!!sel} onClose={() => setSel(null)} title={sel ? detailTitle(sel, columns) : ""} size="lg"
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
      </Drawer>

      {config.create ? (
        <FormDrawer open={creating} title={config.createLabel || (config.title + " 추가")} fields={withOptionsFrom(resolveFields(config.create.fields), null)}
          initial={createInitial || {}} submitLabel="만들기" onClose={() => { setCreating(false); setCreateInitial(null); }}
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
          // fromRow — 서버가 돌려주는 행 모양(예: {approval_policy:{required:bool}})을 폼 필드 이름
          // (예: 체크박스 하나)으로 되돌려 편집 폼을 올바른 초기값으로 연다.
          initial={editing ? (config.fromRow ? config.fromRow(editing) : editing) : {}} submitLabel="저장" onClose={() => setEditing(null)}
          onSubmit={async (body) => {
            const prev = editing;
            const apiBody = config.toApiBody ? config.toApiBody(body) : body;
            const res = await api(config.endpoint + "/" + editing.id, { method: config.editMethod || "PATCH", body: apiBody });
            setEditing(null); setSel(null); refresh();
            // 저장 후 훅(예: 스케줄 정의 변경으로 자동 비활성화됨)이 경고를 직접 알린 경우 기본 성공 토스트는 생략한다.
            const handled = config.onSaved ? config.onSaved(res, { toast, prev }) : false;
            if (!handled) announce(res, "저장했습니다.");
          }} />
      ) : null}
      {actionForm ? (
        <FormDrawer open={!!actionForm} title={actionForm.a.label}
          fields={(actionForm.a.fields || []).map((f) => f.optionsFrom ? { ...f, type: "select", options: f.optionsFrom(actionForm.row) } : f)}
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
          <div className="c-detail-json">{infoView.body}</div>
        </Modal>
      ) : null}
    </div>
  );
}

/* 하위 리소스 드로어 — 액션의 subList로 지정한 엔드포인트(버전·실행 이력 등)를 조회해 표로 보여준다.
 * subList.rowAction이 있으면 각 하위 행에 작업(예: 특정 버전으로 롤백)을 건다. */
function SubListDrawer({ view, onClose, onActed }) {
  const { a, row } = view;
  const sl = a.subList;
  const confirm = useConfirm();
  const toast = useToast();
  const auth = useAuth();
  const role = (auth && auth.data && auth.data.role) || null;
  // 하위 행 작업(롤백·재시도 등)도 role 게이트 — 백엔드 RBAC와 일치시켜 권한 없는 버튼을 숨긴다.
  const canDoRa = (ra) => !ra.roles || (role != null && ra.roles.includes(role));
  const [subPage, setSubPage] = useState(1);
  const [subFilters, setSubFilters] = useState({});
  const [subInfo, setSubInfo] = useState(null);   // 조회형 하위 행 작업(예: 버전 비교 diff) 결과 모달
  // 하위 행 작업 실행 중 — 부모 drawer의 busyKey와 동일한 패턴으로 '어느 행의 어느 액션'인지
  // key로 구분한다(예전엔 단순 boolean이라 하나를 누르면 이 하위 목록의 모든 행·모든 액션 버튼이
  // 동시에 '처리 중…'으로 바뀌었다 — localInfo처럼 네트워크 호출조차 없는 동기 작업까지 포함해).
  const [subBusyKey, setSubBusyKey] = useState(null);
  const subBusy = subBusyKey != null;
  const subRowKey = (r) => r.id != null ? r.id : (r.version != null ? r.version : JSON.stringify(r).slice(0, 24));
  const setSubFilter = (k, v) => { setSubFilters((s) => ({ ...s, [k]: v })); setSubPage(1); };
  // endpoint는 (row, {page, filters})로 호출한다(기존 subList는 2번째 인자를 무시하므로 하위호환).
  const q = useQuery({
    queryKey: ["sub", a.label, row.id, subPage, JSON.stringify(subFilters)],
    queryFn: () => api(sl.endpoint(row, { page: subPage, filters: subFilters })),
    retry: false,
  });
  const rawRows = (q.data && q.data[sl.itemsKey || "items"]) || [];
  // sl.filterRows(row, parentRow) — 백엔드가 이 하위 목록을 부모 행 기준으로 필터할 쿼리 파라미터를
  // 지원하지 않을 때(예: 템플릿 목록엔 policy_id 필터가 없다) 이미 받아 온 전체 목록을 화면에서
  // 직접 거른다(DataScreen 메인 목록의 clientFilter와 동일한 발상).
  const rows = sl.filterRows ? rawRows.filter((r) => sl.filterRows(r, row)) : rawRows;
  const total = q.data && q.data.total;
  const pageSize = (q.data && q.data.page_size) || 20;
  // 부모 목록의 페이저와 동일한 fallback — total이 없는 하위 목록 응답도(paginated:true인데 total
  // 미포함) 이번 페이지가 꽉 찼으면 '다음'을 계속 켜 둔다(DataScreen.jsx 메인 페이저와 동일한 이유).
  const totalPages = (sl.paginated && total != null) ? Math.max(1, Math.ceil(total / pageSize)) : null;
  async function act(ra, subRow, key) {
    // 조회형(로컬) 하위 행 작업 — 네트워크 호출 없이 이미 불러온 하위 행 데이터를 그대로 안내 모달로
    // 보여준다(예: 실행 이력 목록에서는 60자로 자르는 보낸 페이로드/응답 요약의 전체 텍스트 보기).
    // 동기 작업이라 busy 상태를 걸 필요가 없다(예전엔 이것도 subBusy를 켜서 다른 모든 행의 버튼까지
    // '처리 중…'으로 바꿨다 — 네트워크 호출이 전혀 없는데도).
    if (ra.localInfo) { setSubInfo({ title: ra.label, body: ra.localInfo(subRow, row) }); return; }
    // 조회형(GET) 하위 행 작업 — 목록 갱신·드로어 닫기 없이 결과를 안내 모달로 보여준다(예: 버전 비교 diff).
    if (ra.info) {
      setSubBusyKey(key);
      try { const res = await api(ra.path(subRow, row), { method: ra.method || "GET" }); setSubInfo({ title: ra.label, body: ra.info(res) }); }
      catch (e) { handleApiError(e, toast); }
      finally { setSubBusyKey(null); }
      return;
    }
    // confirm은 path/when/body와 동일하게 (하위 행, 부모 행) 두 인자를 받는다 — 부모 행 상태에 따라
    // 다른 경고를 붙여야 하는 롤백(예: 예약 워크플로 경고)을 지원한다.
    if (ra.confirm && !(await confirm(ra.confirm(subRow, row), { danger: ra.variant === "danger" }))) return;
    setSubBusyKey(key);
    try {
      const res = await api(ra.path(subRow, row), { method: ra.method || "POST", body: ra.body ? ra.body(subRow) : {} });
      // 승인 게이트가 걸리면 202 approval_pending — 성공으로 오인하지 않게 안내(예: 연동 롤백).
      if (res && (res.status === "approval_pending" || res.approval_pending)) toast("승인 요청이 접수되었습니다. 관리자 승인 후 반영됩니다.", "info");
      else toast(ra.label + " 완료", "success");
      onActed();
      // keepOpen — 이 하위 행 작업이 지금 보고 있는 바로 이 목록 안의 항목을 제자리에서 바꿀 뿐이면
      // (예: 실행 이력의 '재시도') 드로어를 닫지 않고 하위 목록만 다시 불러온다. 방금 누른 결과를
      // 보려고 재시도했는데 곧바로 드로어가 닫혀 다시 열어야 했던 것을 없앤다. 그 외(예: 버전
      // 롤백처럼 하위 목록을 벗어나는 게 자연스러운 작업)는 기존처럼 닫는다.
      if (ra.keepOpen) q.refetch(); else onClose();
    } catch (e) { handleApiError(e, toast); }
    finally { setSubBusyKey(null); }
  }
  // subList는 단일 rowAction(하위호환) 또는 rowActions 배열(롤백+비교 등 다중)을 받는다. when은 (하위행, 부모행).
  const rowActions = sl.rowActions || (sl.rowAction ? [sl.rowAction] : []);
  const cols = rowActions.length
    ? [...sl.columns, { key: "_act", label: "", render: (r) => {
        const visible = rowActions.filter((ra) => (!ra.when || ra.when(r, row)) && canDoRa(ra));
        // sl.actionHint(하위 행, 부모 행), 액션이 when()으로 숨겨졌을 때, 왜 숨겨졌는지 이유를 그
        // 빈 자리에 대신 보여준다(예: 스케줄 재시도가 부모 스케줄 비활성으로 숨겨진 경우, 예전엔
        // 버튼만 조용히 사라지고 아무 설명도 없었다).
        if (!visible.length && sl.actionHint) {
          const hint = sl.actionHint(r, row);
          if (hint) return <span>{hint}</span>;
        }
        return <>{visible.map((ra, i) => {
          const key = subRowKey(r) + ":" + ra.label;
          // 클릭한 그 버튼만 라벨이 '처리 중…'으로 바뀐다(disabled는 중복 제출 방지를 위해 전체에
          // 걸지만, 라벨은 실제로 진행 중인 액션 하나만, 부모 drawer의 busyKey와 동일한 패턴).
          return <Button key={i} size="sm" variant={ra.variant || "default"} disabled={subBusy} onClick={() => act(ra, r, key)}>{subBusyKey === key ? "처리 중…" : ra.label}</Button>;
        })}</>;
      } }]
    : sl.columns;
  return (
    <Drawer open onClose={onClose} title={sl.title || a.label}>
      {/* sl.hint, 이 하위 목록의 동작 중 암묵적 규칙(예: '비교'가 어느 두 버전을 비교하는지)이
       * 목록만 봐서는 드러나지 않을 때 짧은 안내를 붙인다(폼 필드 도움말과 동일한 스타일 재사용). */}
      {sl.hint ? <div className="k-field-help">{sl.hint}</div> : null}
      {/* 부모 DataScreen 툴바와 동일한 필터 유형(select/date/text)을 지원한다, 예전엔 select만
       * 지원해 오늘날 없는 sl.filters의 date/text 사용처가 생겨도 조용히 <select>로 잘못 렌더될
       * 뻔한 계약 불일치가 있었다(공용 목록 필터 규칙과 통일). */}
      {(sl.filters || []).length ? (
        <div className="c-toolbar-row">
          {(sl.filters).map((f) => f.type === "date" ? (
            <label key={f.key} className="c-filter-date">
              <span className="c-filter-date-label">{f.label}</span>
              <input className="c-filter" type="date"
                value={subFilters[f.key] || ""} onChange={(e) => setSubFilter(f.key, e.target.value)} aria-label={f.label} />
            </label>
          ) : f.type === "text" ? (
            <input key={f.key} className="c-filter" type="text" placeholder={f.label}
              value={subFilters[f.key] || ""} onChange={(e) => setSubFilter(f.key, e.target.value)} aria-label={f.label} />
          ) : (
            <select key={f.key} className="c-filter" value={subFilters[f.key] || ""} onChange={(e) => setSubFilter(f.key, e.target.value)} aria-label={f.label}>
              <option value="">{f.label}: 전체</option>
              {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ))}
        </div>
      ) : null}
      {/* 부모 목록의 capWarning Callout과 동일한 경고 — 이 하위 목록도 백엔드가 페이지당 최대 500건을
       * 반환한다(app/prompts/router.py). paginated가 아니면(전체를 한 번에 받는 하위 목록) 500건에
       * 닿았을 때 '더 있을 수 있음'을 알린다(안 알리면 잘린 데이터가 조용히 사라진 것처럼 보인다). */}
      {/* filterRows(클라이언트 필터)를 쓰는 하위 목록은 필터 후 행 수(rows)가 아니라 서버가 돌려준
       * 원본(rawRows)이 500건 상한에 닿았는지로 판정해야 한다 — 그렇지 않으면 필터로 몇 건만 남은
       * 경우 상한 경고가 안 떠서, 잘린 원본 때문에 누락된 항목이 있는데도 완전한 목록처럼 보였다
       * (예: 정책의 '이 정책을 쓰는 템플릿' — 발행·롤백 전 영향 범위를 이 불완전한 목록으로 오판할 수 있다). */}
      {!sl.paginated && (sl.filterRows ? rawRows.length >= 500 : rows.length >= 500) ? (
        <Callout tone="warn">{sl.filterRows
          ? "원본 목록이 500건으로 제한되어 이 필터 결과가 불완전할 수 있습니다, 일부 관련 항목이 누락됐을 수 있습니다."
          : "결과가 500건으로 제한되어 일부 항목이 보이지 않을 수 있습니다."}</Callout>
      ) : null}
      {q.isLoading ? <Skeleton lines={4} />
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : rows.length === 0 ? <EmptyState title={sl.emptyTitle || "표시할 항목이 없습니다"} help={sl.emptyHelp} />
        : <>
            <DataTable columns={cols} rows={rows} rowKey={(r) => r.id || r.version || JSON.stringify(r).slice(0, 24)} />
            {sl.paginated ? (
              <nav className="c-pager" aria-label="페이지 이동">
                <Button size="sm" disabled={subPage <= 1} onClick={() => setSubPage((p) => Math.max(1, p - 1))}>이전</Button>
                <span className="c-pager-info" aria-live="polite">
                  {totalPages != null ? `${subPage} / ${totalPages}${total != null ? `, 총 ${total}건` : ""}` : `${subPage}페이지`}
                </span>
                <Button size="sm" disabled={totalPages != null ? subPage >= totalPages : rows.length < pageSize} onClick={() => setSubPage((p) => p + 1)}>다음</Button>
              </nav>
            ) : null}
          </>}
      {subInfo ? (
        <Modal open onClose={() => setSubInfo(null)} title={subInfo.title} size="md"
          footer={<div className="k-footer-row"><div className="k-footer-main"><Button variant="primary" onClick={() => setSubInfo(null)}>확인</Button></div></div>}>
          <pre className="c-detail-json">{subInfo.body}</pre>
        </Modal>
      ) : null}
    </Drawer>
  );
}

// 상세 드로어 필드 병합 — columns와 detailFields를 그냥 이어붙이면 같은 key가 두 화면(예: 러너의
// base_url/config_version)에 모두 정의된 경우 드로어에 같은 값이 두 번 보인다. key가 겹치면
// 먼저 오는(columns) 항목만 남기고 detailFields의 중복 항목은 버린다(레지스트리 작성자가 실수로
// 같은 필드를 두 번 넣어도 드로어가 조용히 두 배로 늘어나지 않게).
function mergeDetailFields(config, columns) {
  const seen = new Set();
  const merged = [];
  [...(columns || config.columns || []), ...(config.detailFields || [])].forEach((c) => {
    if (c.key != null) {
      if (seen.has(c.key)) return;
      seen.add(c.key);
    }
    merged.push(c);
  });
  return merged;
}

function detailTitle(row, columns) {
  const first = (columns || [])[0];
  // 열의 render(예: 날짜 KST 포맷)를 존중한다 — 원시 ISO 타임스탬프가 제목으로 새어 나오지 않게.
  // 단 render가 문자열/숫자가 아닌(배지 등 JSX) 값을 주면 원시 값으로 되돌린다(제목은 문자열이어야 함).
  if (first && first.render) {
    const rendered = first.render(row);
    if (typeof rendered === "string" || typeof rendered === "number") return String(rendered);
  }
  // columnsFrom 화면은 응답이 오기 전 한 프레임 동안 열이 비어 있을 수 있다 — 그때 first가
  // undefined면 여기서 크래시가 난다(드로어가 열려 있는 상태에서만 드러나는 결함).
  if (!first) return String(row.id || "상세");
  return String(row[first.key] != null ? row[first.key] : (row.id || "상세"));
}

// 열/필드 렌더 헬퍼 — registry에서 사용.
export const badgeCol = (key, label) => ({ key, label, render: (r) => <Badge value={r[key]} /> });
export const mapCol = (key, label, map) => ({ key, label, render: (r) => map[r[key]] || (r[key] == null ? "-" : String(r[key])) });
export const dateCol = (key, label) => ({ key, label, render: (r) => fmtDateTime(r[key]) });
// 사용 여부(boolean) → 도메인 어휘 배지('사용 중'/'미사용'). 일반 badgeCol의 '예/아니오'는
// 같은 화면의 필터('사용 중'/'미사용')·체크박스 어휘와 어긋나므로 이 렌더로 통일한다.
// 미사용(active=false)은 이 화면이 관리하는 핵심 상태(새로 배정 가능 여부를 가른다)라 눈에 잘
// 안 띄는 중립(neutral) 톤 대신 주의(warn) 톤을 준다 — 훑어보다 놓치기 쉬웠다.
export const activeCol = (label) => ({ key: "active", label, render: (r) => <Badge value={r.active ? "사용 중" : "미사용"} kind={r.active ? "ok" : "warn"} /> });
// 외부 링크 열(예: 발행된 Notion 문서) — http(s) URL만 앵커로, 그 외엔 평문(CSP상 앵커는 안전).
export const linkCol = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "") return "-";
  const s = String(v);
  return /^https?:\/\//i.test(s) ? <a href={s} target="_blank" rel="noopener noreferrer">{s}</a> : s;
} });
// 긴 문자열을 목록에서 말줄임(…)으로 자르되, title 속성으로 전체 텍스트를 마우스 오버 시 볼 수
// 있게 한다(예전엔 '길면 말줄임, title 속성으로 전체 확인'이라는 주석만 있고 실제 title이 없었다).
export const truncateCol = (key, label, max) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "") return "-";
  const s = String(v);
  return s.length > max ? <span title={s}>{s.slice(0, max) + "…"}</span> : s;
} });
// 읽음 여부 — nullable 타임스탬프를 읽음/안읽음 배지로(원시 시각 노출 방지).
export const readCol = (key, label) => ({ key, label, render: (r) => <Badge value={r[key] ? "읽음" : "안읽음"} kind={r[key] ? "neutral" : "warn"} /> });
// 상세 전용: 객체/JSON 값을 보기 좋게 펼쳐 보여준다(정책 규칙·승인 payload·감사 전후 등).
export const jsonField = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  // 빈 객체/배열({}/[])도 '값 없음'으로 취급한다, 서버 기본값이 default_factory=dict인 필드(예:
  // 연동의 capabilities)는 문자열 "{}"로 JSON.stringify되어 <pre> 블록 안에 그대로 보였다(listField가
  // 이미 빈 배열을 '-'로 처리하는 것과 동일한 대우로 맞춘다).
  if (v == null || v === "" || (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0) || (Array.isArray(v) && v.length === 0)) return "-";
  const text = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  return <pre className="c-detail-json">{text}</pre>;
} });
// 상세 전용: 객체(예: 승인 요청 내용 request_payload)를 최상위 키/값 행으로 펼쳐 읽기 쉽게 보여준다.
// '내용 없이 승인 금지' 원칙을 위해, 원시 JSON 한 덩어리 대신 각 필드를 라벨로 분해한다. 중첩 객체·
// 배열은 들여쓴 JSON으로 보여준다. 서버 데이터는 JSX 텍스트로만 렌더(textContent 상당) — CSP/XSS 안전.
export const objectField = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "") return "-";
  if (typeof v !== "object") return <pre className="c-detail-json">{String(v)}</pre>;
  const entries = Array.isArray(v) ? v.map((x, i) => [String(i), x]) : Object.entries(v);
  if (!entries.length) return "-";
  return (
    <div>
      {entries.map(([k, val], i) => (
        <div className="c-kv" key={i}>
          <span className="c-kv-k">{k}</span>
          <span className="c-kv-v">{val != null && typeof val === "object"
            ? <pre className="c-detail-json">{JSON.stringify(val, null, 2)}</pre>
            : (val == null || val === "" ? "-" : String(val))}</span>
        </div>
      ))}
    </div>
  );
} });
// 상세 전용: 문자열 배열을 읽기 쉬운 목록으로(품질 문제 등). 배열이 아니면 JSON으로.
export const listField = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) return "-";
  if (Array.isArray(v)) return <ul>{v.map((x, i) => <li key={i}>{typeof x === "string" ? x : JSON.stringify(x)}</li>)}</ul>;
  return <pre className="c-detail-json">{typeof v === "string" ? v : JSON.stringify(v, null, 2)}</pre>;
} });
// 상세 전용: 문서 미리보기를 읽을 수 있게(제목·본문·행수·링크). 본문을 JSON 문자열로 뭉개지 않는다.
// 서버 데이터는 JSX 텍스트로만 렌더(textContent 상당) — innerHTML 미사용(XSS/CSP 안전).
export const previewField = (key, label) => ({ key, label, render: (r) => {
  const p = r[key];
  if (p == null || p === "") return "-";
  if (typeof p === "string") return <pre className="c-detail-json">{p}</pre>;
  const links = Array.isArray(p.notion_links) ? p.notion_links : [];
  return (
    <div>
      {p.title ? <div><strong>{String(p.title)}</strong></div> : null}
      {p.body != null && p.body !== "" ? <pre className="c-detail-json">{String(p.body)}</pre> : null}
      {p.source_row_count != null ? <div>원본 행 수: {String(p.source_row_count)}</div> : null}
      {links.length ? <div>{links.map((l, i) => { const s = String(l); return /^https?:\/\//i.test(s)
        ? <a key={i} href={s} target="_blank" rel="noopener noreferrer">{s} </a>
        : <span key={i}>{s} </span>; })}</div> : null}
    </div>
  );
} });
