import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Link from "@mui/material/Link";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import {
  Button, Callout, DotLabel, Field, FieldRow, Modal, TechDetail, TechRows, useConfirm,
} from "../../ui/kit.jsx";
import { SettingRow, SettingRows } from "../../ui/adminKit.jsx";
import { ChoiceCards } from "../../ui/ChoiceCards.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import {
  CERT_SENTENCE, CERT_STRATEGIES, CHECK_LABEL, CHECK_TONE, CHECK_WORD, MAX_ALIASES, applyParams, certCoverage,
  hasFailure, normalizeAliases, orderedChecks, parseAddress, plannedSteps, previewQuery, publicDnsText,
} from "./serviceAddress.js";

/* 서비스 주소 바꾸기 대화 상자 (계획 M4, D-574 · 서버 계약 D-573).
 *
 * 상태 기계 넷이다: **입력** → **미리 확인**(서버의 `domain.preview` — DNS · 인증서 · 웹 서버 · 서비스 설정) → **적용**(`domain.apply`,
 * 한 번 묻는다) → **결과**. 미리 확인에 실패(`fail`)가 하나라도 있으면 적용 단추가 꺼진다 — 서버도 같은 것을 다시 본다.
 *
 * 함께 쓸 주소는 고르는 목록이다(지금 대표 주소와 지금 별칭이 처음부터 골라져 있다). 옛 이름을 빼면 그 이름은 더 열리지 않는다 —
 * 그래서 기본은 남기는 쪽이다(D-d: 리디렉션 없는 별칭).
 *
 * 적용 뒤 웹 서버는 3초 뒤에 다시 시작한다(D-i). 이 화면을 연 프로세스가 그 웹 서버라 결과를 먼저 받고, 그 뒤 같은 주소의
 * `/healthz` 를 물어 다시 뜬 것을 확인한다. 새 주소로는 다시 로그인해야 한다(로그인은 주소마다 따로다).
 */

export const HEALTH_POLL_MS = 1000;
export const HEALTH_LIMIT_MS = 60_000;

const STEP_STATE = {
  ok: { label: "완료", tone: "ok" },
  failed: { label: "실패", tone: "danger" },
  running: { label: "진행 중", tone: "info" },
  waiting: { label: "대기", tone: "neutral" },
};

/* 웹 서버 지연 재시작을 지켜본다 — 예약한 시간이 지난 뒤 같은 주소의 `/healthz` 가 200 을 줄 때까지(60초 상한). */
function useRestartWatch(webRestart) {
  const [state, setState] = React.useState("idle");
  React.useEffect(() => {
    if (!webRestart || !webRestart.scheduled) return undefined;
    let stopped = false;
    let timer = null;
    const started = Date.now();
    setState("waiting");
    const tick = async () => {
      if (stopped) return;
      if (Date.now() - started > HEALTH_LIMIT_MS) { setState("slow"); return; }
      try {
        const res = await fetch("/healthz", { cache: "no-store", credentials: "same-origin" });
        if (!stopped && res.ok) { setState("up"); return; }
      } catch {
        /* 다시 시작하는 동안에는 연결이 끊긴다 — 다음 차례에 다시 묻는다. */
      }
      if (!stopped) timer = setTimeout(tick, HEALTH_POLL_MS);
    };
    timer = setTimeout(tick, (webRestart.delay_seconds || 3) * 1000 + 1500);
    return () => { stopped = true; clearTimeout(timer); };
  }, [webRestart]);
  return state;
}

function StepList({ steps, running }) {
  return (
    <Box component="ol" data-testid="domain-steps" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
      {steps.map((step) => {
        const key = running ? "running" : step.ok === false ? "failed" : step.ok ? "ok" : "waiting";
        const meta = STEP_STATE[key];
        return (
          <Box component="li" key={step.name} data-step={step.name} data-step-state={key}
            sx={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 1.5, rowGap: 0.25, minWidth: 0 }}>
            <Typography component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.bodySm, minWidth: "7.5rem" }}>
              {step.label}
            </Typography>
            <DotLabel tone={meta.tone} label={meta.label} size="caption" />
            {step.detail ? (
              <Typography component="span" sx={{ flexBasis: "100%", fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                {step.detail}
              </Typography>
            ) : null}
            {(step.units || []).length ? (
              <Box component="ul" sx={{ flexBasis: "100%", m: 0, pl: 2.5 }}>
                {step.units.map((u) => (
                  <Typography component="li" key={u.unit} sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                    {`${u.label}: ${u.detail}`}
                  </Typography>
                ))}
              </Box>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

function CheckList({ checks }) {
  return (
    <Box component="ul" data-testid="domain-checks" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
      {checks.map((c) => (
        <Box component="li" key={c.key} data-check={c.key} data-check-state={c.state}
          sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr)", sm: "9rem minmax(0,1fr)" }, columnGap: 1.5, rowGap: 0.25 }}>
          <DotLabel tone={CHECK_TONE[c.state] || "neutral"} label={`${CHECK_LABEL[c.key] || c.label} ${CHECK_WORD[c.state] || CHECK_WORD.unknown}`} />
          <Typography variant="body2" sx={KO_WORD_BREAK}>{c.message || "확인하지 못했습니다."}</Typography>
        </Box>
      ))}
    </Box>
  );
}

export function DomainChangeDialog({ open, onClose, domain, currentCert }) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const current = (domain && domain.canonical) || "";
  const [address, setAddress] = React.useState("");
  const [touched, setTouched] = React.useState(false);
  const [rows, setRows] = React.useState(() => [
    ...(current ? [{ name: current, checked: true, note: "지금 대표 주소입니다." }] : []),
    ...((domain && domain.aliases) || []).map((a) => ({ name: a, checked: true, note: "지금 함께 쓰는 주소입니다." })),
  ]);
  const [extra, setExtra] = React.useState("");
  const [extraError, setExtraError] = React.useState(null);
  const [strategy, setStrategy] = React.useState("self_signed");
  const [certificate, setCertificate] = React.useState("");
  const [privateKey, setPrivateKey] = React.useState("");
  const [restartWeb, setRestartWeb] = React.useState(true);
  const [stage, setStage] = React.useState("input");
  const [review, setReview] = React.useState(null);
  const [result, setResult] = React.useState(null);

  const parsed = parseAddress(address);
  const host = parsed.host || "";
  const shownRows = rows.filter((r) => r.name !== host);
  const aliases = normalizeAliases(shownRows.filter((r) => r.checked).map((r) => r.name), host);
  const tooMany = aliases.length > MAX_ALIASES;
  const coverage = certCoverage(currentCert, host ? [host, ...aliases] : []);
  const keepBlocked = coverage.known && coverage.missing.length > 0;
  const pemMissing = strategy === "provided" && (!certificate.trim() || !privateKey.trim());
  const sameAsNow = host && host === current && aliases.join(",") === ((domain && domain.aliases) || []).join(",") && strategy === "keep";
  const inputReady = Boolean(host) && !tooMany && !pemMissing && !(strategy === "keep" && keepBlocked);

  React.useEffect(() => {
    if (strategy === "keep" && keepBlocked) setStrategy("self_signed");
  }, [strategy, keepBlocked]);

  const check = useMutation({
    mutationFn: () => api(`/api/admin/system/domain${previewQuery(host, aliases)}`),
    onSuccess: (res) => { setReview(res); setStage("review"); },
  });
  const apply = useMutation({
    mutationFn: () => api("/api/admin/system/domain.apply", {
      method: "POST",
      body: { params: applyParams({ host, aliases, strategy, certificate, privateKey, restartWeb }) },
    }),
    onMutate: () => setStage("applying"),
    onSuccess: (res) => {
      setResult(res);
      setStage("result");
      qc.invalidateQueries({ queryKey: ["system-ops"] });
      qc.invalidateQueries({ queryKey: ["system-domain"] });
    },
    onError: () => setStage("review"),
  });
  const restart = useRestartWatch(result && result.ok ? (result.data || {}).web_restart : null);

  function addExtra() {
    const got = parseAddress(extra);
    if (!extra.trim()) { setExtraError("추가할 주소를 입력하세요."); return; }
    if (got.error) { setExtraError(got.error); return; }
    if (rows.some((r) => r.name === got.host)) { setExtraError("이미 목록에 있는 주소입니다."); return; }
    setRows((list) => [...list, { name: got.host, checked: true, note: "새로 추가한 주소입니다." }]);
    setExtra("");
    setExtraError(null);
  }

  async function doApply() {
    const ok = await confirm(
      "웹 서버 설정과 서비스 설정을 바꾸고 백그라운드 서비스를 다시 시작합니다. 확인에 실패하면 바꾸기 전 설정으로 되돌립니다.",
      { title: "서비스 주소를 바꿀까요?", confirmLabel: "적용" },
    );
    if (ok) apply.mutate();
  }

  const checkError = failureText([check, "미리 확인을 하지 못했습니다."]);
  const applyError = failureText([apply, "적용 요청을 보내지 못했습니다."]);
  const preview = (review && review.preview) || {};
  const checks = orderedChecks(preview.checks);
  const blocked = !review || review.available === false || review.ok === false || hasFailure(checks) || preview.can_apply === false;
  const impact = [
    ...(preview.impact || []),
    CERT_SENTENCE[strategy],
    restartWeb
      ? "웹 서버를 3초 뒤 다시 시작합니다. 약 3초 동안 접속이 끊깁니다."
      : "웹 서버는 다시 시작하지 않습니다. 웹 화면이 만드는 링크는 웹 서버를 다시 시작한 뒤부터 새 주소를 씁니다.",
  ];
  const publicDns = publicDnsText(preview.dns);
  const data = (result && result.data) || {};
  const steps = stage === "applying" ? plannedSteps(restartWeb) : (data.steps || []);
  const busy = stage === "applying";
  const dirty = stage === "input" && (Boolean(address.trim()) || Boolean(certificate) || Boolean(privateKey));

  let footer;
  if (stage === "input") {
    footer = (
      <>
        <Button onClick={onClose}>취소</Button>
        <Button variant="primary" disabled={!inputReady || Boolean(sameAsNow)} loading={check.isPending}
          onClick={() => { setTouched(true); if (inputReady) check.mutate(); }}>
          미리 확인
        </Button>
      </>
    );
  } else if (stage === "review") {
    footer = (
      <>
        <Button onClick={() => setStage("input")} disabled={apply.isPending}>뒤로</Button>
        <Button variant="primary" disabled={blocked} loading={apply.isPending} onClick={doApply}>적용</Button>
      </>
    );
  } else if (stage === "applying") {
    footer = <Button disabled>적용하는 중</Button>;
  } else {
    footer = (
      <>
        {result && result.ok && data.url ? (
          <Button href={`${data.url}/login`} target="_blank" rel="noopener noreferrer">새 주소 열기</Button>
        ) : null}
        <Button variant="primary" onClick={onClose}>닫기</Button>
      </>
    );
  }

  return (
    <Modal open={open} onClose={busy ? () => {} : onClose} title="서비스 주소 바꾸기" size="lg" dirty={dirty} footer={footer}>
        <Box data-testid="domain-dialog" data-stage={stage} sx={{ display: "grid", gap: 2.5, minWidth: 0 }}>
          {stage === "input" ? (
            <>
              <Field
                label="새 주소" htmlFor="domain-host" required
                error={touched && address.trim() && parsed.error ? parsed.error : null}
                help={sameAsNow ? "지금과 같은 주소와 인증서입니다. 바꿀 것이 없습니다." : "https 주소를 넣습니다. 경로와 포트는 빼고 이름만 씁니다."}
              >
                <TextField
                  id="domain-host" size="small" fullWidth value={address} placeholder="https://service.example.com"
                  onChange={(e) => setAddress(e.target.value)} onBlur={() => setTouched(true)}
                  inputProps={{ spellCheck: false, autoComplete: "off", "aria-invalid": Boolean(touched && address.trim() && parsed.error) }}
                />
              </Field>

              <Box sx={{ display: "grid", gap: 1, minWidth: 0 }}>
                <Typography component="h3" sx={{ m: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold }}>함께 쓸 주소</Typography>
                <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
                  고른 주소도 같은 화면을 엽니다. 다른 주소로 보내지 않습니다. 빼면 그 주소는 더 열리지 않습니다.
                </Typography>
                {shownRows.length ? (
                  <Box data-testid="domain-aliases">
                  <SettingRows>
                    {shownRows.map((r) => (
                      <SettingRow
                        key={r.name} compact label={r.name} description={r.note} controlId={`domain-alias-${r.name}`}
                        action={(
                          <Checkbox
                            id={`domain-alias-${r.name}`} checked={r.checked}
                            onChange={(e) => setRows((list) => list.map((x) => (x.name === r.name ? { ...x, checked: e.target.checked } : x)))}
                            slotProps={{ input: { "aria-label": `${r.name} 함께 쓰기` } }}
                          />
                        )}
                      />
                    ))}
                  </SettingRows>
                  </Box>
                ) : null}
                <FieldRow columns={["min(100%, 24rem)"]} action={<Button onClick={addExtra}>추가</Button>}>
                  <Field label="주소 추가" htmlFor="domain-alias-new" error={extraError}>
                    <TextField
                      id="domain-alias-new" size="small" fullWidth value={extra} placeholder="old.example.internal"
                      onChange={(e) => { setExtra(e.target.value); setExtraError(null); }}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addExtra(); } }}
                      inputProps={{ spellCheck: false, autoComplete: "off" }}
                    />
                  </Field>
                </FieldRow>
                {tooMany ? <Callout tone="warn" compact>{`함께 쓸 주소는 ${MAX_ALIASES}개까지 고를 수 있습니다.`}</Callout> : null}
              </Box>

              <Field label="인증서" labelId="domain-cert-label">
                <ChoiceCards
                  name="domain-cert" ariaLabel="인증서" value={strategy} onChange={setStrategy}
                  options={CERT_STRATEGIES.map((o) => ({ ...o, disabled: o.value === "keep" && keepBlocked }))}
                />
              </Field>
              {strategy === "provided" ? (
                <FieldRow>
                  <Field span={{ wide: 6, mid: 1 }} label="인증서(PEM)" htmlFor="domain-pem-cert" required help="-----BEGIN CERTIFICATE----- 로 시작하는 글입니다.">
                    <TextField id="domain-pem-cert" size="small" fullWidth multiline minRows={4} value={certificate}
                      onChange={(e) => setCertificate(e.target.value)} inputProps={{ spellCheck: false }} />
                  </Field>
                  <Field span={{ wide: 6, mid: 1 }} label="개인키(PEM)" htmlFor="domain-pem-key" required help="저장한 뒤 다시 보여 주지 않습니다.">
                    <TextField id="domain-pem-key" size="small" fullWidth multiline minRows={4} value={privateKey}
                      onChange={(e) => setPrivateKey(e.target.value)} inputProps={{ spellCheck: false, autoComplete: "off" }} />
                  </Field>
                </FieldRow>
              ) : null}

              <SettingRows>
                <SettingRow
                  compact label="웹 서버를 3초 뒤 다시 시작" controlId="domain-restart-web"
                  description="약 3초 동안 접속이 끊깁니다."
                  action={(
                    <Checkbox id="domain-restart-web" checked={restartWeb} onChange={(e) => setRestartWeb(e.target.checked)}
                      slotProps={{ input: { "aria-label": "웹 서버를 3초 뒤 다시 시작" } }} />
                  )}
                />
              </SettingRows>
              {checkError ? <Callout tone="danger" compact>{checkError}</Callout> : null}
            </>
          ) : null}

          {stage === "review" ? (
            <>
              <Typography variant="body2" sx={KO_WORD_BREAK}>
                {`새 대표 주소는 https://${host} 입니다.${aliases.length ? ` 함께 쓰는 주소는 ${aliases.join(", ")} 입니다.` : ""}`}
              </Typography>
              {review && review.available === false ? (
                <Callout tone="warn" compact>{review.detail || "시스템 설정 도우미를 쓸 수 없습니다."}</Callout>
              ) : (
                <>
                  <CheckList checks={checks} />
                  <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
                    {["DNS는 사내 해석기(이 서버가 쓰는 해석기) 기준입니다.", publicDns].filter(Boolean).join(" ")}
                  </Typography>
                </>
              )}
              {hasFailure(checks) || preview.can_apply === false ? (
                <Callout tone="danger" compact>실패한 확인이 있어 적용할 수 없습니다. 그 항목을 수정한 뒤 다시 확인하세요.</Callout>
              ) : null}
              <Callout tone="info" title="적용하면 이렇게 바뀝니다">
                <Box component="ul" data-testid="domain-impact" sx={{ m: 0, pl: 2.5, display: "grid", gap: 0.5 }}>
                  {impact.map((line) => (
                    <Typography component="li" variant="body2" key={line} sx={KO_WORD_BREAK}>{line}</Typography>
                  ))}
                </Box>
              </Callout>
              {applyError ? <Callout tone="danger" compact>{applyError}</Callout> : null}
            </>
          ) : null}

          {stage === "applying" ? (
            <>
              <Typography variant="body2" sx={KO_WORD_BREAK}>
                적용하는 중입니다. 서비스를 다시 시작하느라 1분 남짓 걸릴 수 있습니다. 이 창을 닫지 마세요.
              </Typography>
              <StepList steps={steps} running />
            </>
          ) : null}

          {stage === "result" && result ? (
            <>
              {result.ok ? (
                <Callout tone="success" title={result.detail || "서비스 주소를 바꿨습니다."}>
                  <Typography component="span" variant="body2" sx={KO_WORD_BREAK}>
                    새 주소에서 다시 로그인하세요.{" "}
                    {data.url ? (
                      <Link href={`${data.url}/login`} target="_blank" rel="noopener noreferrer">{`${data.url}/login`}</Link>
                    ) : null}
                  </Typography>
                </Callout>
              ) : (
                <Callout tone="danger" title="서비스 주소를 바꾸지 못했습니다.">
                  {`${result.detail || "적용하지 못했습니다."}${result.rolled_back ? " 바꾸기 전 설정으로 되돌렸습니다." : ""}`}
                </Callout>
              )}
              {result.ok && (data.warnings || []).length ? (
                <Callout tone="warn" compact>{`다시 시작하지 못한 서비스가 있습니다. ${data.warnings.join(" ")}`}</Callout>
              ) : null}
              {result.ok ? (
                <Typography variant="body2" color="text.secondary" data-testid="domain-restart" data-restart={restart} sx={KO_WORD_BREAK}>
                  {restart === "waiting" ? "웹 서버를 다시 시작하는 중입니다."
                    : restart === "up" ? "웹 서버가 다시 시작했습니다. 새 주소로 접속할 수 있습니다."
                      : restart === "slow" ? "웹 서버가 아직 답하지 않습니다. 잠시 뒤 새 주소로 접속하세요."
                        : "웹 서버는 다시 시작하지 않았습니다. 웹 화면이 만드는 링크는 웹 서버를 다시 시작한 뒤부터 새 주소를 씁니다."}
                </Typography>
              ) : null}
              {steps.length ? <StepList steps={steps} /> : null}
              {steps.some((s) => s.technical) ? (
                <TechDetail>
                  <TechRows rows={steps.filter((s) => s.technical).map((s) => [s.label || s.name, s.technical])} />
                </TechDetail>
              ) : null}
            </>
          ) : null}
        </Box>
    </Modal>
  );
}

export default DomainChangeDialog;
