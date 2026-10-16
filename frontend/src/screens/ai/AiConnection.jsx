import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { useInstantSave } from "../../lib/useInstantSave.js";
import {
  Button, Callout, Card, ErrorState, Field, FieldRow, FormSection, PageHeader, Segmented, Skeleton, useToast,
} from "../../ui/kit.jsx";
import { SettingRow, SettingRows } from "../../ui/adminKit.jsx";
import { SecretField } from "../../ui/SecretField.jsx";
import { AiChecks, AiStatusCard } from "./AiStatusCard.jsx";
import { ChatGptLogin } from "./ChatGptLogin.jsx";
import { MODELS_KEY, ModelPicker } from "./ModelPicker.jsx";

/* AI 연결 (계획 A3 · A8 · M4, D-539 · D-540 · D-574) — `/ai-connection`, 시스템 관리자만.
 *
 * 한 열 흐름의 여섯 구획이다: ① 현재 상태(짧은 연결 상태 면, 카드) → 한 판 위의 구획 다섯(② 제공자와 인증 · ③ 모델 · ④ 실행
 * 옵션 · ⑤ AI 기능 · ⑥ 확인과 오류, 머리와 1px 선으로만 나뉜다). 옛 화면의 「2/3 폼 + 1/3 설명 판」과 「저장해야 적용되는 주
 * 스위치」로 돌아가지 않는다. [지금 확인] 은 ⑥ 에 하나뿐이다 — 최근 확인 · 최근 성공 시각과 막힌 까닭이 그 곁에 선다.
 *
 * ## 사람이 누르는 단추가 줄었다 (D-539)
 *
 * - 키를 「저장하고 확인」하거나 ChatGPT 로 연결하면 모델 목록을 저절로 받는다. 모델이 비어 있으면 추천 모델을 명시적으로
 *   저장하고(감사에 auto), 서버가 연결 확인을 시작한다. 「정상」은 그 모델로 실제 생성이 성공한 뒤에만 선다.
 * - 모델을 바꾸면 곧바로 저장하고 다시 확인한다(그동안 「확인 중」). AI 기능 스위치는 모두 누르는 즉시 저장된다(P-118).
 * - 고른 제공자 · 인증 방식이 지금 연결과 다르면 「이 연결로 바꾸기」가 이 화면의 주 동작이다. 처음 설정(지금 연결이 없다)은
 *   인증이 끝나는 순간 그 연결을 쓴다.
 *
 * ## 인증 방식의 자리 (D-566)
 *
 * API 키가 먼저다(발급처 링크 · 조직 키 권장 · 과금 한 줄은 서버의 방식 설명이다). ChatGPT 계정 연결은 API 키와 같은 정식 방식이라
 * 모든 설치에서 서버가 표에 실어 준다(사용자 결정, D-559 대체). 「AI 사용」은 서버의 `credentials.ready` 와 모델이 갖춰진 뒤에만
 * 켤 수 있다(D-558) — 화면이 자격을 짐작하지 않는다.
 */

export const AI_ADMIN_KEY = ["ai-admin"];
/* 구획 제목 글자의 id — 「다음 할 일」이 그 구획으로 간다(`scrollTo`). */
const SECTION_IDS = { provider: "ai-section-provider", model: "ai-section-model", features: "ai-section-features", checks: "ai-section-checks" };
const POLL_MS = 1500;
const VERIFY_LIMIT_MS = 90_000;

const FEATURES = [
  ["chat_enabled", "AI 도우미", "비활성화하면 AI 도우미 화면과 대화 API가 닫힙니다."],
  ["assistant_narrative_enabled", "홈 문장 요약", "활성화하면 홈과 도우미가 숫자 옆에 한두 문장 요약을 붙입니다."],
  ["game_ai_enabled", "게임 퀴즈 AI", "활성화하면 놀이 화면에서 AI가 퀴즈 초안을 만듭니다."],
];

function withoutVerifyId(res) {
  if (!res || typeof res !== "object") return res;
  const { verify_job_id: _ignored, ...rest } = res;
  return rest;
}

/* 확인을 지켜본다 — 서버가 확인 중이라고 하는 동안만 다시 묻고, 90초가 지나면 묻기를 멈추고 그 사실을 말한다. */
function useVerifyWatch(data, toast) {
  const verifying = Boolean(data && data.state && data.state.verifying);
  const [since, setSince] = React.useState(null);
  const [timedOut, setTimedOut] = React.useState(false);
  const watched = React.useRef(false);
  React.useEffect(() => {
    if (verifying) {
      watched.current = true;
      setSince((s) => s || Date.now());
      return undefined;
    }
    setSince(null);
    setTimedOut(false);
    if (watched.current && data && data.state && data.state.display) {
      watched.current = false;
      const key = data.state.display.key;
      if (key === "ok" || key === "off") toast("AI 연결을 확인했습니다.", "success");
    }
    return undefined;
  }, [verifying, data, toast]);
  React.useEffect(() => {
    if (!since) return undefined;
    const left = Math.max(0, VERIFY_LIMIT_MS - (Date.now() - since));
    const timer = setTimeout(() => setTimedOut(true), left);
    return () => clearTimeout(timer);
  }, [since]);
  return { verifying, timedOut };
}

export function AiConnection() {
  const qc = useQueryClient();
  const toast = useToast();
  const stopPolling = React.useRef(false);
  const query = useQuery({
    queryKey: AI_ADMIN_KEY,
    queryFn: () => api("/api/admin/ai"),
    refetchInterval: (q) => (q.state.data && q.state.data.state && q.state.data.state.verifying && !stopPolling.current
      ? POLL_MS : false),
  });
  const data = query.data;
  const watch = useVerifyWatch(data, toast);
  stopPolling.current = watch.timedOut;

  const [choice, setChoice] = React.useState(null);
  const [runDraft, setRunDraft] = React.useState(null);
  const [switchError, setSwitchError] = React.useState(null);
  const [switching, setSwitching] = React.useState(false);
  /* 「다음 할 일」이 가리키는 구획. 감싸는 상자는 `display: contents` 라 판의 줄 간격을 바꾸지 않는다. */

  const saveConfig = useMutation({
    mutationFn: (body) => api("/api/admin/ai/config", { method: "PUT", body }),
    onSuccess: (res) => qc.setQueryData(AI_ADMIN_KEY, withoutVerifyId(res)),
  });
  const verify = useMutation({
    mutationFn: () => api("/api/admin/ai/verify", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: AI_ADMIN_KEY }),
  });
  /* AI 사용은 누르는 즉시 저장된다 - 켜면 서버가 연결 확인을 연다. */
  const generation = useInstantSave({
    queryKey: AI_ADMIN_KEY,
    mutationFn: ({ value }) => api("/api/admin/ai/config", { method: "PUT", body: { generation_enabled: value } }),
    apply: (old, { value }) => ({ ...old, config: { ...(old.config || {}), generation_enabled: value } }),
    fromResponse: (res) => withoutVerifyId(res),
    onSaved: (_res, { value }) => toast(value ? "AI 사용을 활성화했습니다." : "AI 사용을 비활성화했습니다.", "success"),
    onError: (e) => toast(e.message, "error"),
  });
  const feature = useInstantSave({
    queryKey: AI_ADMIN_KEY,
    mutationFn: ({ key, value }) => api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    apply: (old, { key, value }) => ({ ...old, features: { ...(old.features || {}), [key]: value } }),
    onSaved: () => toast("AI 기능 설정을 저장했습니다.", "success"),
    onError: (e) => toast(e.message, "error"),
  });

  /* 모델 칸에 넘기는 콜백은 그리기마다 새로 만들지 않는다 - 그 칸의 「추천 한 번 저장」 효과가 기대는 값이다. */
  const mutateConfig = saveConfig.mutate;
  const saveModel = React.useCallback((body) => mutateConfig(body), [mutateConfig]);
  const announcePick = React.useCallback(() => toast("추천 모델로 정했습니다. 바꿀 수 있습니다.", "info"), [toast]);

  if (query.isLoading) return <Skeleton kind="page" lines={8} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={query.refetch} />;

  const config = data.config || {};
  const providers = data.providers || [];
  const currentProvider = providers.find((p) => p.key === config.provider) || null;
  const currentMethod = currentProvider ? currentProvider.auth_methods.find((m) => m.key === config.auth_method) || null : null;
  const fallback = providers[0] ? { provider: providers[0].key, auth_method: providers[0].auth_methods[0].key } : null;
  const chosen = choice || (config.provider ? { provider: config.provider, auth_method: config.auth_method } : fallback);
  const chosenProvider = chosen ? providers.find((p) => p.key === chosen.provider) || null : null;
  const chosenMethod = chosenProvider
    ? chosenProvider.auth_methods.find((m) => m.key === chosen.auth_method) || chosenProvider.auth_methods[0]
    : null;
  const isCurrent = Boolean(chosenProvider && chosenMethod && config.provider === chosenProvider.key
    && config.auth_method === chosenMethod.key);
  const limits = data.limits || {};
  const [minTimeout, maxTimeout] = limits.timeout_seconds || [5, 300];
  const [, maxSlots] = limits.max_concurrency || [1, 8];
  const run = { timeout_seconds: config.timeout_seconds, max_concurrency: config.max_concurrency, ...(runDraft || {}) };
  const runDirty = Boolean(runDraft) && Object.keys(runDraft).some((k) => runDraft[k] !== config[k]);
  const features = data.features || {};
  /* 자격은 서버가 판정한다(D-558). 켤 수 있는 것은 자격과 모델이 다 있을 때뿐이다. */
  const credentialsReady = Boolean(data.credentials && data.credentials.ready);
  const configured = credentialsReady && Boolean(config.model);
  const saveFailure = failureText([saveConfig, "설정을 저장하지 못했습니다."])
    || failureText([verify, "연결 확인을 시작하지 못했습니다."]);

  function pick(provider, authMethod) {
    setSwitchError(null);
    const target = providers.find((p) => p.key === provider);
    if (!target) return;
    const method = target.auth_methods.find((m) => m.key === authMethod) || target.auth_methods[0];
    setChoice({ provider: target.key, auth_method: method.key });
  }

  /* 「다음 할 일」이 가리키는 구획 — 제목 글자의 id 로 찾아 그 구획의 머리로 간다. 예전에는 구획마다 `display: contents` 상자를
     둘러 ref 를 달았는데, 그 상자가 구획 사이의 형제 규칙(`.k-form-section + .k-form-section`, 판 안 26px)을 끊어 여섯 구획이
     14px 로 붙어 섰다(캡처 m4-1). 메일 설정과 같은 방식이다. */
  function scrollTo(id) {
    const title = typeof document !== "undefined" ? document.getElementById(id) : null;
    const el = title && (title.closest(".k-form-section") || title);
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  /* 상태 면의 「다음 할 일」 — 서버가 준 자리(`next.action`)로 간다. 동작이 하나뿐인 자리(확인 · 켜기)는 바로 한다. 확인은 ⑥ 의
     단추가 하는 일이라 결과가 서는 그 구획으로 함께 간다. */
  function goNext(action) {
    if (action === "verify") { verify.mutate(); scrollTo(SECTION_IDS.checks); return; }
    if (action === "enable") { if (!config.generation_enabled) generation.mutate({ value: true }); return; }
    if (action === "api_key") {
      const target = chosenProvider || currentProvider || providers[0];
      if (target) pick(target.key, "api_key");
      scrollTo(SECTION_IDS.provider);
      return;
    }
    if (action === "login" || action === "paste") {
      pick("openai", "chatgpt");
      scrollTo(SECTION_IDS.provider);
      return;
    }
    scrollTo(action === "model" ? SECTION_IDS.model : SECTION_IDS.provider);
  }

  /* 고른 연결을 지금 연결로 — 그 연결의 모델 목록을 받아, 지금 모델이 그 목록에 있으면 두고 없으면 추천을 쓴다. */
  async function switchTo(target) {
    setSwitchError(null);
    setSwitching(true);
    let model = "";
    let failed = null;
    try {
      const res = await api("/api/admin/ai/models?provider=" + encodeURIComponent(target.provider)
        + "&auth_method=" + encodeURIComponent(target.auth_method));
      qc.setQueryData(MODELS_KEY(target.provider, target.auth_method), res);
      const ids = (res.models || []).map((m) => m.id);
      model = ids.includes(config.model) ? config.model : (res.recommended_id || "");
    } catch (e) {
      failed = e;
    }
    if (failed && config.generation_enabled) {
      setSwitching(false);
      setSwitchError(`${failed.message || "모델 목록을 가져오지 못했습니다."} 연결을 바꾸지 않았습니다.`);
      return;
    }
    saveConfig.mutate(
      { provider: target.provider, auth_method: target.auth_method, model, auto_model: Boolean(model) && model !== config.model },
      { onSettled: () => setSwitching(false), onSuccess: () => setChoice(null) },
    );
  }

  /* 인증이 끝났다(키 저장 · ChatGPT 연결). 처음 설정이면 그 연결을 쓰고, 지금 연결이면 다시 확인한다. 모델이 비어 있으면
     모델 칸이 추천을 저장하고 그 저장이 확인을 연다. 다른 연결이 이미 쓰이고 있으면 바꾸기는 사람이 고른다. */
  async function afterAuth(serverStartedVerify) {
    const fresh = await qc.fetchQuery({ queryKey: AI_ADMIN_KEY, queryFn: () => api("/api/admin/ai") });
    const cfg = (fresh && fresh.config) || {};
    if (!chosenProvider || !chosenMethod) return;
    if (!cfg.provider) {
      switchTo({ provider: chosenProvider.key, auth_method: chosenMethod.key });
      return;
    }
    const same = cfg.provider === chosenProvider.key && cfg.auth_method === chosenMethod.key;
    if (same && cfg.model && !serverStartedVerify && !(fresh.state && fresh.state.verifying)) verify.mutate();
  }

  const currentName = currentProvider && currentMethod ? `${currentProvider.label} ${currentMethod.label}` : null;
  return (
    <Box className="c-screen">
      <PageHeader area="AI" title="AI 연결" help="AI 제공자에 연결하고 AI 기능을 활성화하거나 비활성화합니다." />

      <AiStatusCard data={data} onNext={goNext} timedOut={watch.timedOut} />

      {/* 설정과 확인은 한 판 위의 구획 다섯이다 - 머리와 선으로만 나뉘고 카드를 두르지 않는다(F7 카드 규율, D-527). */}
      <Card stack data-testid="ai-connection-form">
        <FormSection titleAs="h2" title={<span id={SECTION_IDS.provider}>제공자와 인증</span>}>
          {chosenProvider ? (
            <FieldRow columns={["auto", "auto"]}>
              <Field label="제공자" fit>
                <Segmented
                  ariaLabel="제공자" value={chosenProvider.key}
                  options={providers.map((p) => ({ value: p.key, label: p.label }))}
                  onChange={(value) => pick(value, value === chosenProvider.key ? chosenMethod.key : null)}
                />
              </Field>
              {chosenProvider.auth_methods.length > 1 ? (
                <Field label="인증 방식" fit>
                  <Segmented
                    ariaLabel="인증 방식" value={chosenMethod.key}
                    options={chosenProvider.auth_methods.map((m) => ({ value: m.key, label: m.label }))}
                    onChange={(value) => pick(chosenProvider.key, value)}
                  />
                </Field>
              ) : null}
            </FieldRow>
          ) : null}
          {chosenMethod && chosenMethod.account ? (
            <ChatGptLogin
              chatgpt={data.chatgpt} login={data.login}
              onConnected={(res) => afterAuth(Boolean(res && res.verify_job_id))}
              onLoggedOut={(res) => qc.setQueryData(AI_ADMIN_KEY, (res && res.overview) || data)}
            />
          ) : chosenMethod ? (
            <>
              {/* 키는 저장하면 되읽지 않는다. 끝 네 글자로 어느 키인지만 알아본다. */}
              <SecretField
                key={chosenMethod.secret_slot}
                slot={chosenMethod.secret_slot} label="API 키" saveLabel="저장하고 확인"
                help={[chosenMethod.help, chosenMethod.secret_hint ? `저장된 키의 ${chosenMethod.secret_hint}입니다.` : null]
                  .filter(Boolean).join(" ")}
                onChanged={() => afterAuth(false)}
              />
              {chosenMethod.issue_url ? (
                <Typography variant="body2" color="text.secondary">
                  <Link href={chosenMethod.issue_url} target="_blank" rel="noopener noreferrer">
                    {`${chosenProvider.label} 키 발급처 열기`}
                  </Link>
                </Typography>
              ) : null}
            </>
          ) : null}
          {!isCurrent && currentName && chosenProvider && chosenMethod ? (
            <Callout
              tone="info" compact
              action={(
                <Button
                  variant="primary" size="sm" disabled={!chosenMethod.ready} loading={switching}
                  onClick={() => switchTo({ provider: chosenProvider.key, auth_method: chosenMethod.key })}
                >
                  이 연결로 바꾸기
                </Button>
              )}
            >
              {`지금 쓰는 연결은 ${currentName}입니다.`}
            </Callout>
          ) : null}
          {switchError ? <Callout tone="danger" compact>{switchError}</Callout> : null}
        </FormSection>

        <FormSection titleAs="h2" title={<span id={SECTION_IDS.model}>모델</span>}>
          <ModelPicker
            config={config} method={currentMethod} saving={saveConfig.isPending}
            onSave={saveModel} onAutoPicked={announcePick}
          />
        </FormSection>

        <FormSection titleAs="h2" title="실행 옵션">
          <FieldRow
            columns={["12rem", "12rem"]}
            action={(
              <>
                <Button disabled={!runDirty || saveConfig.isPending} onClick={() => setRunDraft(null)}>되돌리기</Button>
                <Button
                  variant="primary" disabled={!runDirty} loading={saveConfig.isPending}
                  onClick={() => saveConfig.mutate(runDraft, {
                    onSuccess: () => { setRunDraft(null); toast("실행 옵션을 저장했습니다.", "success"); },
                  })}
                >
                  저장
                </Button>
              </>
            )}
          >
            <Field label="제한 시간(초)" htmlFor="ai-timeout" help={`${minTimeout}초에서 ${maxTimeout}초 사이로 정합니다.`}>
              <TextField
                id="ai-timeout" size="small" type="number" fullWidth value={run.timeout_seconds ?? ""}
                onChange={(e) => setRunDraft((d) => ({ ...(d || {}), timeout_seconds: Number(e.target.value) }))}
                inputProps={{ min: minTimeout, max: maxTimeout }}
              />
            </Field>
            <Field label="동시 실행 수" htmlFor="ai-concurrency" help={`최대 ${maxSlots}입니다.`}>
              <TextField
                id="ai-concurrency" size="small" type="number" fullWidth value={run.max_concurrency ?? ""}
                onChange={(e) => setRunDraft((d) => ({ ...(d || {}), max_concurrency: Number(e.target.value) }))}
                inputProps={{ min: 1, max: maxSlots }}
              />
            </Field>
          </FieldRow>
        </FormSection>

        <FormSection titleAs="h2" title={<span id={SECTION_IDS.features}>AI 기능</span>}>
          {/* 설정 줄은 괘선 목록이다 - 구획 머리 선 바로 아래 첫 줄은 윗선을 두 번 긋지 않는다. 모두 누르는 즉시 저장된다. */}
          <SettingRows>
            <SettingRow
              compact label="AI 사용" controlId="ai-generation"
              description={configured
                ? "비활성화하면 모든 AI 기능이 답을 만들지 않습니다."
                : (credentialsReady ? "모델을 고르면 활성화할 수 있습니다." : "제공자를 연결하면 활성화할 수 있습니다.")}
              action={(
                <Switch
                  id="ai-generation" checked={Boolean(config.generation_enabled)}
                  disabled={!configured && !config.generation_enabled}
                  onChange={() => generation.mutate({ value: !config.generation_enabled })}
                  slotProps={{ input: { "aria-label": "AI 사용" } }}
                />
              )}
            />
            {FEATURES.map(([key, label, description]) => (
              <SettingRow
                key={key} compact label={label} controlId={`ai-feature-${key}`}
                description={config.generation_enabled ? description : `${description} 지금은 AI 사용이 비활성 상태라 동작하지 않습니다.`}
                action={(
                  <Switch
                    id={`ai-feature-${key}`} checked={Boolean(features[key])}
                    onChange={() => feature.mutate({ key, value: !features[key] })}
                    slotProps={{ input: { "aria-label": label } }}
                  />
                )}
              />
            ))}
          </SettingRows>
        </FormSection>

        {/* ⑥ 확인과 오류 — 이 화면의 하나뿐인 [지금 확인] · 최근 시각 · 막힌 까닭 · 저장 실패가 한 구획에 선다. */}
        <AiChecks
          data={data} onVerify={() => verify.mutate()} verifying={verify.isPending || watch.verifying} problem={saveFailure}
          titleId={SECTION_IDS.checks}
        />
      </Card>
    </Box>
  );
}

export default AiConnection;
