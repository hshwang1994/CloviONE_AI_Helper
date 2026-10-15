import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime, fmtListStamp } from "../../lib/format.js";
import { Button, Callout, Card, DotLabel, FACTS_ROW_SX, HeadRow, MetaBar, TechDetail, TechRows } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* 연결 상태 면 (계획 A3, D-539 · D-558) — 화면에서 카드는 이것 하나다(F7 카드 규율: 독립된 상태).
 *
 * 대시보드가 아니다: 상태 점과 낱말, 한 문장, **서버가 준 사실 줄**(`facts[]` — 자격이 없으면 제공자 · 인증 방식뿐이고 모델 ·
 * 최근 성공 · 능력 줄은 없다), 「다음 할 일」 한 문장과 그 자리로 가는 단추(`next`), [지금 확인]. 낱말과 문장은 서버가 정한다
 * (`state.display` — 초기 설정의 AI 항목과 같은 함수). 이 화면은 어떤 사실도 지어내지 않는다 — 「문서 검색 사용 가능」 같은
 * 고정 문구를 그리지 않는다. 토큰 만료 · 프록시 · 계정 주소 · 색인 수 · 도구 시험의 원시 값은 「기술 정보」 안에만 둔다.
 */

export const KIND_TONE = { ok: "ok", info: "info", warn: "warn", error: "danger", muted: "neutral" };
/* 「다음 할 일」 단추의 글. 자리는 서버의 `next.action` 이고 모양은 화면이 정한다. */
export const NEXT_BUTTON = {
  configure: "제공자 정하기",
  api_key: "API 키 넣기",
  login: "ChatGPT 로그인",
  paste: "주소 붙여 넣기",
  model: "모델 고르기",
  enable: "AI 사용 켜기",
  verify: "지금 확인",
};

/* 띠에는 짧은 꼴(「3분 전」 · 「8월 24일」)을 쓴다 — 「2026. 10. 2. 오전 11:00」 둘이 띠를 1366 에서 두 줄로 접어 첫 폼 칸을 밀었다(P17V).
   정확한 시각은 「기술 정보」에 있다. */
function when(iso) {
  return iso ? fmtListStamp(iso) : "아직 없음";
}

export function AiStatusCard({ data, onVerify, onNext, verifying = false, timedOut = false }) {
  const state = data.state || {};
  const display = state.display || { label: state.label || "알 수 없음", kind: "muted", message: state.message || "" };
  const config = data.config || {};
  const credentials = data.credentials || { ready: false };
  const next = data.next || null;
  const technical = data.technical || {};
  const index = data.index;
  const facts = (data.facts || []).map((f) => ({
    key: f.key, label: f.label, value: f.kind === "time" ? when(f.value) : f.value,
  }));
  const canVerify = Boolean(credentials.ready && config.model);
  const blocked = display.kind === "error" || display.kind === "warn";
  /* 다음 할 일이 상태 문장과 같은 말이면 머리에는 낱말만 둔다 - 같은 문장을 두 번 쓰지 않는다. */
  const headMessage = !blocked && display.message && !(next && next.label === display.message) ? display.message : null;
  /* 「지금 확인」은 머리의 단추 하나다 - 다음 할 일이 확인이면 같은 단추를 한 번 더 그리지 않는다. */
  const nextButton = next && onNext && next.action !== "verify" && NEXT_BUTTON[next.action] ? NEXT_BUTTON[next.action] : null;
  return (
    <Card stack data-testid="ai-state" aria-label="AI 연결 상태">
      <HeadRow
        action={(
          <Button onClick={onVerify} loading={verifying} disabled={!canVerify || verifying}>
            지금 확인
          </Button>
        )}
      >
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.25, flexWrap: "wrap", minWidth: 0 }}>
          <DotLabel label={display.label} tone={KIND_TONE[display.kind] || "neutral"} strong data-testid="ai-state-label" />
          {headMessage ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{headMessage}</Typography>
          ) : null}
        </Box>
      </HeadRow>
      {blocked && display.message ? (
        <Callout tone={display.kind === "error" ? "danger" : "warn"} compact>{display.message}</Callout>
      ) : null}
      {next ? (
        <Callout
          tone="info" compact title="다음 할 일" className="k-ai-next"
          action={nextButton ? (
            <Button size="sm" variant="primary" onClick={() => onNext(next.action)}>
              {nextButton}
            </Button>
          ) : null}
        >
          {next.label}
        </Callout>
      ) : null}
      {timedOut ? (
        <Callout tone="info" compact>확인이 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 확인하세요.</Callout>
      ) : null}
      {/* 칸마다 이름과 값이 한 줄에 붙는 띠다 — 상태 면은 짧아야 한다(F7, 높이 상한 약 120px). 「기술 정보」는 그 띠 끝에 접혀 붙는다. */}
      <Box sx={FACTS_ROW_SX}>
        {facts.length ? (
          <MetaBar strip items={facts} ariaLabel="지금 쓰는 연결" sx={{ flex: "1 1 auto", minWidth: 0 }} />
        ) : (
          <Box sx={{ flex: "1 1 auto", minWidth: 0 }} />
        )}
        <TechDetail trailing>
          <TechRows
            rows={[
              ["연결 상태 코드", state.state],
              ["최근 성공 시각", state.last_success_at ? fmtDateTime(state.last_success_at) : null],
              ["최근 확인 시각", state.checked_at ? fmtDateTime(state.checked_at) : null],
              ["까닭 코드", technical.reason_code],
              ["연속 실패", technical.consecutive_failures ? `${technical.consecutive_failures}회` : null],
              ["프록시", technical.proxy],
              ["연결한 계정", technical.account_label],
              ["토큰 만료", technical.access_expires_at ? fmtDateTime(technical.access_expires_at) : null],
              ["갱신 토큰 만료", technical.refresh_expires_at ? fmtDateTime(technical.refresh_expires_at) : null],
              ["도구 시험 모델", technical.tools_checked_model],
              ["도구 시험 시각", (data.capabilities || {}).checked_at ? fmtDateTime(data.capabilities.checked_at) : null],
              ["색인 문서", index ? `${index.documents ?? 0}건, 조각 ${index.chunks ?? 0}개` : null],
              ["의미 검색 모델", index && index.semantic != null ? (index.semantic ? "있음" : "없음(낱말로 찾습니다)") : null],
              ["요금제 사용량", data.chatgpt && data.chatgpt.manage_usage_url && config.auth_method === "chatgpt" ? data.chatgpt.manage_usage_url : null],
            ]}
          />
        </TechDetail>
      </Box>
    </Card>
  );
}

export default AiStatusCard;
