import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Callout, Card, ErrorState, PageHeader, Skeleton, Tag, TechDetail, useToast } from "../ui/kit.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";

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
const SETTINGS_GRID = {
  display: "grid",
  gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", xxl: "repeat(3, minmax(0, 1fr))" },
  columnGap: 3,
};

function Field({ label, help, children }) {
  return (
    <Box sx={{ mt: 2, minWidth: 0 }}>
      <Typography sx={{ fontWeight: FONT_WEIGHT.bold }}>{label}</Typography>
      {children}
      {help && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {help}
        </Typography>
      )}
    </Box>
  );
}

// PA-RC-0017: embedded(SettingsShell.jsx의 'AI' 탭)일 땐 자체 PageHeader를 그리지 않는다 —
// SystemOps.jsx와 같은 이유.
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
  async function saveDraft() {
    const keys = Object.keys(draft || {});
    if (!keys.length) return;
    setSaving(true);
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
      toast(failCount + "개 항목을 저장하지 못했습니다. 나머지 값은 초안에 그대로 남아 있습니다. 다시 시도해 주세요.", "error");
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
    onError: (err) => toast((err && err.message) || "연결 테스트를 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

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

  return (
    <Box className="c-screen">
      {/* 저장이 언제 반영되는지는 이 화면 전체에 대한 사실이라 도움말에 둔다. 상시 안내
          상자로 두면 화면을 열 때마다 같은 문장을 다시 읽어야 한다(지시 44). */}
      {embedded ? null : <PageHeader area="AI" title="AI 관리" help={data.apply_note} />}

      <Card sx={{ mt: 2, p: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
          <Typography variant="h6" component="h2">지금 적용 중인 값</Typography>
          <Badge value={config.enabled ? "활성" : "비활성"} kind={config.enabled ? "ok" : "muted"} />
          {/* 예전에는 조건 없이 `"확인 안 함" kind="warn"` 이 박혀 있었다 — 백엔드가
              내려 주는 `verified` 를 읽지 않아서, 그 값이 참이 되는 날 화면이 거짓말을
              한다. 그리고 "아직 테스트 안 했다"는 **참고 사실**이라 경고 톤이 아니다
              (지시 35: 참고와 조치 필요를 같은 강도로 표현하지 않는다). */}
          {data.verified
            ? <Badge value="연결 확인됨" kind="ok" />
            : <Tag label="연결 미확인" tone="neutral" />}
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {data.verified_note}
        </Typography>
        {/* UA-28: 백엔드 값이 cli/api 둘 다 아니면 서버가 안전하게 사용 여부를 강제로
            끈다 — 위 배지만 보면 "사용 여부를 껐다"로 읽히지만 실제 원인은 아래 백엔드
            값이다. 켬/끔을 오가며 헛수고하지 않도록 진짜 원인을 바로 옆에서 말한다. */}
        {data.backend_invalid ? (
          <Box sx={{ mt: 1 }}>
            <Callout tone="warn">
              백엔드 값("{config.backend}")이 올바르지 않아 사용 여부와 무관하게 비활성
              상태입니다. 아래 백엔드를 cli 또는 api 중 하나로 바로잡으세요.
            </Callout>
          </Box>
        ) : null}
        {/* 값 옆에 **어디서 온 값인지**를 붙인다. 이게 없으면 "저장했는데 왜 안 바뀌지" 의
            답이 화면에 없다 - 아직 저장한 적이 없어 서버 환경변수 값이 쓰이는 중일 수 있다. */}
        {/* 실행 파일은 서버의 경로다 - AI 를 쓰는 사람이 판단할 값이 아니라 이 서버를 만든
            사람이 아는 값이다(지시 38). 지우지는 않는다: 백엔드가 명령줄 도구일 때 장애를
            보는 사람에게는 그것이 첫 단서다. 기술 정보로 내린다. */}
        <Box data-testid="llm-effective" sx={{ mt: 1, display: "grid", gap: 0.25 }}>
          {[
            // `cli`·`api` 는 설정 파일의 어휘다. 고르는 자리(아래 select)가 이름으로
            // 말하는데 보는 자리만 원문이면 한 값이 두 이름을 갖는다(지시 36).
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
          <TechDetail sx={{ mt: 0.5 }}>
            실행 파일: {config.executable}
            {(data.sources || {}).llm_executable === "env" ? " (서버 환경변수 또는 기본값)" : ""}
          </TechDetail>
        </Box>
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" component="h2">설정</Typography>

        <Box data-testid="llm-settings-grid" sx={SETTINGS_GRID}>
        {/* SYS-07: value=""는 MUI Select가 "아직 아무것도 안 고름"으로 보고, 그 값의
            MenuItem이 있어도 라벨을 안 그린다(닫힌 상자가 빈 채로 보인다) — DataScreen.jsx
            필터 select와 같은 이유·같은 고침(SelectProps displayEmpty:true). 안 그러면
            "서버 값을 따름"(정상 상태)과 "아직 안 불러옴"·"불러오기 실패"가 전부 똑같이
            빈 상자로 보인다. */}
        <Field label="사용 여부" help="비워 두면 서버에 설정된 기본값을 따릅니다.">
          <TextField
            select size="small" fullWidth sx={{ mt: 0.5 }}
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

        <Field label="백엔드" help="구독 명령줄 도구는 서버에 로그인이 필요하고, API 는 키가 필요합니다.">
          <TextField
            select size="small" fullWidth sx={{ mt: 0.5 }}
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

        <Field label="모델" help="비워 두면 기본 모델을 씁니다.">
          <TextField
            size="small" fullWidth sx={{ mt: 0.5 }}
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
            size="small" type="number" fullWidth sx={{ mt: 0.5 }}
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
            size="small" type="number" fullWidth sx={{ mt: 0.5 }}
            value={value("llm_max_concurrency", 1)}
            onChange={(e) => setValue("llm_max_concurrency", Number(e.target.value))}
            inputProps={{ "aria-label": "동시 실행 수" }}
          />
        </Field>
        </Box>

        {/* 실행 파일은 서버 경로라 평소 화면의 내용이 아니다(지시 38). 바꿀 수 있는 자리는
            남기되 접어 둔다 - 명령줄 도구 백엔드에서 장애를 볼 때만 여는 값이다. */}
        <TechDetail label="고급 설정" sx={{ mt: 2 }}>
          <Field label="실행 파일" help="이름만 적으면 서버의 PATH 에서 찾습니다. 절대 경로도 됩니다.">
            <TextField
              size="small" fullWidth sx={{ mt: 0.5, maxWidth: "28rem" }}
              value={value("llm_executable", "")}
              onChange={(e) => setValue("llm_executable", e.target.value)}
              inputProps={{ "aria-label": "실행 파일" }}
            />
          </Field>
        </TechDetail>

        {/* 연결 테스트를 별도 큰 카드로 두지 않는다(지시 38) - 설정을 바꾸고 나서 확인하는
            것이 하나의 흐름이라, 저장 버튼과 같은 줄에 둔다. */}
        <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            variant="primary"
            disabled={busy || !draft}
            onClick={saveDraft}
          >
            {saving ? "저장 중…" : "저장"}
          </Button>
          <Button disabled={busy || !draft} onClick={() => setDraft(null)}>되돌리기</Button>
          <Box sx={{ flex: 1 }} />
          <Button disabled={busy} onClick={() => startTest.mutate()}>연결 테스트</Button>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{data.test_mode_note}</Typography>
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

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
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
