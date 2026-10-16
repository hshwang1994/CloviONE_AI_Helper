import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { failureText } from "../../lib/failure.js";
import { fmtDateTime } from "../../lib/format.js";
import {
  Button, Callout, DotLabel, Field, FieldRow, HeadRow, TechDetail, TechRows, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { SettingRow, SettingRows } from "../../ui/adminKit.jsx";
import { ChoiceCards } from "../../ui/ChoiceCards.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";

/* 메일 · 설정 탭의 「ClovirAssist 로컬 릴레이」 부품 (계획 M7 · M4, D-551 · D-574 · D-592).
 *
 * 여섯 구획(발송 상태 · 발신 정보 · 전달 방식과 서버 이름 · 연결과 시험 발송 · DNS 인증 진단 · 요청 내용과 기술 상세) 가운데 세 자리에
 * 들어간다.
 *  - 「전달 방식과 서버 이름」(`RelayFields`): 구성 요소의 상태 한 줄과 활성화 · 다시 적용 · 비활성화, 전달 방식(상위 SMTP 이용 ·
 *    인터넷으로 직접 전달), 고른 방식의 칸만. 직접 전달이면 「메일 서버 식별 정보」(서버 이름(HELO) · 공인 IP · DKIM)가 선다.
 *  - 「DNS 인증 진단」(`RelayDiagnosis`): 펼친 채 서는 점검 한 문장 · 항목별 상태와 고칠 곳 · 서버 이름 제안 · 참고 문장.
 *  - 「요청 내용과 기술 상세」(`RelayRequests` · `RelayAdvancedFields`): 닫힌 접기 안의 담당자별 요청 내용 · 복사할 DNS 레코드와
 *    받는 도메인별 전달 서버 · 비교할 공개 DNS. 원문이 길어 처음에는 닫혀 있고, 안에서는 소제목으로만 나뉜다.
 *
 * 일반 화면에는 구성 요소의 제품 이름을 쓰지 않는다 - 꾸러미 · 서비스 · 듣는 소켓은 「기술 정보」 안에만 있다.
 * 칸 값은 메일 설정 폼의 한 번의 「저장」에 실린다(비밀번호 포함). 활성화 · 다시 적용 · 비활성화 · 키 추가 · 점검은 저장한 설정으로만
 * 한다 - 저장하지 않은 수정 내용이 있으면 그 단추들은 닫혀 있고 까닭을 한 줄로 말한다.
 */

/* 폼 줄의 칸 폭 — 12칸 격자(`FieldRow` 기본, 칸 폭을 보는 컨테이너 질의)에서 넓을 때 몇 칸, 두 칸 격자일 때 몇 칸. 좁은 판(모바일)
   에서는 한 칸씩 쌓인다. 예전의 고정 열(`2fr 12rem 8rem`)은 390 에서 서버 주소 칸을 20px 로 눌렀다(캡처 m4-1, D-574). */
const FIELD_SPAN = {
  half: { wide: 6, mid: 1 }, server: { wide: 6, mid: 2 }, security: { wide: 4, mid: 1 }, port: { wide: 2, mid: 1 },
  main: { wide: 8, mid: 1 }, side: { wide: 4, mid: 1 },
};

export const MAIL_RELAY_KEY = ["mail-relay"];
const POLL_MS = 2000;
const CHECK_LIMIT_MS = 90_000;
const SECURITY = [["starttls", "STARTTLS"], ["ssl", "SSL"], ["none", "사용 안 함"]];
const PORT_PRESETS = { starttls: 587, ssl: 465, none: 25 };
const COMPONENT_TONE = { ready: "neutral", running: "ok", stopped: "danger", not_installed: "warn", foreign: "warn", unavailable: "neutral" };
const CHECK_STATE = {
  ok: { label: "정상", tone: "ok" },
  warn: { label: "주의", tone: "warn" },
  fail: { label: "실패", tone: "danger" },
  unknown: { label: "알 수 없음", tone: "neutral" },
};

function Line({ children, muted = true }) {
  return (
    <Typography variant="body2" color={muted ? "text.secondary" : "text.primary"} sx={KO_WORD_BREAK}>{children}</Typography>
  );
}

/* 구획 안의 소제목 — 판 제목(구획 머리)보다 한 단 작고 굵다. `level` 4 는 소제목 아래의 소제목이다. `action` 을 주면 제목 줄 오른쪽에
   단추가 선다(제목 첫 줄과 단추 가운데선이 같다, `HeadRow`). */
export function SubHeading({ children, level = 3, action, id }) {
  const heading = (
    <Typography
      component={`h${level}`} id={id}
      sx={{ m: 0, fontSize: level >= 4 ? FONT_SIZE.bodySm : FONT_SIZE.body, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}
    >
      {children}
    </Typography>
  );
  if (!action) return heading;
  return <HeadRow action={action}>{heading}</HeadRow>;
}

function ComponentTechRows({ data }) {
  if (!data) return null;
  const rows = [
    ["패키지", data.packages ? Object.entries(data.packages).map(([k, v]) => `${k} ${v || "없음"}`).join(", ") : null],
    ["다른 메일 발송 프로그램", (data.other_mta || []).join(", ") || null],
    ["설정 파일", data.config],
    ["서비스", data.services ? Object.entries(data.services).map(([k, v]) => `${k}=${v}`).join(", ") : null],
    ["수신 대기 소켓", (data.listeners || []).join(", ") || (data.listeners ? "없음" : null)],
    ["큐", data.queue_count != null ? `${data.queue_count}통` : null],
    ["도우미", data.helper],
  ].filter(([, v]) => v);
  if (!rows.length) return null;
  return (
    <TechDetail>
      <TechRows rows={rows} />
    </TechDetail>
  );
}

/* 구성 요소 상태 한 줄과 활성화 · 다시 적용 · 비활성화(동사표 PA-RC-0002: 켜기 → 활성화, 끄기 → 비활성화). */
function RelayComponent({ relay, savedLocal, dirty, verify }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const component = relay.component || {};
  const after = (res) => {
    if (res && res.relay) qc.setQueryData(MAIL_RELAY_KEY, res.relay);
    qc.invalidateQueries({ queryKey: ["mail-status"] });
  };
  const apply = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/apply", { method: "POST", body: {} }),
    onSuccess: (res) => {
      after(res);
      if (res.result && res.result.ok) {
        toast(res.result.message || "로컬 릴레이를 활성화했습니다.", "success");
        if (res.verify && res.verify.job_id && verify) verify.watch(res.verify.job_id);
      }
    },
  });
  const disable = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/disable", { method: "POST", body: {} }),
    onSuccess: (res) => { after(res); if (res.result && res.result.ok) toast("로컬 릴레이를 비활성화했습니다.", "success"); },
  });
  const refused = apply.data && apply.data.result && !apply.data.result.ok ? apply.data.result : null;
  const error = failureText([apply, "로컬 릴레이를 활성화하지 못했습니다."]) || failureText([disable, "로컬 릴레이를 비활성화하지 못했습니다."]);
  const blockedWhy = !savedLocal ? "발송 방식을 로컬 릴레이로 저장한 뒤에 활성화할 수 있습니다."
    : dirty ? "저장하지 않은 수정 내용이 있습니다. 저장한 뒤에 활성화할 수 있습니다." : null;
  const canStart = ["ready", "stopped"].includes(component.state);
  async function turnOff() {
    const ok = await confirm(
      "로컬 릴레이를 비활성화하면 큐에 남은 메일은 다시 활성화할 때까지 나가지 않습니다. 비활성화할까요?",
      { danger: true, title: "로컬 릴레이 비활성화", confirmLabel: "비활성화" },
    );
    if (ok) disable.mutate();
  }
  const actions = (
    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
      {canStart ? (
        <Button variant="primary" loading={apply.isPending} disabled={Boolean(blockedWhy)} aria-describedby={blockedWhy ? "relay-blocked" : undefined}
          onClick={() => apply.mutate()}>로컬 릴레이 활성화</Button>
      ) : null}
      {component.state === "running" ? (
        <>
          <Button loading={apply.isPending} disabled={Boolean(blockedWhy)} onClick={() => apply.mutate()}>다시 적용</Button>
          <Button variant="danger" loading={disable.isPending} onClick={turnOff}>비활성화</Button>
        </>
      ) : null}
    </Box>
  );
  return (
    <Box sx={{ display: "grid", gap: 1.25, minWidth: 0 }} data-testid="relay-component" data-relay-state={component.state}>
      {/* 상태 낱말과 동작이 한 줄, 문장은 그 아래 줄이다 — 문장을 낱말 옆에 두면 좁은 폭에서 단추 옆 좁은 칸에 세 줄로 접혔다(390 캡처). */}
      <HeadRow action={actions}>
        <DotLabel label={component.label || "확인할 수 없음"} tone={COMPONENT_TONE[component.state] || "neutral"} strong />
      </HeadRow>
      {component.message ? <Line>{component.message}</Line> : null}
      {component.help ? <Line>{component.help}</Line> : null}
      {blockedWhy && canStart ? <Typography id="relay-blocked" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{blockedWhy}</Typography> : null}
      {component.stale && !dirty ? (
        <Callout tone="info" compact>저장한 설정이 아직 로컬 릴레이에 적용되지 않았습니다. 다시 적용하세요.</Callout>
      ) : null}
      {refused ? <Callout tone="danger" compact>{refused.message}</Callout> : null}
      {error ? <Callout tone="danger" compact>{error}</Callout> : null}
      <ComponentTechRows data={component.technical} />
    </Box>
  );
}

function OverrideRows({ rows, onChange }) {
  const list = rows || [];
  const update = (i, patch) => onChange(list.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  return (
    <Box sx={{ display: "grid", gap: 1.5 }} data-testid="relay-overrides">
      {list.map((r, i) => (
        // eslint-disable-next-line react/no-array-index-key
        <FieldRow key={i}>
          <Field span={FIELD_SPAN.half} label="받는 도메인" htmlFor={`relay-ov-domain-${i}`}>
            <TextField id={`relay-ov-domain-${i}`} size="small" fullWidth value={r.domain} placeholder="example.com"
              onChange={(e) => update(i, { domain: e.target.value })} inputProps={{ spellCheck: false }} />
          </Field>
          <Field span={FIELD_SPAN.half} label="전달 서버" htmlFor={`relay-ov-host-${i}`}
            action={(
              <Button onClick={() => onChange(list.filter((_, k) => k !== i))} aria-label={`${r.domain || "빈"} 줄 삭제`}>삭제</Button>
            )}>
            <TextField id={`relay-ov-host-${i}`} size="small" fullWidth value={r.host} placeholder="mx.example.com"
              onChange={(e) => update(i, { host: e.target.value })} inputProps={{ spellCheck: false }} />
          </Field>
        </FieldRow>
      ))}
      <Box>
        <Button disabled={list.length >= 20} onClick={() => onChange([...list, { domain: "", host: "" }])}>줄 추가</Button>
      </Box>
    </Box>
  );
}

/* 「전달 방식과 서버 이름」 구획의 로컬 릴레이 몫 — 메일 설정 폼의 값(`values.relay`)을 고친다. 고른 전달 방식의 칸만 그린다. */
export function RelayFields({ values, setRelay, relayPassword, setRelayPassword, clearRelayPassword, setClearRelayPassword,
  relayPasswordStored, relay, savedLocal, dirty }) {
  const qc = useQueryClient();
  const toast = useToast();
  const r = values.relay;
  const sh = r.smarthost || {};
  const direct = r.delivery === "direct";
  const setSmarthost = (patch) => setRelay({ smarthost: { ...sh, ...patch } });
  const dkim = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/dkim", { method: "POST", body: { selector: r.dkim_selector || null } }),
    onSuccess: (res) => {
      if (res.relay) qc.setQueryData(MAIL_RELAY_KEY, res.relay);
      qc.invalidateQueries({ queryKey: ["mail-settings"] });
      toast(res.result && res.result.message ? res.result.message : "DKIM 키를 추가했습니다.", "success");
    },
  });
  const dkimError = failureText([dkim, "DKIM 키를 추가하지 못했습니다."]);
  const keyBlocked = !savedLocal || dirty;
  const publicKey = relay && relay.dkim ? relay.dkim.public : null;
  function changeSecurity(next) {
    const patch = { security: next };
    if (Number(sh.port) === PORT_PRESETS[sh.security]) patch.port = PORT_PRESETS[next];
    setSmarthost(patch);
  }
  return (
    <>
      {/* 구성 요소 상태 줄과 그 동작(활성화 · 다시 적용 · 비활성화)은 설정 줄과 같은 묶음 폭이다(D-590) — 판 끝까지 늘면 1920 에서
          단추가 상태 낱말에서 1,400px 떨어졌다(캡처 r23-mail-2). */}
      {relay ? (
        <SettingRows width="form">
          <RelayComponentSlot relay={relay} savedLocal={savedLocal} dirty={dirty} />
        </SettingRows>
      ) : null}
      <Field label="전달 방식" labelId="relay-delivery-label">
        <ChoiceCards
          name="relay-delivery" ariaLabel="전달 방식" value={r.delivery}
          onChange={(next) => setRelay({ delivery: next })}
          options={[
            { value: "smarthost", label: "상위 SMTP 이용", description: "다른 SMTP 서버를 거쳐 보냅니다." },
            {
              /* 「고급」은 제목 옆 표지다 — 설명 아래 한 줄(`note`)로 두면 낱말 하나가 외딴 줄로 섰다(P17V 상태 캡처). */
              value: "direct", label: "인터넷으로 직접 전달", badge: "고급",
              description: "받는 쪽 메일 서버로 바로 보냅니다. DNS 설정이 필요합니다.",
            },
          ]}
        />
      </Field>
      {/* 조건 상자(D-560) - 고르기 전부터 보인다. 직접 전달은 서버 혼자 끝낼 수 없고 담당자가 있어야 한다. */}
      <Box data-testid="relay-direct-conditions">
        <Callout tone="info" compact>
          인터넷으로 직접 전달하려면 도메인 DNS 담당자가 필요합니다(SPF, DKIM, 공개 서버 이름). 역방향 이름(PTR)은 회선이나 클라우드 업체가
          넣습니다. 담당자가 없다면 상위 SMTP 이용을 고르세요. 아래 ‘DNS 인증 진단’에서 점검하면 필요한 레코드와 요청 내용이 만들어집니다.
        </Callout>
      </Box>

      {!direct ? (
        <Box component="section" aria-labelledby="relay-smarthost-title" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
          <SubHeading id="relay-smarthost-title">상위 SMTP 서버</SubHeading>
          <FieldRow>
            <Field span={FIELD_SPAN.server} label="서버 주소" htmlFor="relay-sh-host" required={values.enabled}>
              <TextField id="relay-sh-host" size="small" fullWidth value={sh.host || ""} placeholder="smtp.example.com"
                onChange={(e) => setSmarthost({ host: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field span={FIELD_SPAN.security} label="보안 연결" labelId="relay-sh-security-label">
              <TextField id="relay-sh-security" select size="small" fullWidth value={sh.security || "starttls"}
                SelectProps={{ labelId: "relay-sh-security-label" }} onChange={(e) => changeSecurity(e.target.value)}>
                {SECURITY.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
              </TextField>
            </Field>
            <Field span={FIELD_SPAN.port} label="포트" htmlFor="relay-sh-port">
              <TextField id="relay-sh-port" size="small" type="number" fullWidth value={sh.port ?? 587}
                onChange={(e) => setSmarthost({ port: e.target.value })} inputProps={{ min: 1, max: 65535 }} />
            </Field>
          </FieldRow>
          <FieldRow>
            <Field span={FIELD_SPAN.half} label="계정" htmlFor="relay-sh-username" help="계정이 없는 사내 중계라면 계정과 비밀번호를 비워 둡니다.">
              <TextField id="relay-sh-username" size="small" fullWidth value={sh.username || ""}
                onChange={(e) => setSmarthost({ username: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field span={FIELD_SPAN.half}
              label="비밀번호" htmlFor="relay-sh-password"
              help={clearRelayPassword ? "저장하면 비밀번호를 삭제합니다."
                : relayPassword ? "저장하면 이 비밀번호로 바꿉니다."
                  : relayPasswordStored ? "비밀번호가 저장돼 있습니다. 바꿀 때만 새로 넣으세요." : "비밀번호가 저장돼 있지 않습니다."}
              action={relayPasswordStored && !relayPassword ? (
                <Button onClick={() => setClearRelayPassword((v) => !v)}>{clearRelayPassword ? "삭제 취소" : "삭제"}</Button>
              ) : null}
            >
              <TextField id="relay-sh-password" size="small" type="password" fullWidth value={relayPassword}
                placeholder={relayPasswordStored ? "저장됨" : ""} disabled={!sh.username && !relayPassword}
                onChange={(e) => { setRelayPassword(e.target.value); setClearRelayPassword(false); }}
                inputProps={{ autoComplete: "new-password" }} />
            </Field>
          </FieldRow>
        </Box>
      ) : (
        <Box component="section" aria-labelledby="relay-direct-title" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
          <Box sx={{ display: "grid", gap: 0.5, minWidth: 0 }}>
            <SubHeading id="relay-direct-title">메일 서버 식별 정보</SubHeading>
            <Line>받는 쪽 메일 서버가 이 이름과 주소로 이 서버를 확인합니다.</Line>
          </Box>
          <FieldRow>
            <Field span={FIELD_SPAN.main} label="메일 서버 이름(HELO)" htmlFor="relay-helo" required={values.enabled}
              help="공개 DNS에 있는 이름이어야 합니다. 예: mail.example.com">
              <TextField id="relay-helo" size="small" fullWidth value={r.helo_name || ""} placeholder="mail.example.com"
                onChange={(e) => setRelay({ helo_name: e.target.value })} inputProps={{ spellCheck: false, autoComplete: "off" }} />
            </Field>
            <Field span={FIELD_SPAN.side} label="공인 IP" htmlFor="relay-ip" help="비우면 점검이 받는 쪽 인사말에서 읽습니다.">
              <TextField id="relay-ip" size="small" fullWidth value={r.public_ip || ""} placeholder="자동 확인"
                onChange={(e) => setRelay({ public_ip: e.target.value })} inputProps={{ spellCheck: false }} />
            </Field>
          </FieldRow>
          <SettingRows width="form">
            <SettingRow
              label="IPv4만 쓰기" controlId="relay-ipv4"
              description="이 서버에서 외부로 나가는 IPv6가 없으면 선택합니다."
              action={(
                <Checkbox id="relay-ipv4" checked={Boolean(r.ipv4_only)} onChange={(e) => setRelay({ ipv4_only: e.target.checked })}
                  slotProps={{ input: { "aria-label": "IPv4만 쓰기" } }} />
              )}
            />
            <SettingRow
              last label="DKIM 서명" controlId="relay-dkim"
              description="보내는 메일에 이 서버의 서명을 붙입니다. 받는 쪽이 정크로 분류하지 않게 돕습니다."
              action={(
                <Checkbox id="relay-dkim" checked={Boolean(r.dkim_enabled)} onChange={(e) => setRelay({ dkim_enabled: e.target.checked })}
                  slotProps={{ input: { "aria-label": "DKIM 서명" } }} />
              )}
            />
          </SettingRows>
          {r.dkim_enabled ? (
            <FieldRow columns={["min(100%, 20rem)"]}>
              <Field label="선택자" htmlFor="relay-dkim-selector"
                help={publicKey ? "키가 있습니다. ‘요청 내용과 기술 상세’의 DKIM 레코드를 도메인 DNS에 넣으세요."
                  : keyBlocked ? "저장한 뒤에 키를 추가할 수 있습니다." : "키를 추가하면 DNS에 넣을 레코드가 생깁니다."}
                action={(
                  <Button loading={dkim.isPending} disabled={keyBlocked} onClick={() => dkim.mutate()}>
                    {publicKey ? "키 확인" : "키 추가"}
                  </Button>
                )}>
                <TextField id="relay-dkim-selector" size="small" fullWidth value={r.dkim_selector || ""} placeholder="ca1"
                  onChange={(e) => setRelay({ dkim_selector: e.target.value })} inputProps={{ spellCheck: false }} />
              </Field>
            </FieldRow>
          ) : null}
          {dkimError ? <Callout tone="danger" compact>{dkimError}</Callout> : null}
        </Box>
      )}
    </>
  );
}

/* 「요청 내용과 기술 상세」의 로컬 릴레이 고급 칸 — 받는 도메인별 전달 서버(직접 전달일 때만 뜻이 있다)와 비교할 공개 DNS. 값은 같은 폼의
   「저장」에 실린다. */
export function RelayAdvancedFields({ values, setRelay }) {
  const r = values.relay;
  const direct = r.delivery === "direct";
  return (
    <>
      {direct ? (
        <Box component="section" aria-labelledby="relay-overrides-title" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
          <Box sx={{ display: "grid", gap: 0.5, minWidth: 0 }}>
            <SubHeading level={4} id="relay-overrides-title">받는 도메인별 전달 서버</SubHeading>
            <Line>이 서버의 DNS가 받는 쪽 메일 서버를 모를 때(사내 분리 DNS) 도메인마다 보낼 서버를 정합니다.</Line>
          </Box>
          <OverrideRows rows={r.transport_overrides} onChange={(rows) => setRelay({ transport_overrides: rows })} />
        </Box>
      ) : null}
      <FieldRow columns={["1fr"]}>
        <Field label="비교할 공개 DNS 서버" htmlFor="relay-resolvers"
          help="준비 점검이 이 서버의 답과 견줍니다. IPv4 주소를 쉼표로 나눠 세 개까지 넣습니다. 비우면 견주지 않습니다.">
          <TextField id="relay-resolvers" size="small" fullWidth value={(r.compare_resolvers || []).join(", ")}
            placeholder="8.8.8.8" inputProps={{ spellCheck: false }}
            onChange={(e) => setRelay({ compare_resolvers: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
        </Field>
      </FieldRow>
    </>
  );
}

/* RelayFields 안에서 쓰는 구성 요소 줄 - verify 감시는 MailScreen 의 것을 문맥으로 받는다. */
export const RelayVerifyContext = React.createContext(null);
function RelayComponentSlot(props) {
  const verify = React.useContext(RelayVerifyContext);
  return <RelayComponent {...props} verify={verify} />;
}

/* 준비 점검의 한 문장 — 「몇 개 중 몇 개 통과 · 지금 막는 것 · 누가」(D-560). ⑤ 「DNS 인증 진단」의 첫 줄이 이 문장이다. 점검 결과가 없으면 null. */
export function readinessSummary(readiness) {
  const checks = (readiness && readiness.checks) || [];
  if (!checks.length) return null;
  const requests = (readiness && readiness.requests) || [];
  const passed = checks.filter((c) => c.state === "ok").length;
  const blocking = checks.filter((c) => c.state === "fail" || c.state === "warn");
  const owners = [...new Set(requests.map((r) => r.owner))];
  let text = `준비 ${checks.length}개 중 ${passed}개를 통과했습니다.`;
  if (blocking.length) {
    text += ` 지금 막는 것은 ${blocking.map((c) => c.label).join(", ")}입니다.`;
    if (owners.length) text += ` 담당은 ${owners.join(", ")}입니다.`;
  } else {
    text += " 외부 발송 준비가 끝났습니다.";
  }
  return text;
}

/* 준비 점검 잡 하나를 끝날 때까지 지켜본다(90초 상한). 접기를 닫아도 지켜보기는 계속된다 — 그래서 이 상태는 접기 안의 부품이 아니라
   설정 탭이 든다. 끝나면 릴레이 보기(`MAIL_RELAY_KEY`)에 새 점검을 싣는다. */
export function useReadinessCheck() {
  const qc = useQueryClient();
  const [jobId, setJobId] = React.useState(null);
  const [timedOut, setTimedOut] = React.useState(false);
  const start = useMutation({
    mutationFn: () => api("/api/admin/mail/relay/check", { method: "POST", body: {} }),
    onSuccess: (res) => { setTimedOut(false); setJobId(res.job_id); },
  });
  const poll = useQuery({
    queryKey: ["mail-relay-check", jobId],
    queryFn: () => api(`/api/admin/mail/relay/check/${jobId}`),
    enabled: !!jobId && !timedOut,
    refetchInterval: (q) => (q.state.data && q.state.data.pending === false ? false : POLL_MS),
  });
  React.useEffect(() => {
    const d = poll.data;
    if (jobId && d && d.job_id === jobId && d.pending === false) {
      setJobId(null);
      if (d.readiness) qc.setQueryData(MAIL_RELAY_KEY, (old) => (old ? { ...old, readiness: d.readiness } : old));
      qc.invalidateQueries({ queryKey: MAIL_RELAY_KEY });
    }
  }, [poll.data, jobId, qc]);
  React.useEffect(() => {
    if (!jobId) return undefined;
    const timer = setTimeout(() => setTimedOut(true), CHECK_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [jobId]);
  const failed = poll.data && poll.data.pending === false && poll.data.error ? poll.data.error : null;
  return {
    start,
    running: (!!jobId && !timedOut) || start.isPending,
    timedOut,
    error: failureText([start, "점검을 시작하지 못했습니다."]) || failed,
  };
}

/* 클립보드 복사 — 실패하면 직접 고르라고 말한다(값은 화면에 그대로 있다). */
function useCopy() {
  const toast = useToast();
  return React.useCallback(async (value, what) => {
    try {
      await navigator.clipboard.writeText(value);
      toast(what, "success");
    } catch {
      toast("복사하지 못했습니다. 값을 직접 선택해 복사하세요.", "error");
    }
  }, [toast]);
}

/* ⑤ 「DNS 인증 진단」의 로컬 릴레이 몫(D-592) — 점검 한 문장(`readinessSummary`) · 최근 점검 · 서버 이름(HELO) 제안 · 항목별 상태와
   고칠 곳 · 참고 문장. 펼친 채 선다: 무엇이 막혔고 누가 고치는지가 먼저 보여야 한다. 「점검 다시 하기」는 구획 머리의 단추이고,
   요청 내용 원문과 복사할 DNS 레코드는 ⑥ 「요청 내용과 기술 상세」 접기 안이다(`RelayRequests`). 서버가 지은 문장을 그대로 쓴다. */
export function RelayDiagnosis({ relay, blocked, check }) {
  const readiness = relay && relay.readiness;
  const checks = (readiness && readiness.checks) || [];
  /* 서버가 지은 참고 문장(있는 DMARC 를 두라는 말 · `p=none` 권고)과 서버 이름(HELO) 제안(D-572). 화면은 문장을 짓지 않는다. */
  const advice = ((readiness && readiness.advice) || []).filter(Boolean);
  const helo = readiness && readiness.helo_suggestion;
  const heloChange = helo && helo.name && !helo.keep ? helo : null;
  const summary = readinessSummary(readiness);
  return (
    <Box data-testid="relay-readiness" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
      {summary ? <Typography variant="body2" sx={KO_WORD_BREAK} data-testid="relay-summary">{summary}</Typography> : null}
      <Line>{readiness && readiness.checked_at ? `최근 점검 ${fmtDateTime(readiness.checked_at)}` : "아직 점검하지 않았습니다."}</Line>
      {check.running ? <Line>외부 발송 준비 상태를 점검하는 중입니다.</Line> : null}
      {readiness && readiness.stale ? <Callout tone="info" compact>점검한 뒤 설정이 바뀌었습니다. 다시 점검하세요.</Callout> : null}
      {check.timedOut ? <Callout tone="info" compact>점검이 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 점검하세요.</Callout> : null}
      {check.error ? <Callout tone="danger" compact>{check.error}</Callout> : null}
      {heloChange ? (
        <Box data-testid="relay-helo-suggestion">
          <Callout tone="info" compact>
            {[`제안하는 메일 서버 이름(HELO)은 ${heloChange.name}입니다.`, heloChange.note,
              "담당자가 이 이름을 DNS에 넣은 뒤 ‘전달 방식과 서버 이름’의 메일 서버 이름(HELO) 칸을 바꾸세요."].filter(Boolean).join(" ")}
          </Callout>
        </Box>
      ) : null}
      {checks.length ? (
        <Box sx={{ display: "grid", gap: 1, minWidth: 0 }}>
          <SubHeading>점검 결과</SubHeading>
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid" }} data-testid="relay-checks">
            {checks.map((c) => {
              const meta = CHECK_STATE[c.state] || CHECK_STATE.unknown;
              return (
                <Box component="li" key={c.key} data-check={c.key} data-check-state={c.state}
                  sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0,1fr)", sm: "5rem 11rem minmax(0,1fr)" }, columnGap: 1.5, rowGap: 0.25,
                    py: 1.25, alignItems: "baseline", borderTop: 1, borderColor: "rule", "&:first-of-type": { borderTop: 0, pt: 0 } }}>
                  <DotLabel label={meta.label} tone={meta.tone} />
                  <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>{c.label}</Typography>
                  <Box sx={{ minWidth: 0, display: "grid", gap: 0.25 }}>
                    <Line muted={false}>{c.message}</Line>
                    {c.need ? <Line>{c.need}</Line> : null}
                    {c.where ? <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>고칠 곳: {c.where}</Typography> : null}
                    {c.technical ? (
                      <TechDetail><Typography sx={{ fontSize: FONT_SIZE.caption, wordBreak: "break-all" }}>{c.technical}</Typography></TechDetail>
                    ) : null}
                  </Box>
                </Box>
              );
            })}
          </Box>
        </Box>
      ) : null}
      {advice.length ? (
        <Box data-testid="relay-advice" sx={{ display: "grid", gap: 0.5, minWidth: 0 }}>
          <SubHeading>참고</SubHeading>
          {advice.map((line) => <Line key={line}>{line}</Line>)}
        </Box>
      ) : null}
      {!checks.length ? (
        <Line>{blocked ? "로컬 릴레이 설정을 저장한 뒤에 점검할 수 있습니다." : "점검하면 바깥으로 보내는 데 필요한 것을 한 줄씩 확인합니다."}</Line>
      ) : null}
    </Box>
  );
}

/* ⑥ 「요청 내용과 기술 상세」의 로컬 릴레이 몫(D-592) — 담당자별 요청 내용 · 복사할 DNS 레코드 · 점검의 기술 정보. 원문이 길어 처음에는
   닫힌 접기 안에 있고, 안에서는 소제목으로만 나뉜다. 요청 내용은 「요청 내용 복사」, 레코드 값은 「DNS 레코드 복사」로 가져간다. */
export function RelayRequests({ relay }) {
  const copy = useCopy();
  const readiness = relay && relay.readiness;
  if (!readiness) return null;
  const records = readiness.records || [];
  const requests = readiness.requests || [];
  const helo = readiness.helo_suggestion;
  return (
    <>
      {requests.length ? (
        <Box component="section" aria-labelledby="relay-requests-title" data-testid="relay-requests" sx={{ display: "grid", gap: 1.5, minWidth: 0 }}>
          <SubHeading id="relay-requests-title">담당자에게 요청하기</SubHeading>
          <Line>서버가 할 수 없는 일입니다. 담당자별 요청 내용을 그대로 복사해 보내고, 담당자가 넣은 뒤 점검을 다시 하세요.</Line>
          {requests.map((req) => (
            <Box key={req.owner + req.title} data-request-owner={req.owner}
              sx={{ display: "grid", gap: 0.75, p: 1.5, bgcolor: "background.inset", borderRadius: `${RADIUS.sm}px`, minWidth: 0 }}>
              <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
                <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.bodySm }}>{req.owner}</Typography>
                <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{req.title}</Typography>
                <Box sx={{ flex: 1 }} />
                <Button size="sm" onClick={() => copy(req.text, "요청 내용을 복사했습니다.")} aria-label={`${req.owner} 요청 내용 복사`}>요청 내용 복사</Button>
              </Box>
              <Line>{req.why}</Line>
              <Box component="pre" sx={{ m: 0, p: 1.25, bgcolor: "background.paper", borderRadius: `${RADIUS.sm}px`, fontSize: FONT_SIZE.caption,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", whiteSpace: "pre-wrap", wordBreak: "break-all", maxHeight: 220, overflow: "auto" }}>
                {req.text}
              </Box>
            </Box>
          ))}
        </Box>
      ) : null}
      {records.length ? (
        <Box component="section" aria-labelledby="relay-records-title" sx={{ display: "grid", gap: 1, minWidth: 0 }}>
          <SubHeading id="relay-records-title">복사할 DNS 레코드</SubHeading>
          <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1.5 }} data-testid="relay-records">
            {records.map((rec) => (
              <Box component="li" key={rec.key + rec.name}
                sx={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto", columnGap: 1.5, alignItems: "start",
                  p: 1.5, bgcolor: "background.inset", borderRadius: `${RADIUS.sm}px` }}>
                <Box sx={{ minWidth: 0, display: "grid", gap: 0.5 }}>
                  <Box sx={{ display: "flex", gap: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold }}>{rec.type}</Typography>
                    <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", wordBreak: "break-all" }}>{rec.name}</Typography>
                  </Box>
                  <Typography component="code"
                    sx={{ fontSize: FONT_SIZE.caption, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", wordBreak: "break-all" }}>
                    {rec.value}
                  </Typography>
                  {rec.request ? <Line>{rec.request}</Line> : null}
                  {rec.note ? <Line>{rec.note}</Line> : null}
                </Box>
                <Button size="sm" onClick={() => copy(rec.value, "DNS 레코드를 복사했습니다.")} aria-label={`${rec.name} ${rec.type} 레코드 복사`}>
                  DNS 레코드 복사
                </Button>
              </Box>
            ))}
          </Box>
        </Box>
      ) : null}
      <TechDetail>
        <TechRows rows={[
          ["발신 IP", readiness.egress_ip],
          ["웹 주소", readiness.web_host],
          ["웹 주소 IP", readiness.web_ip],
          ["메일 서버 이름 판정", helo ? `${helo.name || "-"} (${helo.reason}${helo.keep ? ", keep" : ""})` : null],
          ["점검한 받는 도메인", readiness.probe_domain],
        ]} />
      </TechDetail>
    </>
  );
}

/* 설정 권한이 없는 역할의 ⑤ — 상태 응답에 실린 준비 점검 요약(줄 이름과 상태)만 있다(D-592). 문장 · 레코드 · 요청 내용은 메일 설정
   권한의 화면에 있다. */
export function RelayBriefChecks({ brief }) {
  const checks = (brief && brief.checks) || [];
  if (!checks.length) return <Line>아직 점검하지 않았습니다.</Line>;
  return (
    <Box sx={{ display: "grid", gap: 1, minWidth: 0 }} data-testid="relay-brief">
      {brief.checked_at ? <Line>{`최근 점검 ${fmtDateTime(brief.checked_at)}`}</Line> : null}
      {brief.stale ? <Callout tone="info" compact>점검한 뒤 설정이 바뀌었습니다. 다시 점검해야 결과가 맞습니다.</Callout> : null}
      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", rowGap: 0.5 }}>
        {checks.map((c) => {
          const meta = CHECK_STATE[c.state] || CHECK_STATE.unknown;
          return (
            <Box component="li" key={c.key} data-check={c.key} data-check-state={c.state}
              sx={{ display: "grid", gridTemplateColumns: "5rem minmax(0,1fr)", columnGap: 1.5, alignItems: "baseline" }}>
              <DotLabel label={meta.label} tone={meta.tone} />
              <Typography sx={{ fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>{c.label}</Typography>
            </Box>
          );
        })}
      </Box>
      <Line>점검 문장과 담당자에게 보낼 요청 내용은 메일 설정 권한이 있는 사람이 볼 수 있습니다.</Line>
    </Box>
  );
}

/* 설정 권한이 없는 역할이 보는 한 줄 — 전달 방식만. 칸 값은 설정 탭의 읽기 전용 줄이 그린다. */
export function RelayReadOnly({ summary }) {
  const relay = summary && summary.relay ? summary.relay : {};
  return <Line muted={false}>{relay.delivery === "direct" ? "인터넷으로 직접 전달합니다." : "상위 SMTP 서버를 거쳐 보냅니다."}</Line>;
}

export function useRelayQuery(enabled) {
  return useQuery({ queryKey: MAIL_RELAY_KEY, queryFn: () => api("/api/admin/mail/relay"), enabled, retry: false });
}
