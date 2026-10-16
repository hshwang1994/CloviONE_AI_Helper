import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime, fmtListStamp } from "../../lib/format.js";
import {
  Button, Callout, Card, DotLabel, FACTS_ROW_SX, SectionHeader, TechDetail, TechRows,
} from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { MailSteps } from "./MailSteps.jsx";

/* ① 발송 상태 (계획 M1 · M2 · M4, D-546 · D-560 · D-574 · D-592) — 메일 설정 탭의 첫 구획이고 독립된 판이다(F7 카드 규율: 독립된 상태).
 *
 * 상태 줄 넷이 서로 다른 사실을 따로 말한다(D-592):
 *   메일 발송 가능     마지막 연결 확인의 결과 — 이 서버가 메일 서버에 붙어 보낼 수 있는가
 *   SMTP 수락          최근 시험 메일을 메일 서버가 접수했는가(로컬 릴레이면 받는 쪽 서버까지 넘겼는가)
 *   DNS 인증           SPF · DKIM · 역방향 이름(PTR) · 메일 서버 이름(HELO) 점검 — 인터넷으로 직접 전달할 때만 이 서버가 점검한다
 *   받은 편지함 확인   사람이 받은 편지함에서 직접 확인하고 기록한 결과
 * SMTP 수락은 받은 편지함에 들어갔다는 뜻이 아니고(D-555), 발송이 정상이어도 DNS 인증은 따로 실패할 수 있다. 그래서 한 낱말로 합치지
 * 않는다. 점검하지 않은 것은 「점검 대상 아님」 · 「점검 전」이라고 쓰고 통과로 세지 않는다. 로컬 릴레이면 구성 요소와 최근 바깥 전달
 * 두 줄이 같은 목록에 더해진다(D-551).
 *
 * 그 아래 「지금 할 일」 한 줄과 [이동], 설정 단계 목록(`MailSteps`)이 선다. 단계가 다 끝났으면 목록 대신 한 문장만 남는다 — 설정을
 * 마친 뒤에는 일곱 칸이 첫 화면을 차지할 까닭이 없다. 마지막 연결 확인의 단계 줄은 실패했을 때만 보인다(어디서 막혔는지가 그때
 * 필요하다). 서버 응답 원문 · 실패 종류 코드 · 상태 코드는 「기술 정보」 안에만 둔다.
 */

export const STATE_TONE = { neutral: "neutral", warn: "warn", info: "info", ok: "ok", danger: "danger" };
const STAGE_STATE = {
  ok: { label: "정상", tone: "ok" },
  failed: { label: "실패", tone: "danger" },
  skipped: { label: "건너뜀", tone: "neutral" },
  not_reached: { label: "확인 안 됨", tone: "neutral" },
};

const COMPONENT_TONE = { ready: "neutral", running: "ok", stopped: "danger", not_installed: "warn", foreign: "warn", unavailable: "neutral" };
const OUTER_TONE = { delivered: "ok", deferred: "warn", bounced: "danger", expired: "danger" };

/* 시험 메일 한 통의 짧은 낱말 — 발송 기록 탭의 상태 이름과 같은 말을 쓴다. 바깥 전달을 추적하는 방식(로컬 릴레이)이면 받는 쪽까지의
   결과가 접수보다 앞선다. 「도착」 · 「받았습니다」라고 말하지 않는다(D-555). */
const TEST_WORD = {
  queued: ["보낼 차례", "info"], retrying: ["다시 보낼 차례", "info"], sent: ["서버가 접수함", "ok"], failed: ["보내지 못함", "danger"],
  unconfigured: ["설정이 끝나지 않음", "neutral"], cancelled: ["보내지 않음", "neutral"], superseded: ["보내지 않음", "neutral"],
};
const REMOTE_WORD = {
  delivered: ["수신측 서버로 전달함", "ok"], deferred: ["전달을 다시 시도하는 중", "warn"],
  bounced: ["수신측이 거부함", "danger"], expired: ["전달 기한이 지남", "danger"],
};

/** 시험 메일 한 통의 낱말과 톤. 없으면 null. */
export function testWord(test) {
  if (!test) return null;
  if (test.status === "sent" && test.remote_status && REMOTE_WORD[test.remote_status]) {
    const [label, tone] = REMOTE_WORD[test.remote_status];
    return { label, tone };
  }
  const [label, tone] = TEST_WORD[test.status] || [test.status, "neutral"];
  return { label, tone };
}

function methodWord(summary) {
  if (!summary || !summary.mode) return null;
  if (summary.mode === "local_relay") {
    const delivery = summary.relay && summary.relay.delivery;
    return delivery === "direct" ? "로컬 릴레이(직접 전달)" : "로컬 릴레이(상위 SMTP)";
  }
  return summary.mode === "external" ? "외부 SMTP" : null;
}

/* 「DNS 인증」 줄이 세는 준비 점검 줄 — 받는 쪽이 이 서버와 보내는 도메인을 믿게 하는 DNS 쪽 항목이다. 구성 요소 · 포트 · 앱 연결 같은
   동작 점검은 「메일 발송 가능」 · 「로컬 릴레이」 줄의 몫이라 여기서 세지 않는다. */
const DNS_AUTH_KEYS = new Set([
  "sender_domain_public", "spf", "dkim", "dmarc", "ptr_fcrdns", "helo_dns", "egress_vs_web", "sender_alignment",
]);

/** 「DNS 인증」 줄의 낱말 · 톤 · 덧붙임. 인터넷으로 직접 전달할 때만 이 서버가 점검한다 — 점검하지 않은 것을 통과로 쓰지 않는다. */
export function dnsAuthLine(summary, relay) {
  const mode = summary && summary.mode;
  const delivery = (relay && relay.delivery) || (summary && summary.relay && summary.relay.delivery);
  if (mode !== "local_relay") return { word: "점검 대상 아님", tone: "neutral", rest: "외부 SMTP 서비스의 DNS 설정을 따릅니다." };
  if (delivery !== "direct") return { word: "점검 대상 아님", tone: "neutral", rest: "상위 SMTP 서버의 DNS 설정을 따릅니다." };
  const readiness = relay && relay.readiness;
  const checks = ((readiness && readiness.checks) || []).filter((c) => DNS_AUTH_KEYS.has(c.key));
  if (!checks.length) return { word: "점검 전", tone: "neutral", rest: "아래 ‘DNS 인증 진단’에서 점검할 수 있습니다." };
  if (readiness.stale) return { word: "다시 점검 필요", tone: "warn", rest: "점검한 뒤 설정이 바뀌었습니다." };
  const passed = checks.filter((c) => c.state === "ok").length;
  const failing = checks.filter((c) => c.state === "fail");
  const unsure = checks.filter((c) => c.state !== "ok" && c.state !== "fail");
  const open = [...failing, ...unsure].map((c) => c.label).join(", ");
  const count = `${checks.length}개 중 ${passed}개 통과`;
  if (failing.length) return { word: "조치 필요", tone: "danger", rest: `${count}, 확인할 항목: ${open}` };
  if (unsure.length) return { word: "확인 필요", tone: "warn", rest: `${count}, 확인할 항목: ${open}` };
  return { word: "통과", tone: "ok", rest: `${checks.length}개 항목 모두 통과` };
}

/* 「받은 편지함 확인」 줄 — 사람이 남긴 기록만 말한다. 최근 시험 메일이 아닌 앞선 메일의 기록이면 그 사실을 붙이고 톤을 낮춘다. */
function inboxLine(inbox, test) {
  if (!inbox) return { word: "기록 없음", tone: "neutral", rest: null };
  const older = Boolean(test && inbox.delivery_id !== test.id);
  const rest = [inbox.at ? fmtListStamp(inbox.at) : null, older ? "이전 시험 메일" : null].filter(Boolean).join(", ");
  return {
    word: inbox.received ? "받은 편지함에서 확인함" : "받은 편지함에 없음",
    tone: older ? "neutral" : (inbox.received ? "ok" : "warn"),
    rest: rest || null,
  };
}

/* 상태 줄 목록 — 이름 열과 값 열의 두 칸 격자(좁으면 한 칸으로 쌓인다). 값은 점 + 낱말과 그 뒤의 덧붙임이다. */
function StatusLines({ rows }) {
  return (
    <Box
      component="dl" aria-label="메일 발송 상태" data-testid="mail-status-lines"
      sx={{
        m: 0, minWidth: 0, display: "grid", columnGap: 2, rowGap: { xs: 0.25, sm: 0.75 },
        gridTemplateColumns: { xs: "minmax(0,1fr)", sm: "9rem minmax(0,1fr)" },
      }}
    >
      {rows.map((row) => (
        <React.Fragment key={row.key}>
          <Typography component="dt" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", pt: { xs: 0.75, sm: 0 } }}>
            {row.label}
          </Typography>
          <Box
            component="dd" data-status-line={row.key} data-testid={row.testid}
            sx={{ m: 0, minWidth: 0, display: "flex", alignItems: "baseline", columnGap: 1, rowGap: 0.25, flexWrap: "wrap" }}
          >
            <DotLabel label={row.word} tone={row.tone} strong={row.strong} data-testid={row.labelTestId} />
            {row.rest ? <Typography component="span" variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{row.rest}</Typography> : null}
          </Box>
        </React.Fragment>
      ))}
    </Box>
  );
}

/* 연결 확인의 단계 줄 — 발송이 실패했을 때만 선다. 어느 단계에서 멈췄는지가 그때 고칠 자리를 알려 준다. */
function StageList({ stages }) {
  const shown = (stages || []).filter((s) => s.state !== "skipped");
  if (!shown.length) return null;
  return (
    <Box
      component="dl" aria-label="연결 확인 단계" data-testid="mail-stages"
      sx={{ m: 0, display: "flex", flexWrap: "wrap", columnGap: 3, rowGap: 0.75, minWidth: 0 }}
    >
      {shown.map((s) => {
        const meta = STAGE_STATE[s.state] || STAGE_STATE.not_reached;
        return (
          <Box key={s.key} data-stage={s.key} data-stage-state={s.state}
            sx={{ display: "inline-flex", alignItems: "baseline", gap: 0.75, minWidth: 0 }}>
            <Typography component="dt" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{s.label}</Typography>
            <Box component="dd" sx={{ m: 0 }}>
              <DotLabel label={meta.label} tone={meta.tone} />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

/* 「지금 할 일」 한 줄(D-560) — 서버가 고른 다음 단계의 문장과 그 자리로 가는 [이동]. 제목 없이 한 줄(굵은 꼬리표 + 문장)이다 — 동작이
   든 상자의 계약(D-528: 아이콘 · 첫 줄 · 동작이 한 가운데선)은 제목 줄을 세지 않는다. 막힌 단계면 주의 톤이다. */
function NextStep({ next, onGo }) {
  return (
    <Callout
      tone={next.state === "blocked" ? "warn" : "info"} className="k-mail-next"
      action={onGo ? <Button size="sm" variant="primary" onClick={() => onGo(next)}>이동</Button> : null}
    >
      <Typography component="span" variant="body2" sx={KO_WORD_BREAK}>
        <Box component="strong" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 0.75 }}>지금 할 일</Box>
        {next.hint || next.label}
      </Typography>
    </Callout>
  );
}

export function MailStatusCard({
  health, summary, relay = null, checking = false, timedOut = false, progress = null, latestTest = null, inbox = null, onGo,
}) {
  const h = health || {};
  const tone = STATE_TONE[h.kind] || "neutral";
  const failing = h.state === "failing" && !checking;
  const failed = (h.stages || []).find((s) => s.state === "failed");
  const checked = h.checked_at ? `최근 확인 ${fmtDateTime(h.checked_at)}` : "아직 확인하지 않음";
  const problemList = h.state === "unconfigured" && (h.problems || []).length > 1 ? h.problems : null;
  const steps = progress && Array.isArray(progress.steps) ? progress.steps : [];
  const next = progress && progress.next ? progress.next : null;
  const allDone = steps.length > 0 && steps.every((s) => s.state === "done");
  const dns = dnsAuthLine(summary, relay);
  const box = inboxLine(inbox, latestTest);
  const test = testWord(latestTest);
  const component = relay ? relay.component || {} : null;
  const outer = relay ? relay.outer : null;
  const rows = [
    {
      key: "send", label: "메일 발송 가능", labelTestId: "mail-state-label", strong: true,
      word: checking ? "확인하는 중" : (h.label || "알 수 없음"), tone: checking ? "info" : tone,
      rest: checking ? "메일 서버 연결을 확인하고 있습니다." : (failing ? null : h.message),
    },
    component ? {
      key: "relay", label: "로컬 릴레이", testid: "relay-component-line",
      word: component.label || "확인할 수 없음", tone: COMPONENT_TONE[component.state] || "neutral",
      rest: component.state !== "running" ? component.message : null,
    } : null,
    {
      key: "smtp", label: "SMTP 수락",
      word: test ? test.label : "시험 메일 없음", tone: test ? test.tone : "neutral",
      rest: latestTest ? fmtListStamp(latestTest.sent_at || latestTest.created_at) : null,
    },
    relay ? {
      key: "outer", label: "최근 바깥 전달", testid: "relay-outer",
      word: outer ? outer.label : "결과 없음", tone: outer ? OUTER_TONE[outer.status] || "neutral" : "neutral",
      rest: outer ? [outer.sentence, outer.at ? `최근 ${fmtDateTime(outer.at)}` : null].filter(Boolean).join(" ") || null
        : "아직 바깥 전달 결과가 없습니다.",
    } : null,
    { key: "dns", label: "DNS 인증", testid: "mail-dns-line", word: dns.word, tone: dns.tone, rest: dns.rest },
    { key: "inbox", label: "받은 편지함 확인", testid: "mail-inbox-line", word: box.word, tone: box.tone, rest: box.rest },
  ].filter(Boolean);
  const stageText = (h.stages || []).filter((s) => s.state !== "skipped")
    .map((s) => `${s.label} ${(STAGE_STATE[s.state] || STAGE_STATE.not_reached).label}`).join(", ");
  return (
    <Card stack data-testid="mail-state" aria-label="메일 발송 상태">
      {/* 「최근 확인」은 단추가 아니라 글이라 머리 줄 오른쪽 끝에 글로 선다. */}
      <SectionHeader
        component="h2" title="발송 상태" spacing="none"
        action={(
          <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", whiteSpace: "nowrap" }}>
            {checked}
          </Typography>
        )}
      />
      <StatusLines rows={rows} />
      {failing ? (
        <Callout tone="danger" compact>
          {failed && failed.detail ? failed.detail : h.message}
          {/* 실패 종류의 흔한 원인 한 문장(P4 ③) - 서버 응답 원문은 기술 정보 안이다. */}
          {h.hint ? <Typography component="span" variant="body2" sx={{ display: "block", mt: 0.5, ...KO_WORD_BREAK }} data-testid="mail-failure-hint">{h.hint}</Typography> : null}
        </Callout>
      ) : null}
      {failing ? <StageList stages={h.stages} /> : null}
      {problemList ? (
        <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
          {problemList.map((p) => (
            <li key={p}><Typography variant="body2" sx={KO_WORD_BREAK}>{p}</Typography></li>
          ))}
        </Box>
      ) : null}
      {timedOut ? (
        <Callout tone="info" compact>확인이 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 확인하세요.</Callout>
      ) : null}
      {next ? <NextStep next={next} onGo={onGo} /> : null}
      {allDone ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK} data-testid="mail-progress-complete">
          일곱 단계가 모두 끝났습니다. 설정을 바꾸면 연결 확인부터 다시 합니다.
        </Typography>
      ) : <MailSteps steps={steps} quietKey={next ? next.key : null} />}
      {/* 「기술 정보」는 판 끝 오른쪽에 접힌 채 선다(`FACTS_ROW_SX`). */}
      <Box sx={FACTS_ROW_SX}>
        <Box sx={{ flex: "1 1 auto", minWidth: 0 }} />
        <TechDetail trailing>
          <TechRows
            labelWidth="8rem"
            rows={[
              ["상태 코드", h.state],
              ["실패 종류", h.failure_kind],
              ["실패 단계", h.stage],
              ["연결 확인 단계", !failing && stageText ? stageText : null],
              ["연속 실패", h.consecutive_failures ? `${h.consecutive_failures}회` : null],
              ["최근 성공", h.last_success_at ? fmtDateTime(h.last_success_at) : null],
              ["발송 방식", methodWord(summary)],
              ["메일 서버", relay ? "127.0.0.1:2525(로컬 릴레이)" : (summary && summary.host ? `${summary.host}:${summary.port}` : null)],
              ["보내는 이름", summary && summary.from_name ? summary.from_name : null],
              ["시험 메일 받는 주소", latestTest ? latestTest.to_email : null],
              ["시험 메일 상태 코드", latestTest ? [latestTest.status, latestTest.remote_status].filter(Boolean).join(", ") : null],
              ["시험 메일 시각", latestTest ? fmtDateTime(latestTest.sent_at || latestTest.created_at) : null],
              ["받은 편지함 기록 시각", inbox && inbox.at ? fmtDateTime(inbox.at) : null],
            ]}
          />
        </TechDetail>
      </Box>
    </Card>
  );
}

export default MailStatusCard;
