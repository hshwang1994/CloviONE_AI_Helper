import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, ErrorState, PageHeader, Skeleton, useToast,
} from "../ui/kit.jsx";

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
  { value: "on", label: "켬" },
  { value: "off", label: "끔" },
];

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

function Field({ label, help, children }) {
  return (
    <Box sx={{ mt: 2 }}>
      <Typography sx={{ fontWeight: 700 }}>{label}</Typography>
      {children}
      {help && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {help}
        </Typography>
      )}
    </Box>
  );
}

export function LlmConsole() {
  const qc = useQueryClient();
  const toast = useToast();
  const [jobId, setJobId] = React.useState(null);
  const [draft, setDraft] = React.useState(null);

  const state = useQuery({
    queryKey: ["llm-console"],
    queryFn: () => api("/api/admin/llm"),
  });

  const settings = useQuery({
    queryKey: ["llm-console", "settings"],
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

  const save = useMutation({
    mutationFn: ({ key, value }) =>
      api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-console"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
      setDraft(null);
      toast("저장했습니다. " + ((state.data && state.data.apply_note) || ""), "success");
    },
    onError: (err) => toast((err && err.message) || "저장하지 못했습니다.", "error"),
  });

  const startTest = useMutation({
    mutationFn: () => api("/api/admin/llm/test", { method: "POST", body: {} }),
    onSuccess: (result) => {
      setJobId(result.job_id);
      toast("연결 테스트를 작업 큐에 맡겼습니다.", "success");
    },
    onError: (err) => toast((err && err.message) || "연결 테스트를 시작하지 못했습니다.", "error"),
  });

  if (state.isLoading) return <Skeleton lines={8} />;
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
  const busy = save.isPending || startTest.isPending;
  const result = testJob.data && testJob.data.result;

  return (
    <Box>
      <PageHeader area="연동" title="AI 관리" />

      <Callout tone="info">{data.apply_note}</Callout>

      <Card sx={{ mt: 2, p: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
          <Typography variant="h6">지금 적용 중인 값</Typography>
          <Badge value={config.enabled ? "켜짐" : "꺼짐"} kind={config.enabled ? "ok" : "muted"} />
          <Badge value="확인 안 함" kind="warn" />
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {data.verified_note}
        </Typography>
        {/* 값 옆에 **어디서 온 값인지**를 붙인다. 이게 없으면 "저장했는데 왜 안 바뀌지" 의
            답이 화면에 없다 - 아직 저장한 적이 없어 서버 환경변수 값이 쓰이는 중일 수 있다. */}
        <Box data-testid="llm-effective" sx={{ mt: 1, display: "grid", gap: 0.25 }}>
          {[
            ["백엔드", config.backend, "llm_backend"],
            ["실행 파일", config.executable, "llm_executable"],
            ["모델", config.model, "llm_model"],
            ["제한 시간", config.timeout_seconds + "초", "llm_timeout_seconds"],
            ["동시 실행 수", config.max_concurrency, "llm_max_concurrency"],
          ].map(([label, shown, key]) => (
            <Typography variant="body2" key={key}>
              {label}: {shown}
              {(data.sources || {})[key] === "env" ? " (서버 환경변수 또는 기본값)" : ""}
            </Typography>
          ))}
        </Box>
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6">설정</Typography>

        <Field label="사용 여부" help="비워 두면 서버 환경변수(LLM_ENABLED)를 따릅니다.">
          <TextField
            select size="small" sx={{ minWidth: 280, mt: 0.5 }}
            value={value("llm_enabled", "")}
            onChange={(e) => setValue("llm_enabled", e.target.value)}
            inputProps={{ "aria-label": "사용 여부" }}
          >
            {ENABLED_CHOICES.map((c) => (
              <MenuItem key={c.value || "inherit"} value={c.value}>{c.label}</MenuItem>
            ))}
          </TextField>
        </Field>

        <Field label="백엔드" help="구독 명령줄 도구는 서버에 로그인이 필요하고, API 는 키가 필요합니다.">
          <TextField
            select size="small" sx={{ minWidth: 320, mt: 0.5 }}
            value={value("llm_backend", "")}
            onChange={(e) => setValue("llm_backend", e.target.value)}
            inputProps={{ "aria-label": "백엔드" }}
          >
            {BACKEND_CHOICES.map((c) => (
              <MenuItem key={c.value || "inherit"} value={c.value}>{c.label}</MenuItem>
            ))}
          </TextField>
        </Field>

        <Field label="실행 파일" help="이름만 적으면 서버의 PATH 에서 찾습니다. 절대 경로도 됩니다.">
          <TextField
            size="small" sx={{ minWidth: 320, mt: 0.5 }}
            value={value("llm_executable", "")}
            onChange={(e) => setValue("llm_executable", e.target.value)}
            inputProps={{ "aria-label": "실행 파일" }}
          />
        </Field>

        <Field label="모델" help="비워 두면 기본 모델을 씁니다.">
          <TextField
            size="small" sx={{ minWidth: 320, mt: 0.5 }}
            value={value("llm_model", "")}
            onChange={(e) => setValue("llm_model", e.target.value)}
            inputProps={{ "aria-label": "모델" }}
          />
        </Field>

        <Field
          label="제한 시간(초)"
          help={"0이면 기본값을 씁니다. " + (limits.min_timeout_seconds || 5) + "부터 "
                + (limits.max_timeout_seconds || 600) + "까지 넣을 수 있습니다."}
        >
          <TextField
            size="small" type="number" sx={{ minWidth: 200, mt: 0.5 }}
            value={value("llm_timeout_seconds", 0)}
            onChange={(e) => setValue("llm_timeout_seconds", Number(e.target.value))}
            inputProps={{ "aria-label": "제한 시간(초)" }}
          />
        </Field>

        <Field
          label="동시 실행 수"
          help={"최대 " + (limits.max_concurrency || 4)
                + "입니다. 구독 한도를 이 서버에서 명령줄 도구를 쓰는 사람과 나눠 쓰므로 작게 잡습니다."}
        >
          <TextField
            size="small" type="number" sx={{ minWidth: 200, mt: 0.5 }}
            value={value("llm_max_concurrency", 1)}
            onChange={(e) => setValue("llm_max_concurrency", Number(e.target.value))}
            inputProps={{ "aria-label": "동시 실행 수" }}
          />
        </Field>

        <Box sx={{ mt: 2, display: "flex", gap: 1 }}>
          <Button
            variant="primary"
            disabled={busy || !draft}
            onClick={() => {
              Object.keys(draft || {}).forEach((key) => save.mutate({ key, value: draft[key] }));
            }}
          >
            저장
          </Button>
          <Button disabled={busy || !draft} onClick={() => setDraft(null)}>되돌리기</Button>
        </Box>
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>연결 테스트</Typography>
        <Typography variant="body2" color="text.secondary">{data.test_mode_note}</Typography>
        <Box sx={{ mt: 1.5 }}>
          <Button variant="primary" disabled={busy} onClick={() => startTest.mutate()}>
            연결 테스트
          </Button>
        </Box>
        {jobId && (
          <Box data-testid="llm-test-result" sx={{ mt: 2 }}>
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

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {data.login && data.login.title}
        </Typography>
        <Box component="ol" sx={{ pl: 3, m: 0 }}>
          {((data.login && data.login.steps) || []).map((step) => (
            <Typography component="li" variant="body2" key={step} sx={{ mb: 0.5 }}>
              {step}
            </Typography>
          ))}
        </Box>
        <Callout tone="warn">{data.login && data.login.note}</Callout>
      </Card>
    </Box>
  );
}

export default LlmConsole;
