import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { fmtDateTime } from "../../lib/format.js";
import { Note, StatusList, StatusTile } from "../../ui/adminKit.jsx";
import {
  PageHeader, Badge, Callout, DataTable, Section, Skeleton, ErrorState, EmptyState, Surface, TechDetail, useToast,
} from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";
import { TILE_PADDING } from "../../ui/density.js";
import {
  serviceLabel, fmtNum, errorBuckets, healthVerdict, copyText, bundleStamp,
  integrationState, upSummaryText, SERVICE_STATE_LABEL, SERVICE_STATE_KIND,
} from "./opsHelpers.js";
import { OVERFLOW } from "../../ui/columnTypes.js";
import { ServiceStatusPanel } from "./ServiceStatusPanel.jsx";
import { JobQueuePanel } from "./JobQueuePanel.jsx";
import { DiagnosticActions } from "./DiagnosticActions.jsx";

/* 진단 — 진단 번들을 수집해 구조화해 보여준다(GET /api/admin/diagnostics/bundle).
 * 번들은 admin/system_admin만 조회할 수 있으므로 다른 역할에겐 수집 버튼을 감춘다.
 *
 * 이 파일은 오케스트레이터다: 수집/재시도/토스트 판단 같은 상태 관리와, 어느 섹션에도 속하지 않는
 * 작은 섹션(상단 요약 배너·외부 연동·설치처 설정·활성 스케줄 줄·대시보드로 가는 줄·원본 JSON)만
 * 남기고, 응집도 높은 큰 덩어리(서비스 상태 카드, 작업 큐 패널, 헤더 액션)는 옆 파일로 옮겼다. */
export function Diagnostics() {
  const toast = useToast();
  const nav = useNavigate();
  // 이 컴포넌트에 도달할 수 있는 역할은 이미 App.jsx의 라우트 가드(RequireRole roles=["admin",
  // "system_admin"])로 WRITE_ROLES와 정확히 같은 집합으로 제한된다 — 그래서 예전의 canCollect 분기
  // (역할 부족 안내문·수집 버튼 숨김·'눌러서 수집하세요' 폴백)는 이 화면에 도달한 시점엔 항상 참이라
  // 실행될 수 없는 죽은 코드였다. 역할 판정은 라우트 가드 한 곳에만 둔다.
  const q = useQuery({ queryKey: ["diag"], queryFn: () => api("/api/admin/diagnostics/bundle"), enabled: false, retry: false });
  // 재수집은 조용히 실패하면 안 된다 — 실패 시 토스트로 알리고, 이전 번들이 남아 있으면
  // 그것이 '지금' 값이 아님을 분명히 한다(아래 stale 배너). 수동 수집 성공만 완료 토스트를 띄운다
  // (자동/폴링 성공까지 알리면 시끄럽다).
  // 토스트는 refetch를 부른 각 caller(수동 버튼·60초 자동 폴링)마다 개별 .then()에서 판단하지 않고,
  // 쿼리 자체의 isFetching 전이(진행중→정지) 한 곳에서만 결정한다 — 안 그러면 수동 클릭과 자동 폴링이
  // 거의 같은 순간 겹칠 때 같은 실패에 토스트가 두 번 뜬다(react-query가 동시 refetch를 내부적으로
  // 하나의 요청으로 합쳐도, 각 호출자가 각자 .then()을 달면 둘 다 알림을 띄운다).
  const manualRef = React.useRef(false);
  const wasFetchingRef = React.useRef(false);
  const wasErrorRef = React.useRef(false); // 이미 오류 스트릭 중이면 자동 폴링 실패마다 같은 stale 토스트를 반복하지 않는다
  // 60초 자동 폴링도 q.isFetching을 켜므로, 버튼 disabled/라벨을 raw q.isFetching에 물리면 매분
  // '수집 중…'으로 깜빡이며 사용자가 시작하지도 않은 배경 조회 동안 주 버튼이 비활성화됐다 —
  // Dashboard.jsx의 manualRefreshing 패턴처럼 '수동 수집'만 버튼 상태로 반영한다.
  const [manualCollecting, setManualCollecting] = React.useState(false);
  React.useEffect(() => { if (!q.isFetching) setManualCollecting(false); }, [q.isFetching]);
  function collect(manual) {
    if (manual) { manualRef.current = true; setManualCollecting(true); }
    return q.refetch();
  }
  React.useEffect(() => {
    if (wasFetchingRef.current && !q.isFetching) {
      const wasManual = manualRef.current;
      manualRef.current = false;
      if (q.isError) {
        /* 실패는 토스트로 따로 말하지 않는다 — 이전 번들이 있으면 본문 위 주의 상자(「진단 갱신에 실패했습니다」)가,
           없으면 전체 오류 상태가 이미 그 사실을 말한다. 같은 말이 두 곳에 서면 어느 쪽이 지금 상태인지
           헷갈린다(핸드오프 RULES §1). */
        wasErrorRef.current = true;
      } else {
        wasErrorRef.current = false;
        if (wasManual && q.data) toast("진단을 수집했습니다.", "success");
      }
    }
    wasFetchingRef.current = q.isFetching;
  }, [q.isFetching, q.isError, q.data]); // eslint-disable-line react-hooks/exhaustive-deps
  // 마운트 시(또는 Dashboard 경보에서 넘어올 때) 자동 수집해 빈 화면 대신 최신 번들을 바로 보여준다.
  // 재방문 시에도 다시 수집하므로 캐시된 낡은 번들을 복사/다운로드하는 일을 막는다.
  React.useEffect(() => { collect(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Dashboard.jsx와 같은 이유로(운영 현황은 실시간성이 핵심) 60초마다 자동 재수집한다 — 활성 장애를
  // 조사하는 화면을 열어둔 채 지켜봐도 수치가 저절로 갱신되지 않아 계속 수동으로 눌러야 했다.
  // enabled:false 쿼리라 refetchInterval이 스스로 도는 대신, 여기서 주기적으로 collect(false)를 부른다.
  React.useEffect(() => {
    const t = setInterval(() => collect(false), 60 * 1000);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [copied, setCopied] = React.useState("");
  const copiedTimerRef = React.useRef(null); // 연속 클릭 시 이전 타이머가 방금 세팅한 '복사됨'을 조기에 지우지 않도록
  // '복사'를 누르고 1.5초 안에 다른 화면으로 이동하면, 예약된 setCopied가 이미 언마운트된
  // 컴포넌트에 대고 실행된다 — 언마운트 시 남은 타이머를 반드시 지운다.
  React.useEffect(() => () => { if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current); }, []);
  const bundle = q.data || null;
  const text = bundle ? JSON.stringify(bundle, null, 2) : "";

  /* 복사 · 내려받기 실패 — 머리 바로 아래에 남는다(원본을 직접 선택해 복사해야 하는 사람이 읽을 수 있게).
     다음에 누르면 걷힌다. */
  const [bundleFailure, setBundleFailure] = React.useState("");
  function doCopy() {
    setBundleFailure("");
    copyText(text).then((ok) => {
      // 성공도 토스트로 알린다 — 버튼 라벨 변화만으론 스크린리더가 인지하지 못한다.
      if (ok) {
        setCopied("복사됨");
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = setTimeout(() => setCopied(""), 1500);
        toast("복사됨", "success");
      }
      else setBundleFailure("복사에 실패했습니다. 아래 원본을 직접 선택해 복사하세요.");
    });
  }
  function doDownload() {
    setBundleFailure("");
    try {
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "diagnostics-" + bundleStamp(bundle) + ".json";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      // 복사와 대칭으로 성공도 알린다 — 브라우저가 조용히 내려받는 경우 확인 신호가 없었다.
      toast("진단 번들을 내려받았습니다.", "success");
    } catch (e) { setBundleFailure("다운로드에 실패했습니다. 다시 시도해 주세요."); }
  }

  const dash = (bundle && bundle.dashboard) || {};
  const disk = dash.disk || {};
  const mem = dash.memory || {};
  const comps = dash.components || {};
  const jobs24 = dash.jobs_24h || {};
  const jobErrors = (bundle && bundle.recent_job_errors) || [];
  const errorDist = errorBuckets(jobErrors);
  // 번들은 down만이 아니라 전체 연동 상태(integrations)와 리소스 수(counts)를 담는다 -
  // 정상 연동 목록과 시스템 카운트를 숨기면 지원팀이 원본 JSON을 뒤져야 했다.
  const integrations = dash.integrations || {};
  const counts = dash.counts || {};
  // 설치처 고유 설정(app/core/tenant_config.py). 예전엔 노션 DB id 와 이메일 도메인의 기본값이
  // 개발 워크스페이스를 가리켜서, 다른 고객사에 설치해도 아무 설정 없이 '되는 것처럼' 보였다.
  // 이제 기본값이 비어 있고, **안 채운 값이 있다는 사실을 여기서 말한다** - 안 그러면 화면은
  // 그냥 빈 목록을 보여 주고 그건 '데이터가 없음'과 구별되지 않는다.
  // 서버가 이 필드를 안 주는 낡은 배포에서는 섹션 자체를 그리지 않는다(없는 것을 있는 척하지 않는다).
  const tenant = bundle && bundle.tenant_config ? bundle.tenant_config : null;
  const tenantItems = (tenant && tenant.items) || [];
  // 스펙 §14.7 'Integration Error Summary'용 integration_errors 필드는 build_diagnostic_bundle
  // (app/health/service.py)이 더 이상 응답에 내려주지 않는다, 이 화면 바로 위 '외부 연동' 섹션이
  // 이미 down/degraded 전 목록을 배지로 보여주므로, 존재하지 않는 필드를 읽어 항상 빈 배열이 되는
  // 죽은 요약 Callout은 만들지 않는다(백엔드가 이 필드를 되살리면 그때 다시 추가).

  return (
    <Box className="c-screen">
      {/* 수집 시각은 머리의 캡션(대시보드의 「N 기준」과 같은 자리)이고, 「민감정보가 가려져 있다」는
          제목 옆 `?` 다 — 예전에는 둘이 본문 첫 줄의 문장 하나였다(D-453). */}
      <PageHeader area="운영" title="진단"
        help="이 번들은 민감정보가 가려져 있어 지원팀에 그대로 전달해도 안전합니다."
        actions={
          <>
            {bundle ? (
              <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", fontVariantNumeric: "tabular-nums" }}>
                수집 시각: {fmtDateTime(bundle.generated_at)}
              </Typography>
            ) : null}
            <DiagnosticActions manualCollecting={manualCollecting} onCollect={() => collect(true)}
              hasText={!!text} copied={copied} onCopy={doCopy} onDownload={doDownload} />
          </>
        } />
      {bundleFailure ? <Callout tone="danger" compact sx={{ mb: 2 }}>{bundleFailure}</Callout> : null}
      {/* 스켈레톤은 최초 수집 때만, 재수집(refetch) 중에는 이전 번들을 그대로 두어 읽던 맥락이 사라지지 않게 한다.
          (재수집 진행은 헤더의 '수집 중…' 버튼 상태가 알려 준다.) */}
      {(q.isFetching && !bundle) ? <Skeleton kind="page" lines={4} />
        : (q.isError && !bundle) ? <ErrorState error={q.error} onRetry={() => collect(true)} />
        : bundle ? (
          <Box>
            {/* 재수집이 실패해도 이전 번들이 그대로 남으므로, 낡은 값을 최신처럼 보여주지 않도록 경고 배너를 띄운다. */}
            {q.isError ? <Box sx={{ mb: 3 }}><Callout tone="warn">진단 갱신에 실패했습니다. 아래 값은 {fmtDateTime(bundle.generated_at)}에 수집한 이전 자료입니다.</Callout></Box> : null}
            {/* 상태 요약(정상/주의)은 수집마다 바뀌므로 낭독되도록 라이브 영역으로 감싼다. */}
            {(() => {
              // 저장소도 함께 넘긴다 — 대시보드의 조치 목록이 「운영 저장소에 못 씀」을
              // 위험으로 올리는데 이 배너만 그것을 모르면 두 화면이 같은 순간에 다른
              // 말을 한다(dashboard-diagnostics-consistency 가 지키는 성질).
              const hv = healthVerdict(comps, disk, mem, dash.cert_days_remaining, jobs24, integrations, dash, dash.storage);
              /* 갈 곳이 있는 줄(작업 백로그)은 그 줄 끝에서 바로 간다 — 「대기 작업 보기」 · 「실패 작업 보기」는 작업 큐를
                 그 상태로 거른다(대시보드 경보와 같은 곳 · 같은 이름, `opsHelpers.js::JOBS_BACKLOG_LINKS`). */
              const goTo = (p) => (p.link ? (
                <Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav(p.link.to)}
                  sx={{ flexShrink: 0, marginInlineStart: 0.5 }}>
                  {p.link.label}
                </Link>
              ) : null);
              return (
                <Box sx={{ mb: 4 }} role="status" aria-live="polite">
                  <Callout tone={hv.tone}>
                    {hv.problems.length > 1 ? (
                      <>
                        <Box>{hv.msg}</Box>
                        <Box component="ul" sx={{ listStyle: "none", m: 0, mt: 0.75, p: 0, display: "grid", gap: 0.25 }}>
                          {hv.problems.map((p, i) => (
                            <Box component="li" key={i}
                              /* QAH-03(2026-08-11 하네스 실측): warning.main 글자색이
                                 4.48:1로 AA(4.5) 근소 미달이었다 — 판독 칸 배지와 같은
                                 원인이라 같은 수정(palette.{error,warning}.strong)을 쓴다. */
                              sx={{ display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: 0.75, color: p.tone === "danger" ? "error.strong" : "warning.strong" }}>
                              {/* 심각도를 색만으로 전하지 않는다(WCAG 1.4.1) — 짧은 글자 라벨을 함께 둔다. */}
                              <Box component="span" sx={{ flexShrink: 0, fontWeight: FONT_WEIGHT.extrabold, fontSize: FONT_SIZE.caption }}>
                                {p.tone === "danger" ? "위험" : "주의"}
                              </Box>
                              {p.msg}
                              {goTo(p)}
                            </Box>
                          ))}
                        </Box>
                      </>
                    ) : (
                      <>
                        {hv.msg}
                        {hv.problems.length === 1 ? goTo(hv.problems[0]) : null}
                      </>
                    )}
                  </Callout>
                </Box>
              );
            })()}
            <ServiceStatusPanel disk={disk} mem={mem} certDaysRemaining={dash.cert_days_remaining} comps={comps} nav={nav}
              pair={Object.keys(integrations).length > 0}
              aside={
            <Section titleAs="h2" title="외부 연동"
              action={Object.keys(integrations).length ? (
                <Typography variant="body2" color="text.secondary">
                  {/* PA-RC-0028: 도넛 대신 제목 옆 'N / M' 한 줄로 — 옆 카드가 이미 개별 상태를
                      말하므로, 100% 정상일 때 도넛이 화면에서 가장 큰 시각 요소가 되어 '볼 것
                      없음'에 최대 면적을 주는 문제를 없앤다(Dashboard.jsx의 같은 처방과 동일). */}
                  {upSummaryText(Object.values(integrations).map(integrationState))}
                </Typography>
              ) : null}>
              {/* down만이 아니라 전체 연동 상태를 보여준다, unknown도 드러나야 진단에 쓸모가 있다.
                  비활성 연동은 마지막 헬스값 대신 '비활성화'로 표기한다. */}
              {/* 서비스 이름은 대시보드와 같은 serviceLabel()로 표기해 두 화면이 같은 연동을 다르게 부르지 않게 한다.
                  활성인데 아직 헬스체크 이력이 없으면(last_health null) 무의미한 '알 수 없음' 대신 '미점검'으로 표시한다.
                  '서비스 상태'와 같은 '지금 이 순간' 스냅샷이라 바로 옆에 둔다, 이 페이지 자신이 선언한
                  '스냅샷 먼저, 이력 나중' 원칙을 이 섹션에도 실제로 지킨다. */}
              {Object.keys(integrations).length ? (
                <StatusList ariaLabel="외부 연동">
                  {Object.keys(integrations).map((k) => {
                    /* 상태 어휘는 `opsHelpers.js` 한 곳에서 온다(대시보드와 같은 함수) —
                       꺼 둔 것 · 한 번도 안 잰 것 · 실제로 죽은 것 셋을 그 함수가 가른다.
                       세는 규칙(위 요약)과 그리는 규칙이 갈리지 않는 유일한 방법이다. */
                    const state = integrationState(integrations[k]);
                    // 다른 화면(Dashboard.jsx의 서비스 목록)과 같은 방식으로 누를 수 있는 줄로 만든다 -
                    // 이름, 상태 배지만 보여주고 조치할 곳이 없는 막다른 줄로 남기지 않는다.
                    return (
                      /* 「외부 연동」 관리 화면은 걷었다 — 여기가 그 상태를 보는 자리다.
                         갈 곳이 없어졌으므로 누를 수 없는 줄로 둔다: 이름과 상태만 말한다.
                         조치가 필요하면 서버 쪽 연동 설정을 손봐야 하고, 그것은 이 콘솔에
                         있던 적이 없다(등록·수정 API 는 그대로 있다). */
                      <StatusTile key={k} name={serviceLabel(k)}>
                        <Badge value={SERVICE_STATE_LABEL[state]} kind={SERVICE_STATE_KIND[state]} />
                      </StatusTile>
                    );
                  })}
                </StatusList>
              ) : (
                // dash.integrations(위 integrations)는 Integration 테이블 전 행을 무조건 담고(app/health/
                // service.py build_dashboard), integration_errors는 그중 down/degraded만 거른 부분집합이다 -
                // 그래서 integrations가 비어 있으면 그 부분집합도 항상 비어 있다. '등록된 연동은 없지만
                // 오류만 있는' 중간 분기는 절대 일어나지 않아 제거하고, 곧장 빈 상태로 간다.
                <EmptyState layout="inline" title="추가된 외부 연동이 없습니다." help="이 설치는 바깥으로 나가는 호출을 쓰지 않습니다. 연동이 추가되면 여기에 상태가 표시됩니다." />
              )}
            </Section>
              } />
            {/* 설치처 설정. '외부 연동' 바로 아래에 둔다 - 연동이 비어 보이는 이유가 대개 여기 있다.
                값을 그리지 않고 **채웠는지 여부만** 그린다: DB id 는 설치처 식별자라 진단 화면에
                띄울 이유가 없고, 필요한 정보는 "안 채운 것이 있는가" 하나뿐이다. */}
            {tenantItems.length ? (
              <Section titleAs="h2" title="설치처 설정" rule>
                  {tenant.configured ? (
                    <Note sx={{ mt: 0 }}>설치처 고유 설정을 모두 채웠습니다.</Note>
                  ) : (
                    <Box sx={{ mb: 2 }}>
                      <Callout tone="info">
                        아직 설정하지 않은 항목이 {tenant.unset_count}개 있습니다. 그 기능은 비어 있는 것이 아니라 아직 연결되지 않은 상태입니다.
                      </Callout>
                    </Box>
                  )}
                  {/* 채웠는지 · 무엇을 · 안 채우면 무슨 일이 벌어지는지 세 열은 표다(계획 B-5). 상태는 표 안이라
                      점 + 낱말로 선다(글자가 남는다 — 색만으로 구분하지 않는다). */}
                  {/* 목록 판 — 판이 곧 표 상자다(조합 계약 C-3). 점검표라 발에 받은 건수를 세우지 않는다. */}
                  <DataTable
                    placement="surface"
                    list={false}
                    columns={[
                      { key: "state", label: "상태", type: "status",
                        render: (item) => <Badge value={item.state === "set" ? "설정됨" : "설정 안 됨"} kind={item.state === "set" ? "ok" : "warn"} /> },
                      /* 설정 이름은 짧다(「계정 생성 허용 도메인」) — 폭을 적어 남는 폭을 산문에 넘긴다(D-501). 폭을 안 적은 제목은
                         남는 폭을 다 먹어 1,300px 칸에 열한 글자가 서고, 옆의 「설정하지 않으면」은 스무 글자에서 잘렸다. 설정 표의
                         「항목명」과 같은 폭이다(`settings/SettingsMain.jsx`). */
                      { key: "label", label: "설정", type: "title", width: "13rem" },
                      /* 안 채운 항목만 "그래서 무슨 일이 벌어지는가"를 붙인다. 다 채운 항목에까지 설명을 달면
                         경고가 묻힌다. 고칠 자리(환경 변수 이름)도 같이 준다. 읽는 산문이라 남는 폭을 갖는다(`grow`). */
                      { key: "when_unset", label: "설정하지 않으면", type: "text", grow: true, overflow: OVERFLOW.word,
                        render: (item) => (item.state === "set" ? "" : `${item.when_unset} (${item.env_var})`) },
                    ]}
                    rows={tenantItems}
                    rowKey={(item) => item.key}
                  />
              </Section>
            ) : null}
            <JobQueuePanel jobs24={jobs24} jobErrors={jobErrors} errorDist={errorDist} nav={nav} />
            {/* 활성 스케줄 수는 **줄 하나**다(D-501). 여기 「현재 리소스」 구획이 있었고, 값 하나를 든 전폭 판(「1 활성 스케줄」)이
                1,600px 를 가로질렀다 — 누를 곳도 경보도 아닌 값 하나는 판을 세울 이유가 없다. 바로 아래 「대시보드에서 보기」와
                같은 주석 줄(수 한 문장 + 가는 길)로 그 줄 위에 선다. 가는 길은 실행 일정 화면이고, 이 화면에 들어오는 역할(운영자
                이상)은 언제나 그곳에 닿는다. 번들이 이 수를 안 주는 배포에서는 줄도 없다. */}
            {counts.active_schedules != null ? (
              <Note sx={{ mt: 0, mb: 0.75 }}>
                {`지금 켜져 있는 스케줄은 ${fmtNum(counts.active_schedules)}개입니다.`}{" "}
                <Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/schedules")}>
                  스케줄에서 보기 →
                </Link>
              </Note>
            ) : null}
            {/* PA-RC-0028: '백업'과 '최근 주요 변경'을 이 화면 본문에서 뺐다 — /dashboard가
                이미 상시(30초 폴링)로 같은 두 섹션을 보여주고 있어(build_diagnostic_bundle이
                build_dashboard()를 그대로 품는 구조, 데이터는 번들에 그대로 남는다·JSON
                다운로드도 불변) 본문 79줄 중 54줄이 두 화면에서 문자 그대로 겹쳤다. 대시보드로
                가는 링크 한 줄만 남긴다 — 진단의 나머지(시스템 리소스·설치처 설정·최근 작업
                오류·원본 JSON)는 대시보드가 안 답하는 것들이라 그대로 둔다. */}
            {/* 문장 하나와 링크 하나는 판이 아니라 줄이다 — 예전에는 이것이 전폭 흰 판이었다. */}
            <Note sx={{ mt: 0, mb: 3 }}>
              백업 상태와 최근 주요 변경은 대시보드에서 항상 확인할 수 있습니다.{" "}
              <Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/dashboard")}>
                대시보드에서 보기 →
              </Link>
            </Note>
            <Section titleAs="h2" title="원본 자료">
              {/* 기술 정보는 공용 `TechDetail`(메일 발송의 오류 원문과 같은 접기)이고 원문은 함몰면
                  위에 선다 — 예전에는 맨 `<details>` 를 판으로 감싸 이 화면만 다른 접기를 가졌다. */}
              <TechDetail label="원본(JSON) 보기">
                <Surface tone="sunken" component="pre" aria-label="진단 번들 원본 JSON"
                  sx={{
                    m: 0, mt: 1, p: TILE_PADDING, whiteSpace: "pre-wrap", wordBreak: "break-word",
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: FONT_SIZE.caption, lineHeight: 1.5,
                    maxHeight: "60vh", overflow: "auto",
                  }}>
                  {text}
                </Surface>
              </TechDetail>
            </Section>
          </Box>
        ) : q.isFetched ? (
          // 자동 수집 전 첫 프레임에 이 안내가 번쩍이던 문제, 아직 fetch 전이면(아래 폴백) 스켈레톤을 보여
          // '수집을 눌러라'는 안내가 앱이 이미 자동으로 하는 일을 지시하지 않게 한다.
          <EmptyState layout="page" art="settings" title="아직 수집한 진단이 없습니다"
            help="‘진단 수집’을 눌러 현재 시스템 상태(서비스 상태, 디스크, 메모리, 인증서, 작업 오류)를 확인하세요." />
        ) : <Skeleton kind="page" lines={4} />}
    </Box>
  );
}
