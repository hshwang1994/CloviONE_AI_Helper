import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime } from "../../lib/format.js";
import { Callout, Card, DotLabel, HeadRow, TechDetail } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";

/* 메일 상태 면 (계획 M1 · M2, D-546) — 메일 화면에서 카드는 이것 하나다(F7 카드 규율: 독립된 상태).
 *
 * 대시보드가 아니다: 상태 점과 낱말(사용 안 함 · 설정 덜 됨 · 확인 전 · 정상 · 발송 실패), 한 문장, 최근 확인 시각, 그리고 마지막 연결
 * 확인이 지난 단계의 이름과 결과(DNS 조회 · 서버 연결 · 보안 연결 · 인증 · 보내는 사람 · 받는 사람 중 지금 방식이 지나는 것). 실패면
 * 그 단계만 오류색이고 까닭 한 문장이 선다. 서버 응답 원문 · 실패 종류 코드는 「기술 정보」 안에만 둔다. 상태별 수는 발송 기록 탭이
 * 말한다.
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

/* 로컬 릴레이 방식일 때만 서는 두 줄(D-551) — 구성 요소가 동작하는가, 그리고 최근 바깥 전달이 어떻게 됐는가. 「접수」와 「전달」을 섞지
   않는다(D-555): 앱 → 릴레이는 위의 단계 줄이 말하고, 받는 쪽까지는 이 줄이 말한다. */
function RelayLines({ relay }) {
  const component = relay.component || {};
  const outer = relay.outer;
  const cell = { m: 0, minWidth: 0, display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" };
  return (
    <Box component="dl" aria-label="로컬 릴레이" data-testid="relay-lines"
      sx={{ m: 0, display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", columnGap: 1.5, rowGap: 0.75 }}>
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

export function MailStatusCard({ health, summary, relay = null, checking = false, timedOut = false }) {
  const h = health || {};
  const tone = STATE_TONE[h.kind] || "neutral";
  const failed = (h.stages || []).find((s) => s.state === "failed");
  const checked = h.checked_at ? `최근 확인 ${fmtDateTime(h.checked_at)}` : "아직 확인하지 않음";
  const label = checking ? "확인하는 중" : (h.label || "알 수 없음");
  const message = checking ? "메일 서버 연결을 확인하고 있습니다." : h.message;
  const problemList = h.state === "unconfigured" && (h.problems || []).length > 1 ? h.problems : null;
  return (
    <Card stack data-testid="mail-state" aria-label="메일 발송 상태">
      <HeadRow
        action={(
          <Typography component="span" sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", whiteSpace: "nowrap" }}>
            {checked}
          </Typography>
        )}
      >
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.25, flexWrap: "wrap", minWidth: 0 }}>
          <DotLabel label={label} tone={checking ? "info" : tone} strong data-testid="mail-state-label" />
          {message && !(h.state === "failing" && !checking) ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{message}</Typography>
          ) : null}
        </Box>
      </HeadRow>
      {h.state === "failing" && !checking ? (
        <Callout tone="danger" compact>
          {failed && failed.detail ? failed.detail : h.message}
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
      {checking ? null : <StageList stages={h.stages} />}
      {relay ? <RelayLines relay={relay} /> : null}
      <TechDetail>
        <Box sx={{ display: "grid", gap: 0.5 }}>
          <TechLine name="상태 코드" value={h.state} />
          <TechLine name="실패 종류" value={h.failure_kind} />
          <TechLine name="실패 단계" value={h.stage} />
          <TechLine name="연속 실패" value={h.consecutive_failures ? `${h.consecutive_failures}회` : null} />
          <TechLine name="최근 성공" value={h.last_success_at ? fmtDateTime(h.last_success_at) : null} />
          <TechLine name="메일 서버" value={relay ? "127.0.0.1:2525(로컬 릴레이)" : (summary && summary.host ? `${summary.host}:${summary.port}` : null)} />
        </Box>
      </TechDetail>
    </Card>
  );
}

function TechLine({ name, value }) {
  if (value == null || value === "") return null;
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "8rem minmax(0,1fr)", gap: 1, minWidth: 0 }}>
      <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{name}</Typography>
      <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.regular, wordBreak: "break-all" }}>
        {value}
      </Typography>
    </Box>
  );
}

export default MailStatusCard;
