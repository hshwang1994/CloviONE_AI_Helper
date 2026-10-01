import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime } from "../../lib/format.js";
import { Button, Callout, Card, DotLabel, HeadRow, MetaBar, TechDetail } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* 연결 상태 면 (계획 A3, D-539) — 화면에서 카드는 이것 하나다(F7 카드 규율: 독립된 상태).
 *
 * 대시보드가 아니다: 상태 점과 낱말, 한 문장, 지금 쓰는 연결(제공자 · 인증 방식 · 모델), 최근 성공 · 최근 확인, 문서 검색과
 * 도구 호출 두 줄, [지금 확인]. 낱말과 문장은 서버가 정한다(`state.display` — 초기 설정의 AI 항목과 같은 함수). 정상이 아니면
 * 까닭 한 문장이 메시지 상자로 선다. 토큰 만료 · 프록시 · 계정 주소 · 색인 수 · 도구 시험의 원시 값은 「기술 정보」 안에만 둔다.
 */

export const KIND_TONE = { ok: "ok", info: "info", warn: "warn", error: "danger", muted: "neutral" };
const TOOLS_TEXT = { ok: "사용 가능", unsupported: "사용할 수 없음", unknown: "아직 모름" };

function when(iso) {
  return iso ? fmtDateTime(iso) : "아직 없음";
}

function TechLine({ name, value }) {
  if (value == null || value === "") return null;
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "10rem minmax(0,1fr)", gap: 1, minWidth: 0 }}>
      <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>{name}</Typography>
      <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, wordBreak: "break-all" }}>{value}</Typography>
    </Box>
  );
}

export function AiStatusCard({ data, onVerify, verifying = false, timedOut = false }) {
  const state = data.state || {};
  const display = state.display || { label: state.label || "알 수 없음", kind: "muted", message: state.message || "" };
  const config = data.config || {};
  const provider = (data.providers || []).find((p) => p.key === config.provider) || null;
  const method = provider ? provider.auth_methods.find((m) => m.key === config.auth_method) || null : null;
  const technical = data.technical || {};
  const index = data.index;
  const tools = (data.capabilities || {}).tools || "unknown";
  const canVerify = Boolean(config.provider && config.model && method && method.ready);
  const blocked = display.kind === "error" || display.kind === "warn";
  const items = [
    { key: "provider", label: "제공자", value: provider ? provider.label : "정하지 않음" },
    { key: "auth", label: "인증 방식", value: method ? method.label : "정하지 않음" },
    { key: "model", label: "모델", value: config.model || "정하지 않음" },
    { key: "success", label: "최근 성공", value: when(state.last_success_at) },
    { key: "checked", label: "최근 확인", value: when(state.checked_at) },
    { key: "search", label: "문서 검색", value: "사용 가능" },
    { key: "tools", label: "도구 호출", value: TOOLS_TEXT[tools] || TOOLS_TEXT.unknown },
  ];
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
          {!blocked && display.message ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{display.message}</Typography>
          ) : null}
        </Box>
      </HeadRow>
      {blocked && display.message ? (
        <Callout tone={display.kind === "error" ? "danger" : "warn"} compact>{display.message}</Callout>
      ) : null}
      {timedOut ? (
        <Callout tone="info" compact>확인이 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 확인하세요.</Callout>
      ) : null}
      <MetaBar items={items} ariaLabel="지금 쓰는 연결" />
      <TechDetail>
        <Box sx={{ display: "grid", gap: 0.5 }}>
          <TechLine name="연결 상태 코드" value={state.state} />
          <TechLine name="까닭 코드" value={technical.reason_code} />
          <TechLine name="연속 실패" value={technical.consecutive_failures ? `${technical.consecutive_failures}회` : null} />
          <TechLine name="프록시" value={technical.proxy} />
          <TechLine name="연결한 계정" value={technical.account_label} />
          <TechLine name="토큰 만료" value={technical.access_expires_at ? fmtDateTime(technical.access_expires_at) : null} />
          <TechLine name="갱신 토큰 만료" value={technical.refresh_expires_at ? fmtDateTime(technical.refresh_expires_at) : null} />
          <TechLine name="도구 시험 모델" value={technical.tools_checked_model} />
          <TechLine name="도구 시험 시각" value={(data.capabilities || {}).checked_at ? fmtDateTime(data.capabilities.checked_at) : null} />
          <TechLine name="색인 문서" value={index ? `${index.documents ?? 0}건, 조각 ${index.chunks ?? 0}개` : null} />
          <TechLine
            name="의미 검색 모델"
            value={index && index.semantic != null ? (index.semantic ? "있음" : "없음(낱말로 찾습니다)") : null}
          />
          {data.chatgpt && data.chatgpt.manage_usage_url && config.auth_method === "chatgpt" ? (
            <TechLine name="요금제 사용량" value={data.chatgpt.manage_usage_url} />
          ) : null}
        </Box>
      </TechDetail>
    </Card>
  );
}

export default AiStatusCard;
