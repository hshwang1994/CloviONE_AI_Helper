import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime, fmtListStamp } from "../../lib/format.js";
import {
  Button, Callout, Card, DotLabel, FACTS_ROW_SX, MetaBar, SectionHeader, TechDetail, TechRows,
} from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { MailSteps } from "./MailSteps.jsx";

/* ① 상태 요약 (계획 M1 · M2 · M4, D-546 · D-560 · D-574) — 메일 설정 탭의 첫 구획이고 독립된 판이다(F7 카드 규율: 독립된 상태).
 *
 * 대시보드가 아니다: 상태 점과 낱말(사용 안 함 · 설정 덜 됨 · 확인 전 · 정상 · 발송 실패), 한 문장, 최근 확인 시각. 그 아래 「지금 할 일」
 * 한 줄과 [이동](예전 진행 띠의 자리에서 옮겼다), 일곱 단계 목록(`MailSteps`), 마지막 연결 확인이 지난 단계의 이름과 결과, 사실 띠(보내는
 * 방법 · 보내는 주소 · 최근 시험 메일 · 받은 편지함)와 접힌 「기술 정보」가 선다. 실패면 그 단계만 오류색이고 까닭 한 문장이 선다.
 *
 * 사실을 지어내지 않는다: 값을 모르는 사실 칸은 띠에서 빠진다. 「최근 시험 메일」은 접수까지만 말한다(D-555 — 「도착」이 아니다).
 * 서버 응답 원문 · 실패 종류 코드 · 상태 코드는 「기술 정보」 안에만 둔다.
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

/* 사실 띠 — 값이 없는 칸은 빠진다(모르는 것을 「-」로 채우지 않는다). 시험 메일과 받은 편지함은 「없다」도 사실이라 그 말을 쓴다. */
export function mailFacts({ summary, latestTest, inbox }) {
  const word = testWord(latestTest);
  const items = [
    { key: "method", label: "발송 방식", value: methodWord(summary) },
    { key: "from", label: "보내는 주소", value: (summary && summary.from_address) || null },
    {
      key: "test", label: "최근 시험 메일",
      value: word ? `${word.label}, ${fmtListStamp(latestTest.sent_at || latestTest.created_at)}` : "아직 없음",
    },
    {
      key: "inbox", label: "받은 편지함",
      value: inbox
        ? `${inbox.received ? "받았다고 기록함" : "받지 못했다고 기록함"}${latestTest && inbox.delivery_id !== latestTest.id ? "(이전 시험 메일)" : ""}`
        : "기록 없음",
    },
  ];
  return items.filter((it) => it.value != null && it.value !== "");
}

/* 로컬 릴레이 방식일 때만 서는 두 줄(D-551) — 구성 요소가 동작하는가, 그리고 최근 바깥 전달이 어떻게 됐는가. 「접수」와 「전달」을 섞지
   않는다(D-555): 앱 → 릴레이는 위의 단계 줄이 말하고, 받는 쪽까지는 이 줄이 말한다. */
function RelayLines({ relay }) {
  const component = relay.component || {};
  const outer = relay.outer;
  const cell = { m: 0, minWidth: 0, display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" };
  return (
    <Box component="dl" aria-label="로컬 릴레이" data-testid="relay-lines"
      sx={{ m: 0, display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", columnGap: 1.5, rowGap: 0.75, minWidth: 0 }}>
      <Typography component="dt" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>로컬 릴레이</Typography>
      <Box component="dd" sx={cell}>
        <DotLabel label={component.label || "확인할 수 없음"} tone={COMPONENT_TONE[component.state] || "neutral"} />
        {component.state !== "running" && component.message ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{component.message}</Typography>
        ) : null}
      </Box>
      <Typography component="dt" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>바깥 전달</Typography>
      <Box component="dd" sx={cell} data-testid="relay-outer">
        {outer ? (
          <>
            <DotLabel label={outer.label} tone={OUTER_TONE[outer.status] || "neutral"} />
            {outer.sentence ? <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{outer.sentence}</Typography> : null}
            {outer.at ? <Typography variant="body2" color="text.secondary">{`최근 ${fmtDateTime(outer.at)}`}</Typography> : null}
          </>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>아직 바깥 전달 결과가 없습니다.</Typography>
        )}
      </Box>
    </Box>
  );
}

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
  const failed = (h.stages || []).find((s) => s.state === "failed");
  const checked = h.checked_at ? `최근 확인 ${fmtDateTime(h.checked_at)}` : "아직 확인하지 않음";
  const label = checking ? "확인하는 중" : (h.label || "알 수 없음");
  const message = checking ? "메일 서버 연결을 확인하고 있습니다." : h.message;
  const problemList = h.state === "unconfigured" && (h.problems || []).length > 1 ? h.problems : null;
  const steps = progress && Array.isArray(progress.steps) ? progress.steps : [];
  const next = progress && progress.next ? progress.next : null;
  const facts = mailFacts({ summary, latestTest, inbox });
  return (
    <Card stack data-testid="mail-state" aria-label="메일 발송 상태">
      {/* 「최근 확인」은 단추가 아니라 글이라 머리 줄 오른쪽 끝에 글로 선다. */}
      <SectionHeader
        component="h2" title="상태 요약" spacing="none"
        action={(
          <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", whiteSpace: "nowrap" }}>
            {checked}
          </Typography>
        )}
      />
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.25, flexWrap: "wrap", minWidth: 0 }}>
        <DotLabel label={label} tone={checking ? "info" : tone} strong data-testid="mail-state-label" />
        {message && !(h.state === "failing" && !checking) ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{message}</Typography>
        ) : null}
      </Box>
      {h.state === "failing" && !checking ? (
        <Callout tone="danger" compact>
          {failed && failed.detail ? failed.detail : h.message}
          {/* 실패 종류의 흔한 원인 한 문장(P4 ③) - 서버 응답 원문은 기술 정보 안이다. */}
          {h.hint ? <Typography component="span" variant="body2" sx={{ display: "block", mt: 0.5, ...KO_WORD_BREAK }} data-testid="mail-failure-hint">{h.hint}</Typography> : null}
        </Callout>
      ) : null}
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
      {!next && steps.length ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK} data-testid="mail-progress-complete">
          일곱 단계가 모두 끝났습니다. 설정을 바꾸면 연결 확인부터 다시 합니다.
        </Typography>
      ) : null}
      <MailSteps steps={steps} quietKey={next ? next.key : null} />
      {!checking ? <StageList stages={h.stages} /> : null}
      {relay ? <RelayLines relay={relay} /> : null}
      {/* 사실 띠 끝에 「기술 정보」가 접힌 채 붙는다(`FACTS_ROW_SX`). */}
      <Box sx={FACTS_ROW_SX}>
        {facts.length ? (
          <MetaBar strip items={facts} ariaLabel="메일 발송 사실" sx={{ flex: "1 1 auto", minWidth: 0 }} />
        ) : (
          <Box sx={{ flex: "1 1 auto", minWidth: 0 }} />
        )}
        <TechDetail trailing>
          <TechRows
            labelWidth="8rem"
            rows={[
              ["상태 코드", h.state],
              ["실패 종류", h.failure_kind],
              ["실패 단계", h.stage],
              ["연속 실패", h.consecutive_failures ? `${h.consecutive_failures}회` : null],
              ["최근 성공", h.last_success_at ? fmtDateTime(h.last_success_at) : null],
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
