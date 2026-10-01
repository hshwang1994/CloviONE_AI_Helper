import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { fmtDateTime } from "../../lib/format.js";
import { useInstantSave } from "../../lib/useInstantSave.js";
import {
  ActionFooter, Badge, Button, Callout, Card, ErrorState, Field, FieldRow, FormSection, Section, Skeleton, useToast,
} from "../../ui/kit.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { SecretField } from "../../ui/SecretField.jsx";
import { ChatGptAccount } from "./ChatGptConnect.jsx";
import { KO_WORD_BREAK } from "../../ui/theme.js";

/* AI 설정 (계획 3.13 · 3.14, D-515) — `/settings?tab=ai`, 시스템 관리자만.
 *
 * 흐름 하나다: 연결 상태 → 제공자 → 인증 → 모델 → 실행 옵션 → AI 기능 → 저장 → 연결 확인.
 * 예전 화면(명령줄 도구 로그인 안내 레일과 「비우면 기본 모델」)은 없다 — 서버에 로그인된 구독 명령줄 도구는
 * 공식 정책상 더 쓸 수 없고, 모델을 비우면 AI 는 꺼진다(제품이 모델을 대신 고르지 않는다).
 *
 * ## 세 가지를 하지 않는다
 *
 * 1. 설정만 보고 「정상」을 그리지 않는다. 정상은 실제로 성공한 호출이나 연결 확인 뒤에만 선다(서버의 연결 상태).
 * 2. 연결 확인을 이 화면에서 기다리지 않는다. 작업 큐에 맡기고 결과를 이어서 묻는다.
 * 3. 제공자가 지원하지 않는 인증 방식을 그리지 않는다. 고를 수 있는 방식은 서버의 표가 준다(`providers`).
 *
 * 인증 칸은 두 모양이다. API 키는 비밀 칸(`SecretField`)이고, 계정 연결(OpenAI 의 ChatGPT 계정, D-516)은 로그인
 * 단추와 연결 도우미다(`ChatGptConnect.jsx`) - 사람이 토큰을 붙여 넣는 칸은 없다.
 */

const STATE_KIND = {
  unconfigured: "muted", unverified: "info", ok: "ok", degraded: "warn", reauth_required: "error", error: "error",
};

const VERIFY_POLL_MS = 1500;

/* 연결 확인 — POST 로 잡을 넣고 끝날 때까지 결과를 묻는다. 메일 화면의 연결 확인과 같은 모양이다. */
function useAiVerify({ onDone }) {
  const [jobId, setJobId] = React.useState(null);
  const start = useMutation({
    mutationFn: () => api("/api/admin/ai/verify", { method: "POST" }),
    onSuccess: (res) => setJobId(res && res.job_id),
  });
  const poll = useQuery({
    queryKey: ["ai-verify", jobId],
    queryFn: () => api("/api/admin/ai/verify/" + jobId),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && !q.state.data.pending ? false : VERIFY_POLL_MS),
  });
  const done = poll.data && !poll.data.pending ? poll.data : null;
  const announced = React.useRef(null);
  React.useEffect(() => {
    if (!done || announced.current === done.job_id) return;
    announced.current = done.job_id;
    onDone(done);
  }, [done, onDone]);
  return { start, waiting: start.isPending || (!!jobId && !done), result: done && done.result };
}

export function AiSettings() {
  const qc = useQueryClient();
  const toast = useToast();
  const query = useQuery({ queryKey: ["ai-admin"], queryFn: () => api("/api/admin/ai") });
  const [draft, setDraft] = React.useState(null);
  const [models, setModels] = React.useState(null);

  const save = useMutation({
    mutationFn: (body) => api("/api/admin/ai/config", { method: "PUT", body }),
    onSuccess: (data) => {
      qc.setQueryData(["ai-admin"], data);
      setDraft(null);
      toast("AI 설정을 저장했습니다.", "success");
    },
  });
  /* 기능 스위치 셋은 누르는 즉시 저장된다 — 누른 순간 반영하고 요청은 한 줄로 보낸다(D-525). 저장 중이라고 다른
     기능 스위치를 끄지 않는다. */
  const feature = useInstantSave({
    queryKey: ["ai-admin"],
    mutationFn: ({ key, value }) => api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    apply: (old, { key, value }) => ({ ...old, features: { ...(old.features || {}), [key]: value } }),
    onSaved: () => toast("AI 기능 설정을 저장했습니다.", "success"),
    onError: (e) => toast(e.message, "error"),
  });
  const loadModels = useMutation({
    mutationFn: ({ provider, auth_method }) => api(
      "/api/admin/ai/models?provider=" + encodeURIComponent(provider) + "&auth_method=" + encodeURIComponent(auth_method),
    ),
    onSuccess: (res) => setModels((res && res.models) || []),
  });
  const verify = useAiVerify({
    onDone: React.useCallback((r) => {
      qc.invalidateQueries({ queryKey: ["ai-admin"] });
      if (r && r.result && r.result.ok) toast("AI 제공자 연결을 확인했습니다.", "success");
    }, [qc, toast]),
  });

  if (query.isLoading) return <Skeleton lines={8} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;

  const data = query.data || {};
  const saved = data.config || {};
  const form = { ...saved, ...(draft || {}) };
  const set = (key, value) => setDraft((d) => ({ ...(d || {}), [key]: value }));
  const providers = data.providers || [];
  const provider = providers.find((p) => p.key === form.provider) || null;
  const method = provider
    ? (provider.auth_methods.find((m) => m.key === form.auth_method) || (provider.auth_methods.length === 1 ? provider.auth_methods[0] : null))
    : null;
  const state = data.state || {};
  const limits = data.limits || {};
  const [minTimeout, maxTimeout] = limits.timeout_seconds || [5, 300];
  const [, maxSlots] = limits.max_concurrency || [1, 8];
  const features = data.features || {};
  const dirty = !!draft && Object.keys(draft).some((k) => draft[k] !== saved[k]);
  const saveFailure = failureText([save, "설정을 저장하지 못했습니다."]);
  const verifyFailure = failureText([verify.start, "연결 확인을 시작하지 못했습니다."])
    || (verify.result && !verify.result.ok ? "연결 확인에 실패했습니다. " + (verify.result.message || "") : null);
  const modelFailure = failureText([loadModels, "모델 목록을 받지 못했습니다."]);

  function saveDraft() {
    const body = {};
    Object.keys(draft || {}).forEach((k) => { if (draft[k] !== saved[k]) body[k] = draft[k]; });
    if (provider && method && body.provider !== undefined) body.auth_method = method.key;
    save.mutate(body);
  }

  return (
    <>
      {/* 연결 상태 — 「값이 있다」와 「동작한다」를 가른 여섯 상태 중 하나다(서버가 판정한다). */}
      <Box data-testid="ai-state">
      <Section
        titleAs="h2" title="연결 상태"
        action={<Badge value={state.label || "알 수 없음"} kind={STATE_KIND[state.state] || "muted"} />}
      >
        <Typography variant="body2" sx={KO_WORD_BREAK}>{state.message}</Typography>
        {state.problems && state.problems.length ? (
          <Box component="ul" sx={{ m: 0, mt: 1, pl: 3 }}>
            {state.problems.map((p) => <Typography component="li" variant="body2" key={p}>{p}</Typography>)}
          </Box>
        ) : null}
        {state.reason ? <Callout tone="warn" compact>{state.reason}</Callout> : null}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          {state.last_success_at ? `마지막 성공은 ${fmtDateTime(state.last_success_at)}입니다. ` : "아직 성공한 호출이 없습니다. "}
          {state.checked_at ? `마지막 연결 확인은 ${fmtDateTime(state.checked_at)}입니다.` : ""}
        </Typography>
        {data.proxy ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }} data-testid="ai-proxy">
            {`프록시 ${data.proxy}를 거쳐 제공자에 연결합니다.`}
          </Typography>
        ) : null}
      </Section>
      </Box>

      {/* 설정은 한 판 위의 구획 넷이다 - 구획은 머리와 선으로만 나뉘고 카드를 두르지 않는다(F7 카드 규율, D-527). */}
      <Card stack data-testid="ai-settings-form">
        <FormSection titleAs="h2" title="제공자와 인증">
          <FieldRow>
            <Field
              label="AI 제공자" span={{ wide: 6, mid: 1 }}
              help={provider ? provider.help : "답변을 만들 AI 제공자를 고릅니다."}
            >
              <TextField
                select size="small" fullWidth SelectProps={{ displayEmpty: true }}
                value={form.provider || ""}
                onChange={(e) => { set("provider", e.target.value); setModels(null); }}
                inputProps={{ "aria-label": "AI 제공자" }}
              >
                <MenuItem value="">고르지 않음</MenuItem>
                {providers.map((p) => <MenuItem key={p.key} value={p.key}>{p.label}</MenuItem>)}
              </TextField>
            </Field>
            {provider && provider.auth_methods.length > 1 ? (
              <Field label="인증 방식" span={{ wide: 6, mid: 1 }}>
                <TextField
                  select size="small" fullWidth
                  value={(method && method.key) || ""}
                  onChange={(e) => set("auth_method", e.target.value)}
                  inputProps={{ "aria-label": "인증 방식" }}
                >
                  {provider.auth_methods.map((m) => <MenuItem key={m.key} value={m.key}>{m.label}</MenuItem>)}
                </TextField>
              </Field>
            ) : null}
          </FieldRow>
          {method && method.account ? (
            <ChatGptAccount
              chatgpt={data.chatgpt} state={state} tokenSettings={data.token_settings}
              onChanged={() => qc.invalidateQueries({ queryKey: ["ai-admin"] })}
            />
          ) : method ? (
            /* 키는 저장하면 되읽지 않는다. 끝 네 글자로 어느 키인지만 알아본다. 키를 새로 넣으면 연결 상태가
               「확인 전」으로 돌아간다(서버가 설정 지문으로 판정한다). */
            <SecretField
              slot={method.secret_slot} label={method.label}
              help={[method.help, method.secret_hint ? `저장된 키의 ${method.secret_hint}입니다.` : null].filter(Boolean).join(" ")}
              onChanged={() => qc.invalidateQueries({ queryKey: ["ai-admin"] })}
            />
          ) : null}
        </FormSection>

        <FormSection titleAs="h2" title="모델">
          {/* 「모델 불러오기」는 입력과 같은 줄의 동작 칸이다 - 윗선과 높이가 입력과 같다(D-527). */}
          <Field
            label="모델" htmlFor={models && models.length ? undefined : "ai-model"} width="xl"
            help="제품이 모델을 대신 고르지 않습니다. 비워 두면 AI 가 꺼져 있습니다."
            action={(
              <Button
                disabled={!method || !method.secret_set} loading={loadModels.isPending}
                onClick={() => loadModels.mutate({ provider: provider.key, auth_method: method.key })}
              >
                모델 불러오기
              </Button>
            )}
          >
            {models && models.length ? (
              <TextField
                select size="small" fullWidth SelectProps={{ displayEmpty: true }}
                value={form.model || ""}
                onChange={(e) => set("model", e.target.value)}
                inputProps={{ "aria-label": "모델" }}
              >
                <MenuItem value="">고르지 않음</MenuItem>
                {models.map((m) => <MenuItem key={m.id} value={m.id}>{m.label}</MenuItem>)}
              </TextField>
            ) : (
              <TextField
                id="ai-model" size="small" fullWidth value={form.model || ""}
                onChange={(e) => set("model", e.target.value)}
                inputProps={{ "aria-label": "모델" }}
              />
            )}
          </Field>
          {modelFailure ? <Callout tone="warn" compact>{modelFailure}</Callout> : null}
        </FormSection>

        <FormSection titleAs="h2" title="실행 옵션">
          <FieldRow>
            <Field
              label="제한 시간(초)" htmlFor="ai-timeout" span={{ wide: 4, mid: 1 }}
              help={`호출 하나를 기다리는 시간입니다. ${minTimeout}초에서 ${maxTimeout}초 사이로 정합니다.`}
            >
              <TextField
                id="ai-timeout" size="small" type="number" fullWidth value={form.timeout_seconds ?? ""}
                onChange={(e) => set("timeout_seconds", Number(e.target.value))}
                inputProps={{ "aria-label": "제한 시간(초)", min: minTimeout, max: maxTimeout }}
              />
            </Field>
            <Field
              label="동시 실행 수" htmlFor="ai-concurrency" span={{ wide: 4, mid: 1 }}
              help={`웹과 워커가 함께 나눠 쓰는 슬롯 수입니다. 최대 ${maxSlots}입니다.`}
            >
              <TextField
                id="ai-concurrency" size="small" type="number" fullWidth value={form.max_concurrency ?? ""}
                onChange={(e) => set("max_concurrency", Number(e.target.value))}
                inputProps={{ "aria-label": "동시 실행 수", min: 1, max: maxSlots }}
              />
            </Field>
          </FieldRow>
        </FormSection>

        <FormSection titleAs="h2" title="AI 기능">
          {/* 설정 줄은 괘선 목록이다 - 구획 머리 선 바로 아래 첫 줄은 윗선을 두 번 긋지 않는다. */}
          <Box sx={{ "& > .k-settingrow:first-of-type": { borderTop: 0, pt: 0 } }}>
            <SettingRow
              compact label="AI 답변 생성" description="켜면 아래 기능들이 이 연결로 답을 만듭니다. 저장을 눌러야 적용됩니다."
              controlId="ai-generation"
              action={(
                <Switch
                  id="ai-generation"
                  checked={!!form.generation_enabled}
                  onChange={() => set("generation_enabled", !form.generation_enabled)}
                  slotProps={{ input: { "aria-label": "AI 답변 생성" } }}
                />
              )}
            />
            {[
              ["chat_enabled", "AI 채팅", "끄면 채팅 화면과 대화 API 가 닫힙니다."],
              ["assistant_narrative_enabled", "홈 AI 문장 요약", "켜면 홈과 도우미가 숫자 옆에 한두 문장 요약을 붙입니다."],
              ["game_ai_enabled", "게임 퀴즈 AI", "켜면 놀이 화면에서 AI 가 퀴즈 초안을 만듭니다."],
            ].map(([key, label, description]) => (
              <SettingRow
                key={key} compact label={label} description={description}
                controlId={`ai-feature-${key}`}
                action={(
                  <Switch
                    id={`ai-feature-${key}`}
                    checked={!!features[key]}
                    onChange={() => feature.mutate({ key, value: !features[key] })}
                    slotProps={{ input: { "aria-label": label } }}
                  />
                )}
              />
            ))}
          </Box>
        </FormSection>

        {saveFailure || verifyFailure ? (
          <Callout tone="danger" compact>{saveFailure || verifyFailure}</Callout>
        ) : null}
        {/* 저장이 주 동작이고 연결 확인은 설정을 바꾼 뒤 이어서 하는 보조 동작이다 - 같은 발에 선다. */}
        <ActionFooter
          placement="card"
          extra={(
            <Button loading={verify.waiting} disabled={dirty} onClick={() => verify.start.mutate()}>
              연결 확인
            </Button>
          )}
        >
          <Button disabled={!dirty || save.isPending} onClick={() => setDraft(null)}>되돌리기</Button>
          <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={saveDraft}>저장</Button>
        </ActionFooter>
      </Card>
    </>
  );
}

export default AiSettings;
