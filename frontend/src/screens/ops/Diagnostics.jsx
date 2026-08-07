import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { fmtDateTime, actionKo, objKo } from "../../lib/format.js";
import { serviceLabel, daysSince, BACKUP_STALE_DAYS, DashSection, Note, StatusTile, STAT_GRID, SERVICE_GRID } from "../Dashboard.jsx";
import { PageHeader, Card, Badge, Button, Callout, StatCard, Skeleton, ErrorState, EmptyState, useToast } from "../../ui/kit.jsx";
import { Donut } from "../../ui/charts/Donut.jsx";
import { errorBuckets, healthVerdict, integrationMix, shortId, copyText, bundleStamp } from "./opsHelpers.js";
import { LogRow, LogList } from "./LogList.jsx";
import { ServiceStatusPanel } from "./ServiceStatusPanel.jsx";
import { JobQueuePanel } from "./JobQueuePanel.jsx";
import { DiagnosticActions } from "./DiagnosticActions.jsx";

/* 진단 — 진단 번들을 수집해 구조화해 보여준다(GET /api/admin/diagnostics/bundle).
 * 번들은 admin/system_admin만 조회할 수 있으므로 다른 역할에겐 수집 버튼을 감춘다.
 *
 * 이 파일은 오케스트레이터다: 수집/재시도/토스트 판단 같은 상태 관리와, 어느 섹션에도 속하지 않는
 * 작은 섹션(상단 요약 배너·외부 연동·설치처 설정·현재 리소스·백업·최근 주요 변경·원본 JSON)만
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
        if (q.data) {
          // 자동 폴링(manual=false)이 계속 실패하는 동안엔(장애 지속) 매 60초마다 같은 배너를 반복
          // 토스트하지 않는다 — 오류 스트릭 진입 순간과, 사용자가 수동으로 다시 시도한 순간에만 알린다.
          if (wasManual || !wasErrorRef.current) toast("진단 갱신에 실패했습니다, 아래 값은 이전에 수집한 자료입니다.", "error");
        } else if (wasManual) toast("진단 수집에 실패했습니다.", "error");
        // 자동 수집(manual=false)이고 이전 번들도 없으면 전체화면 ErrorState가 이미 실패를 알리므로 토스트를 겹치지 않는다.
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

  function doCopy() {
    copyText(text).then((ok) => {
      // 성공도 토스트로 알린다 — 버튼 라벨 변화만으론 스크린리더가 인지하지 못한다.
      if (ok) {
        setCopied("복사됨");
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = setTimeout(() => setCopied(""), 1500);
        toast("복사됨", "success");
      }
      else toast("복사에 실패했습니다. 아래 원본을 직접 선택해 복사하세요.", "error");
    });
  }
  function doDownload() {
    try {
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "diagnostics-" + bundleStamp(bundle) + ".json";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      // 복사와 대칭으로 성공도 알린다 — 브라우저가 조용히 내려받는 경우 확인 신호가 없었다.
      toast("진단 번들을 내려받았습니다.", "success");
    } catch (e) { toast("다운로드에 실패했습니다.", "error"); }
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
  // 번들은 actor 이름까지 해석한 '최근 주요 변경'(누가 role_change/backup.restore/rollback/approve 했나)을 담는데
  // 화면이 이걸 버려 지원팀이 원본 JSON을 뒤져야 했다, 대시보드와 같은 방식(actionKo/objKo)으로 구조화해 보여준다.
  const recentAudit = dash.recent_critical_audit || [];
  // 스펙 §14.7 'Integration Error Summary'용 integration_errors 필드는 build_diagnostic_bundle
  // (app/health/service.py)이 더 이상 응답에 내려주지 않는다, 이 화면 바로 위 '외부 연동' 섹션이
  // 이미 down/degraded 전 목록을 배지로 보여주므로, 존재하지 않는 필드를 읽어 항상 빈 배열이 되는
  // 죽은 요약 Callout은 만들지 않는다(백엔드가 이 필드를 되살리면 그때 다시 추가).

  return (
    <Box>
      <PageHeader area="운영" title="진단"
        actions={
          <DiagnosticActions manualCollecting={manualCollecting} onCollect={() => collect(true)}
            hasText={!!text} copied={copied} onCopy={doCopy} onDownload={doDownload} />
        } />
      {/* 스켈레톤은 최초 수집 때만, 재수집(refetch) 중에는 이전 번들을 그대로 두어 읽던 맥락이 사라지지 않게 한다.
          (재수집 진행은 헤더의 '수집 중…' 버튼 상태가 알려 준다.) */}
      {(q.isFetching && !bundle) ? <Card><Skeleton lines={4} /></Card>
        : (q.isError && !bundle) ? <ErrorState error={q.error} onRetry={() => collect(true)} />
        : bundle ? (
          <Box>
            {/* 재수집이 실패해도 이전 번들이 그대로 남으므로, 낡은 값을 최신처럼 보여주지 않도록 경고 배너를 띄운다. */}
            {q.isError ? <Box sx={{ mb: 3 }}><Callout tone="warn">진단 갱신에 실패했습니다, 아래 값은 {fmtDateTime(bundle.generated_at)}에 수집한 이전 자료입니다.</Callout></Box> : null}
            <Note sx={{ mt: 0, mb: 3 }}>수집 시각: {fmtDateTime(bundle.generated_at)}, 이 번들은 민감정보가 가려져 있어 지원팀에 그대로 전달해도 안전합니다.</Note>
            {/* 상태 요약(정상/주의)은 수집마다 바뀌므로 낭독되도록 라이브 영역으로 감싼다. */}
            {(() => {
              const hv = healthVerdict(comps, disk, mem, dash.cert_days_remaining, jobs24, integrations, dash);
              return (
                <Box sx={{ mb: 4 }} role="status" aria-live="polite">
                  <Callout tone={hv.tone}>
                    {hv.problems.length > 1 ? (
                      <>
                        <Box>{hv.msg}</Box>
                        <Box component="ul" sx={{ listStyle: "none", m: 0, mt: 0.75, p: 0, display: "grid", gap: 0.25 }}>
                          {hv.problems.map((p, i) => (
                            <Box component="li" key={i}
                              sx={{ display: "flex", alignItems: "baseline", gap: 0.75, color: p.tone === "danger" ? "error.main" : "warning.main" }}>
                              {/* 심각도를 색만으로 전하지 않는다(WCAG 1.4.1) — 짧은 글자 라벨을 함께 둔다. */}
                              <Box component="span" sx={{ flexShrink: 0, fontWeight: 800, fontSize: "0.75rem" }}>
                                {p.tone === "danger" ? "위험" : "주의"}
                              </Box>
                              {p.msg}
                            </Box>
                          ))}
                        </Box>
                      </>
                    ) : hv.msg}
                  </Callout>
                </Box>
              );
            })()}
            <ServiceStatusPanel disk={disk} mem={mem} certDaysRemaining={dash.cert_days_remaining} comps={comps} nav={nav} />
            <DashSection title="외부 연동">
              {/* down만이 아니라 전체 연동 상태를 보여준다, unknown도 드러나야 진단에 쓸모가 있다.
                  비활성 연동은 마지막 헬스값 대신 '비활성화'로 표기한다. */}
              {/* 서비스 이름은 대시보드와 같은 serviceLabel()로 표기해 두 화면이 같은 연동을 다르게 부르지 않게 한다.
                  활성인데 아직 헬스체크 이력이 없으면(last_health null) 무의미한 '알 수 없음' 대신 '미점검'으로 표시한다.
                  '서비스 상태'와 같은 '지금 이 순간' 스냅샷이라 바로 옆에 둔다, 이 페이지 자신이 선언한
                  '스냅샷 먼저, 이력 나중' 원칙(아래 '현재 리소스' 주석)을 이 섹션에도 실제로 지킨다. */}
              {Object.keys(integrations).length ? (
                <Box sx={{ display: "grid", gap: 2, alignItems: "start", gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1fr) minmax(0, 24rem)" } }}>
                  <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: SERVICE_GRID }}>
                    {Object.keys(integrations).map((k) => {
                      const it = integrations[k] || {};
                      // last_health는 NOT NULL이라 'unknown'으로 채워져 온다(models.py), 'it.last_health ||'
                      // 폴백은 결코 타지 않아 갓 만든/미점검 연동이 '알 수 없음'으로 새고 있었다.
                      // 'unknown'(과 만일의 빈 값)을 명시적으로 '미점검'으로 표기한다.
                      const raw = it.last_health;
                      const val = it.enabled === false ? "disabled" : (!raw || raw === "unknown") ? "미점검" : raw;
                      // 다른 화면(Dashboard.jsx의 서비스 카드)과 같은 방식으로 클릭 가능한 카드로 만든다 -
                      // 이름, 상태 배지만 보여주고 조치할 곳이 없는 막다른 카드로 남기지 않는다.
                      return (
                        <StatusTile key={k} name={serviceLabel(k)} onClick={() => nav("/integrations")}
                          ariaLabel={serviceLabel(k) + " 연동 관리로 이동"}>
                          <Badge value={val} />
                        </StatusTile>
                      );
                    })}
                  </Box>
                  {/* 연동이 열 개를 넘는 배포에서는 카드를 하나씩 세는 것보다 구성비가 빠르다. */}
                  <Card sx={{ p: 2.5 }}>
                    <Typography variant="body2" sx={{ fontWeight: 750, mb: 1.5 }}>연동 상태 구성</Typography>
                    <Donut segments={integrationMix(integrations)} unit="개" centerLabel="연동" emptyLabel="연동 정보 없음" />
                  </Card>
                </Box>
              ) : (
                // dash.integrations(위 integrations)는 Integration 테이블 전 행을 무조건 담고(app/health/
                // service.py build_dashboard), integration_errors는 그중 down/degraded만 거른 부분집합이다 -
                // 그래서 integrations가 비어 있으면 그 부분집합도 항상 비어 있다. '등록된 연동은 없지만
                // 오류만 있는' 중간 분기는 절대 일어나지 않아 제거하고, 곧장 빈 상태로 간다.
                <Card>
                  <EmptyState title="등록된 외부 연동이 없습니다" help="‘외부 연동’ 관리 화면에서 서비스를 등록하면 여기에 상태가 표시됩니다."
                    art="search"
                    relatedLink={{ href: "#/integrations", label: "외부 연동으로 이동" }} />
                </Card>
              )}
            </DashSection>
            {/* 설치처 설정. '외부 연동' 바로 아래에 둔다 - 연동이 비어 보이는 이유가 대개 여기 있다.
                값을 그리지 않고 **채웠는지 여부만** 그린다: DB id 는 설치처 식별자라 진단 화면에
                띄울 이유가 없고, 필요한 정보는 "안 채운 것이 있는가" 하나뿐이다. */}
            {tenantItems.length ? (
              <DashSection title="설치처 설정">
                <Card>
                  {tenant.configured ? (
                    <Note sx={{ mt: 0 }}>설치처 고유 설정을 모두 채웠습니다.</Note>
                  ) : (
                    <Box sx={{ mb: 2 }}>
                      <Callout tone="warn">
                        아직 설정하지 않은 항목이 {tenant.unset_count}개 있습니다. 그 기능은 비어 있는 것이 아니라 아직 연결되지 않은 상태입니다.
                      </Callout>
                    </Box>
                  )}
                  <LogList>
                    {tenantItems.map((item) => (
                      <LogRow key={item.key} when={item.state === "set" ? "설정됨" : "설정 안 됨"} what={item.label}>
                        {/* 안 채운 항목만 "그래서 무슨 일이 벌어지는가"를 붙인다. 다 채운 항목에까지
                            설명을 달면 경고가 묻힌다. 고칠 자리(환경 변수 이름)도 같이 준다. */}
                        {item.state === "set" ? null : (
                          <Typography variant="body2" color="text.secondary">
                            {item.when_unset} ({item.env_var})
                          </Typography>
                        )}
                      </LogRow>
                    ))}
                  </LogList>
                </Card>
              </DashSection>
            ) : null}
            {/* '현재 리소스'는 '시스템 리소스', '서비스 상태'와 같은 '지금 이 순간' 스냅샷이라, 이전엔
                오류, 감사 이력(시간을 두고 훑는 섹션들) 사이에 끼어 있어 위쪽 두 섹션과 한눈에 묶여
                읽히지 않았다, 같은 성격의 섹션끼리 먼저 모아 두고, 이력성 섹션은 그 아래로 둔다. */}
            {Object.keys(counts).length ? (
              <DashSection title="현재 리소스">
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: STAT_GRID }}>
                  {/* Dashboard.jsx의 동일한 인벤토리 타일과 똑같이 해당 레지스트리로 드릴다운한다 -
                      이 화면은 admin/system_admin 전용이라 세 화면 모두 항상 도달 가능하다(대시보드처럼
                      역할별 canGo 분기가 필요 없다). */}
                  <StatCard value={fmtNum(counts.active_workflows)} label="활성 워크플로" onClick={() => nav("/workflows")} />
                  <StatCard value={fmtNum(counts.active_schedules)} label="활성 스케줄" onClick={() => nav("/schedules")} />
                  <StatCard value={fmtNum(counts.runners)} label="등록된 러너" onClick={() => nav("/runners")} />
                </Box>
              </DashSection>
            ) : null}
            <JobQueuePanel jobs24={jobs24} jobErrors={jobErrors} errorDist={errorDist} nav={nav} />
            <DashSection title="백업">
              {/* 대시보드 백업 카드(Dashboard.jsx)와 동일하게 '백업 관리'로 이동할 수단을 준다 -
                  '마지막 백업: 없음'/실패를 보고도 조치할 곳이 없는 막다른 카드가 되지 않게 한다(백업 화면은 이 역할이 도달 가능). */}
              <Card sx={{ p: 2.5, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
                {/* component="div" — 안에 Badge(Chip은 <div>)가 들어간다(Dashboard.jsx 백업 카드와 같은 이유). */}
                <Typography component="div" variant="body2" sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
                  마지막 백업: {dash.last_backup_at ? fmtDateTime(dash.last_backup_at) : "없음"}
                  {dash.last_backup_status ? <Badge value={dash.last_backup_status} /> : null}
                  {/* Dashboard.jsx 백업 카드와 같은 나이 배지 — 성공 이력은 있지만 오래됐으면(계속 실패 중일 수
                      있음) 두 화면이 같은 임계값(BACKUP_STALE_DAYS)으로 같은 신호를 보이게 한다. */}
                  {(() => { const age = dash.last_backup_at ? daysSince(dash.last_backup_at) : null; return age != null && age > BACKUP_STALE_DAYS ? <Badge value={Math.floor(age) + "일 전"} kind={age > BACKUP_STALE_DAYS * 2 ? "danger" : "warn"} /> : null; })()}
                </Typography>
                <Button variant={dash.last_backup_at ? "default" : "primary"} size="sm" onClick={() => nav("/backup")}>백업 관리</Button>
              </Card>
            </DashSection>
            {/* '최근 작업 오류'(위 JobQueuePanel)와 짝인 섹션, 비었다고 화면에서 통째로 사라지면 '아직
                안 불러왔나'와 '실제로 최근 주요 변경이 없다'를 구분할 수 없다. 형제 섹션과 같은 방식으로
                항상 렌더하고 빈 목록엔 안심시키는 안내 문구를 둔다. */}
            {/* Dashboard.jsx의 동일 섹션, 바로 위 '최근 작업 오류' 섹션과 같은 방식으로 전체 감사
                로그(/audit)로 가는 딸린 링크를 준다, 이전엔 이 섹션만 더 볼 곳으로 가는 길이 없었다. */}
            <DashSection title="최근 주요 변경"
              action={<Link component="button" type="button" variant="body2" underline="hover" onClick={() => nav("/audit")}>전체 보기 →</Link>}>
              <Card>
                {recentAudit.length ? (
                  <LogList>
                    {recentAudit.map((a) => (
                      <LogRow key={a.created_at + "|" + (a.object_id || "") + "|" + a.action}
                        when={fmtDateTime(a.created_at)}
                        what={actionKo(a.action) + " (" + (a.actor || "시스템") + ")"}>
                        {/* Dashboard.jsx의 동일 섹션과 같은 방식, title 툴팁은 터치, 스크린리더에서 안
                            뜨므로, 대상 ID가 있으면 눌러서 전체 값을 복사할 수 있는 버튼으로 둔다
                            (예전엔 여기만 비인터랙티브 <span>이라 8자로 잘린 ID를 다시 알아낼 방법이 없었다). */}
                        {a.object_id ? (
                          <Link component="button" type="button" variant="body2" underline="hover" color="text.secondary" title={a.object_id}
                            aria-label={objKo(a.object_type) + " 전체 ID 복사: " + a.object_id}
                            onClick={() => copyText(a.object_id).then((ok) => toast(ok ? "ID를 복사했습니다." : "복사에 실패했습니다.", ok ? "success" : "error"))}
                            sx={{ textAlign: "left" }}>
                            {objKo(a.object_type)}, {shortId(a.object_id)}
                          </Link>
                        ) : <Typography variant="body2" color="text.secondary">{objKo(a.object_type)}</Typography>}
                      </LogRow>
                    ))}
                  </LogList>
                ) : <Note sx={{ mt: 0 }}>최근 주요 변경 이력이 없습니다.</Note>}
              </Card>
            </DashSection>
            <DashSection title="원본 자료">
              {/* 다른 모든 섹션과 같은 Card로 감싸 원시 브라우저 기본 <details> 외형(카드 없음, 테두리 없음)이
                  이 페이지에서만 미완성처럼 보이던 문제를 없앤다. */}
              <Card>
                <details>
                  <Box component="summary" sx={{ cursor: "pointer", fontWeight: 700, fontSize: "0.9375rem" }}>원본(JSON) 보기</Box>
                  <Box component="pre" aria-label="진단 번들 원본 JSON"
                    sx={{
                      m: 0, mt: 2, p: 2, whiteSpace: "pre-wrap", wordBreak: "break-word",
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "0.75rem", lineHeight: 1.5,
                      maxHeight: "60vh", overflow: "auto", bgcolor: "background.default", borderRadius: 2,
                    }}>
                    {text}
                  </Box>
                </details>
              </Card>
            </DashSection>
          </Box>
        ) : q.isFetched ? (
          // 자동 수집 전 첫 프레임에 이 안내가 번쩍이던 문제, 아직 fetch 전이면(아래 폴백) 스켈레톤을 보여
          // '수집을 눌러라'는 안내가 앱이 이미 자동으로 하는 일을 지시하지 않게 한다.
          <Card><Note sx={{ mt: 0 }}>‘진단 수집’을 눌러 현재 시스템 상태(서비스 상태, 디스크, 메모리, 인증서, 작업 오류)를 확인하세요.</Note></Card>
        ) : <Card><Skeleton lines={4} /></Card>}
    </Box>
  );
}
