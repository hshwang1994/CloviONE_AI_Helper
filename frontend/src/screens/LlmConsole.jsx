import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import { Badge, Button, Callout, Card, ErrorState, FieldLabel, Section, SectionTitle, Skeleton, Tag, TechDetail, useToast } from "../ui/kit.jsx";
import { kindSx } from "../ui/filters.jsx";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { BASELINE_TRACKS, FORM_FIELD_CONTAINER, FORM_FIELD_GRID, pairTracks } from "../ui/density.js";

/* AI(LLM) 관리 (9-5).
 *
 * ## 이 화면이 생긴 이유
 *
 * AI 요약을 켜려면 서버의 환경변수 파일을 고치고 재시작해야 했다. 바꿀 화면이 없었다.
 *
 * ## 세 가지를 절대 하지 않는다
 *
 * 1. **설정만 보고 초록불을 그리지 않는다.** 설정이 맞아도 서버에 로그인이 안 돼 있으면
 *    아무것도 안 된다. 실제로 통하는지는 연결 테스트를 눌러야 안다.
 * 2. **연결 테스트를 여기서 기다리지 않는다.** 명령줄 도구 호출은 수십 초가 걸릴 수 있고,
 *    웹 요청에서 기다리면 그 처리 칸이 잠겨 다른 사람의 화면이 함께 느려진다. 작업 큐에
 *    맡기고 결과만 이어서 확인한다.
 * 3. **아직 안 끝난 것을 끝난 것처럼 그리지 않는다.** 큐에 있는 동안은 결과가 없다고 말한다.
 *
 * ## 빈 값은 끄기가 아니다
 *
 * 사용 여부는 세 상태다: 켬 / 끔 / 비움(서버 환경변수를 따름). 끄기와 안 정하기를 합치면
 * 이미 환경변수로 켜 둔 설치가 이 화면을 처음 여는 순간 꺼진다.
 */

// 사용 여부 세 상태. 값은 서버 레지스트리(_llm_enabled)가 받는 문자열 그대로다.
const ENABLED_CHOICES = [
  { value: "", label: "서버 환경변수를 따름" },
  { value: "on", label: "활성화" },
  { value: "off", label: "비활성화" },
];

/** 값 → 사람이 읽는 이름. 고르는 자리와 보는 자리가 같은 표를 쓴다. */
export const BACKEND_LABELS = {
  cli: "서버에 로그인된 구독 명령줄 도구",
  api: "Anthropic API",
};

const BACKEND_CHOICES = [
  { value: "", label: "서버 환경변수를 따름" },
  { value: "cli", label: "서버에 로그인된 구독 명령줄 도구" },
  { value: "api", label: "Anthropic API" },
];

// 잡 상태 -> 화면의 말. 큐에 있는 동안 "확인 중" 이라고만 말한다.
const JOB_LABEL = {
  queued: "차례를 기다리는 중",
  running: "확인하는 중",
  succeeded: "확인 완료",
  failed: "확인 완료",
  cancelled: "취소됨",
};

export function jobLabel(status) {
  return JOB_LABEL[status] || "상태를 알 수 없음";
}

/** 결과 어휘 -> 배지 색. 문구는 서버가 준 것을 그대로 쓴다. */
export function testKind(status) {
  if (status === "ok") return "ok";
  if (status === "busy" || status === "disabled") return "warn";
  return "error";
}

/* 필드 여섯 개가 세로 한 줄씩(mt:2 만 갖고 폭 제한이 없는 Box) 쌓여 있었다 — 화면 하나에
 * TextField(minWidth 200~320) 하나씩만 놓이니, 그 오른쪽으로 카드 나머지 폭이 전부 빈다
 * (사용자 지적: "AI관리 페이지... 쓸때없이 페이지만 너비만 차지하고 실제 설정하는거는
 * 한줄로 돼있고"). Ticket.jsx의 META_GRID와 같은 반응형 그리드로 옮겨 남는 폭을 여러
 * 필드가 나눠 쓰게 한다. */
/* **넓은 화면은 열을 늘려서 쓴다. 컨트롤을 늘려서 쓰지 않는다** (W5 · F-W5D-140).
 *
 * 예전 트랙은 `repeat(2, minmax(0,1fr))` 였다. 1fr 은 «남는 폭을 똑같이 나눠 가져라» 라서
 * 값의 길이와 무관하게 커진다 — 실측(`/settings?tab=ai` 1920): 좌우 각 775px, 그런데 3행에는
 * 「동시 실행 수」 하나뿐이라 오른쪽 770×95px 가 **고유 색 1개짜리 백지**였고, 값이 «1»
 * 한 글자인 칸이 775px 였다. 폭이 값에 대해 거짓말을 하면 사용자는 무엇을 넣어야 하는지
 * 잘못 짐작한다.
 *
 * 트랙을 **내용이 요구하는 폭**으로 바꾸고(auto-fill · 17~26rem), 남는 폭은 열 수로 간다.
 * 컨트롤 자체의 폭은 종류가 정한다(`CONTROL_KIND` — 탐색 줄과 같은 어휘다). 마지막 줄에
 * 남는 자리는 칠하지 않은 캔버스다(PLAN «남는 폭» ③). */
/* 「지금 적용 중인 값」의 격자 — 값 넷이 세로로 쌓이지 않고 폭에 맞춰 펴진다(넓은 화면 규칙 ②:
   남는 폭은 «더 많은 행» 으로 쓴다). */
const EFFECTIVE_GRID = {
  mt: 1,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))",
  columnGap: 3,
  rowGap: 0.25,
};

/* 필드 하나 — 라벨은 **위**이고 kit 의 `FieldLabel` 이다(D-458). 예전에는 굵은 `Typography` 로
   손수 그린 네 번째 라벨 패턴이었다. 컨트롤 폭은 종류(`kindSx`)가 정하고 도움말은 칸 폭을 쓴다. */
function Field({ label, help, children, kind }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <FieldLabel>{label}</FieldLabel>
      <Box sx={kind ? kindSx(kind) : null}>{children}</Box>
      {help ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, ...KO_WORD_BREAK }}>
          {help}
        </Typography>
      ) : null}
    </Box>
  );
}

export function LlmConsole({ embedded = false } = {}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [jobId, setJobId] = React.useState(null);
  const [draft, setDraft] = React.useState(null);

  const state = useQuery({
    queryKey: ["llm-console"],
    queryFn: () => api("/api/admin/llm"),
  });

  // 정본 캐시 키를 그대로 쓴다 — Maintenance.jsx·SettingsMain.jsx 등 같은 엔드포인트
  // (/api/admin/settings)를 읽는 다른 화면과 캐시를 공유한다. 예전엔 이 화면 전용
  // ["llm-console","settings"] 키를 따로 썼는데, 지금은 llm_* 키가 일반 설정 표에서
  // 제외돼(settingsRegistry.js DEDICATED_SCREEN_KEYS) 우연히 문제가 안 드러났을 뿐,
  // 다른 화면이 ["settings"]만 무효화하면(예: 버전 롤백) 이 화면이 열려 있는 동안은
  // 그 무효화를 받지 못하는 함정이었다(["settings"]는 ["llm-console","settings"]의
  // 접두어가 아니다).
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api("/api/admin/settings"),
  });

  // 큐에 맡긴 테스트의 결과. 끝날 때까지만 다시 묻는다 - 끝난 뒤에도 계속 물으면
  // 관리자가 이 탭을 열어 둔 동안 서버를 쉬지 않고 두드린다.
  const testJob = useQuery({
    queryKey: ["llm-console", "test", jobId],
    queryFn: () => api("/api/admin/llm/test/" + jobId),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query && query.state && query.state.data;
      return data && data.pending ? 2000 : false;
    },
  });

  // mutationFn만 갖고 onSuccess/onError는 두지 않는다 — 저장은 필드마다 이 mutation을
  // 여러 번 호출하므로(아래 saveDraft), 훅 하나에 붙인 onSuccess/onError는 필드마다
  // 그대로 다시 실행돼 중복 토스트를 낸다. 결과 처리는 saveDraft가 순서대로 모아 한 번만 한다.
  const save = useMutation({
    mutationFn: ({ key, value }) =>
      api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
  });
  // 바뀐 필드 수만큼 이 mutation을 그 자리에서 동시에(forEach + mutate) 쏘던 예전 코드는
  // 세 가지 문제가 있었다: 1) 필드마다 뜨는 중복 성공 토스트, 2) 먼저 끝난 요청의 onSuccess가
  // setDraft(null)을 불러 아직 응답을 기다리던 다른 필드의 미저장 값을 통째로 지움(그 필드가
  // 나중에 실패해도 이미 초안이 비어 복구할 수 없었다), 3) 공유 mutation의 isPending이 요청
  // 사이를 들락거려 저장 버튼의 비활성 상태를 신뢰할 수 없음. 필드를 하나씩 순서대로 저장하고,
  // 실패한 필드만 초안에 남겨 사용자가 그 값을 잃지 않게 한다.
  const [saving, setSaving] = React.useState(false);
  /* 일부 항목을 못 저장한 사실 — 초안에 남은 값과 함께 저장 줄 위에 남는다. 다시 저장하면 새로 선다. */
  const [saveFailure, setSaveFailure] = React.useState("");
  async function saveDraft() {
    const keys = Object.keys(draft || {});
    if (!keys.length) return;
    setSaving(true);
    setSaveFailure("");
    const remaining = { ...draft };
    let failCount = 0;
    for (const key of keys) {
      try {
        await save.mutateAsync({ key, value: draft[key] });
        delete remaining[key];
      } catch {
        failCount += 1;
      }
    }
    qc.invalidateQueries({ queryKey: ["llm-console"] });
    qc.invalidateQueries({ queryKey: ["settings"] });
    setSaving(false);
    setDraft(Object.keys(remaining).length ? remaining : null);
    if (failCount) {
      setSaveFailure(failCount + "개 항목을 저장하지 못했습니다. 나머지 값은 초안에 그대로 남아 있습니다. 다시 시도해 주세요.");
    } else {
      toast("저장했습니다. " + ((state.data && state.data.apply_note) || ""), "success");
    }
  }

  const startTest = useMutation({
    mutationFn: () => api("/api/admin/llm/test", { method: "POST", body: {} }),
    onSuccess: (result) => {
      setJobId(result.job_id);
      toast("연결 테스트를 작업 큐에 맡겼습니다.", "success");
    },
  });
  const testFailure = failureText([startTest, "연결 테스트를 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."]);

  /* 이 셋은 헤더까지 포함해 **화면 전체**가 아직 없다 - 회색 줄만 그리면 도착하는 순간
     제목·지표·본문이 한꺼번에 튀어 들어온다. 들어올 배치를 미리 잡아 준다(지시 20). */
  if (state.isLoading) return <Skeleton kind="page" lines={4} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.refetch} />;

  const data = state.data || {};
  const config = data.config || {};
  const limits = data.limits || {};
  const saved = {};
  const rows = (settings.data && settings.data.settings) || {};
  Object.keys(rows).forEach((key) => { saved[key] = rows[key].value; });

  const value = (key, fallback) => {
    if (draft && Object.prototype.hasOwnProperty.call(draft, key)) return draft[key];
    return saved[key] !== undefined && saved[key] !== null ? saved[key] : fallback;
  };
  const setValue = (key, next) => setDraft({ ...(draft || {}), [key]: next });
  const busy = saving || startTest.isPending;
  const result = testJob.data && testJob.data.result;

  /* 옛 주소 `/llm-console` 은 `/settings?tab=ai` 로 보내는 리다이렉트다 — 이 화면은
     언제나 설정 껍데기 안이고, 머리와 `.c-screen` 은 그 껍데기가 그린다. */
  return (
    <>
      {/* **판이 아니라 줄이다** (S18 · B10) — 지금 값은 읽는 줄이지 자기 생명주기를 가진 경계
          객체가 아니다. 제목 줄에 활성/확인 배지가 서고 설명은 제목 아래 한 줄이다. */}
      <Section
        titleAs="h2" title="지금 적용 중인 값" help={data.verified_note}
        action={
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Badge value={config.enabled ? "활성" : "비활성"} kind={config.enabled ? "ok" : "muted"} />
            {/* "아직 테스트 안 했다"는 **참고 사실**이라 경고 톤이 아니다(지시 35). */}
            {data.verified
              ? <Badge value="연결 확인됨" kind="ok" />
              : <Tag label="연결 미확인" tone="neutral" />}
          </Box>
        }
      >
        {/* UA-28: 백엔드 값이 cli/api 둘 다 아니면 서버가 안전하게 사용 여부를 강제로 끈다 —
            배지만 보면 "사용 여부를 껐다"로 읽히지만 실제 원인은 아래 백엔드 값이다. */}
        {data.backend_invalid ? (
          <Box sx={{ mb: 1.5 }}>
            <Callout tone="warn">
              백엔드 값("{config.backend}")이 올바르지 않아 사용 여부와 무관하게 비활성
              상태입니다. 아래 백엔드를 cli 또는 api 중 하나로 바로잡으세요.
            </Callout>
          </Box>
        ) : null}
        {/* 값 옆에 **어디서 온 값인지**를 붙인다. 실행 파일은 서버의 경로라 기술 정보로 내린다(지시 38). */}
        <Box data-testid="llm-effective" sx={EFFECTIVE_GRID}>
          {[
            ["백엔드", BACKEND_LABELS[config.backend] || config.backend, "llm_backend"],
            ["모델", config.model, "llm_model"],
            ["제한 시간", config.timeout_seconds + "초", "llm_timeout_seconds"],
            ["동시 실행 수", config.max_concurrency, "llm_max_concurrency"],
          ].map(([label, shown, key]) => (
            <Typography variant="body2" key={key}>
              {label}: {shown}
              {(data.sources || {})[key] === "env" ? " (서버 환경변수 또는 기본값)" : ""}
            </Typography>
          ))}
          <TechDetail sx={{ mt: 0.5, gridColumn: "1 / -1" }}>
            실행 파일: {config.executable}
            {(data.sources || {}).llm_executable === "env" ? " (서버 환경변수 또는 기본값)" : ""}
          </TechDetail>
        </Box>
      </Section>

      {/* 폼은 `/new-ticket` 의 모양이다(D-458): 왼쪽 폼 판 + 오른쪽 안내 레일 판. 예전에는 로그인
          절차가 화면 폭 판 하나를 통째로 차지했고 필드 격자는 사설 상수였다. */}
      <Box sx={pairTracks(BASELINE_TRACKS.two)}>
        <Card>
          <SectionTitle component="h2" title="설정" />
          <Box sx={FORM_FIELD_CONTAINER}>
            <Box data-testid="llm-settings-grid" sx={FORM_FIELD_GRID}>
              {/* SYS-07: value=""는 MUI Select가 "아직 아무것도 안 고름"으로 보고 라벨을 안 그린다 —
                  DataScreen 필터 select와 같은 고침(SelectProps displayEmpty:true). */}
              <Field kind="enum" label="사용 여부" help="비워 두면 서버에 설정된 기본값을 따릅니다.">
                <TextField
                  select size="small" fullWidth
                  SelectProps={{ displayEmpty: true }}
                  value={value("llm_enabled", "")}
                  onChange={(e) => setValue("llm_enabled", e.target.value)}
                  inputProps={{ "aria-label": "사용 여부" }}
                >
                  {ENABLED_CHOICES.map((c) => (
                    <MenuItem key={c.value || "inherit"} value={c.value}>{c.label}</MenuItem>
                  ))}
                </TextField>
              </Field>
              <Field kind="enum" label="백엔드" help="구독 명령줄 도구는 서버에 로그인이 필요하고, API 는 키가 필요합니다.">
                <TextField
                  select size="small" fullWidth
                  SelectProps={{ displayEmpty: true }}
                  value={value("llm_backend", "")}
                  onChange={(e) => setValue("llm_backend", e.target.value)}
                  inputProps={{ "aria-label": "백엔드" }}
                >
                  {BACKEND_CHOICES.map((c) => (
                    <MenuItem key={c.value || "inherit"} value={c.value}>{c.label}</MenuItem>
                  ))}
                </TextField>
              </Field>
              <Field kind="text" label="모델" help="비워 두면 기본 모델을 씁니다.">
                <TextField
                  size="small" fullWidth
                  value={value("llm_model", "")}
                  onChange={(e) => setValue("llm_model", e.target.value)}
                  inputProps={{ "aria-label": "모델" }}
                />
              </Field>
              <Field
                kind="number"
                label="제한 시간(초)"
                help={"0이면 기본값을 씁니다. " + (limits.min_timeout_seconds || 5) + "부터 "
                      + (limits.max_timeout_seconds || 600) + "까지 넣을 수 있습니다."}
              >
                <TextField
                  size="small" type="number" fullWidth
                  value={value("llm_timeout_seconds", 0)}
                  onChange={(e) => setValue("llm_timeout_seconds", Number(e.target.value))}
                  inputProps={{ "aria-label": "제한 시간(초)" }}
                />
              </Field>
              <Field
                kind="number"
                label="동시 실행 수"
                help={"최대 " + (limits.max_concurrency || 4)
                      + "입니다. 구독 한도를 이 서버에서 명령줄 도구를 쓰는 사람과 나눠 쓰므로 작게 잡습니다."}
              >
                <TextField
                  size="small" type="number" fullWidth
                  value={value("llm_max_concurrency", 1)}
                  onChange={(e) => setValue("llm_max_concurrency", Number(e.target.value))}
                  inputProps={{ "aria-label": "동시 실행 수" }}
                />
              </Field>
            </Box>
          </Box>

          {/* 실행 파일은 서버 경로라 평소 화면의 내용이 아니다(지시 38). 바꿀 수 있는 자리는
              남기되 접어 둔다 - 명령줄 도구 백엔드에서 장애를 볼 때만 여는 값이다. */}
          <TechDetail label="고급 설정" sx={{ mt: 2 }}>
            <Field kind="text" label="실행 파일" help="이름만 적으면 서버의 PATH 에서 찾습니다. 절대 경로도 됩니다.">
              <TextField
                size="small" fullWidth
                value={value("llm_executable", "")}
                onChange={(e) => setValue("llm_executable", e.target.value)}
                inputProps={{ "aria-label": "실행 파일" }}
              />
            </Field>
          </TechDetail>

          {/* 연결 테스트를 별도 큰 카드로 두지 않는다(지시 38) - 설정을 바꾸고 나서 확인하는
              것이 하나의 흐름이라 저장 줄에 함께 둔다. 주 동작(저장)은 폼 판의 오른쪽 끝이다. */}
          {saveFailure || testFailure ? (
            <Callout tone="danger" compact sx={{ mt: 2.5 }}>{saveFailure || testFailure}</Callout>
          ) : null}
          <Box sx={{ mt: 2.5, display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
            <Button disabled={busy} onClick={() => { setSaveFailure(""); startTest.mutate(); }}>연결 테스트</Button>
            <Box sx={{ flex: 1 }} />
            <Button disabled={busy || !draft} onClick={() => setDraft(null)}>되돌리기</Button>
            <Button variant="primary" disabled={busy || !draft} loading={saving} onClick={saveDraft}>
              저장
            </Button>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1, ...KO_WORD_BREAK }}>{data.test_mode_note}</Typography>
          {jobId && (
            <Box data-testid="llm-test-result" sx={{ mt: 1.5 }}>
              <Badge
                value={jobLabel(testJob.data && testJob.data.status)}
                kind={result ? testKind(result.status) : "muted"}
              />
              {result ? (
                <Typography variant="body2" sx={{ mt: 1 }}>{result.message}</Typography>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  아직 결과가 없습니다. 작업 큐가 이 확인을 처리하면 여기에 나옵니다.
                </Typography>
              )}
            </Box>
          )}
        </Card>

        {/* 안내 레일 — 서버 절차는 폼이 아니라 곁에 선다(`/new-ticket` 의 작성 도움과 같은 자리). */}
        <Card>
          <SectionTitle component="h2" title={data.login && data.login.title} />
          <Box component="ol" sx={{ pl: 3, m: 0 }}>
            {((data.login && data.login.steps) || []).map((step) => (
              <Typography component="li" variant="body2" key={step} sx={{ mb: 0.5, ...KO_WORD_BREAK }}>
                {step}
              </Typography>
            ))}
          </Box>
          <Box sx={{ mt: 1.5 }}>
            <Callout tone="warn">{data.login && data.login.note}</Callout>
          </Box>
        </Card>
      </Box>
    </>
  );
}

export default LlmConsole;
