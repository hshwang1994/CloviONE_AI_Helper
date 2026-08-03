import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { useAuth } from "../app/auth.jsx";
import { PageHeader, Card, Badge, Button, Callout, DataTable, Drawer, Skeleton, EmptyState, ErrorState, useConfirm, useToast } from "../ui/kit.jsx";
import { ACCENT_PRESETS, normalizeAccent } from "../ui/theme.js";
import { useThemeMode } from "../ui/ThemeModeProvider.jsx";

/* 설정 — 시스템 동작 값을 관리한다. GET /api/admin/settings는 {settings:{key:{value,type,
 * description,restart_required,is_default}}} 형태. 편집은 모달에서 타입별 입력 → PUT /{key}. object 타입
 * (ui_branding·password_policy·session_policy·allowed_email_domains)은 JSON 텍스트로 편집한다.
 *
 * 2026-08 MUI 재설계: 손으로 쓴 입력(.c-search/.k-chip/textarea)을 MUI 폼 컴포넌트로 바꿨다.
 * 값은 rem/테마 값이라 4K에서 글자와 여백이 함께 커진다. 저장 로직(coerce/dry-run/보안 완화 확인/
 * 미저장 변경 보호)은 한 줄도 바꾸지 않았다 — 이 화면의 위험은 전부 그쪽에 있다. */

// snake_case 백엔드 키를 한국어 이름으로. 한국어 콘솔에 raw 영문 키를 주 식별자로 노출하지 않는다.
const SETTING_LABELS = {
  // 라벨과 설명(registry.py) 용어를 '보존'으로 통일한다 — 라벨은 '보관', 옆 설명은 '보존'이라 서로 다른 개념처럼 보였다.
  conversation_retention_days: "대화 보존 기간(일)",
  notification_retention_days: "알림 보존 기간(일)",
  trash_retention_days: "휴지통 보관 기간(일)",
  ui_branding: "브랜딩",
  maintenance_mode: "유지보수 모드",
  maintenance_message: "점검 공지",
  password_policy: "비밀번호 정책",
  session_policy: "세션 정책",
  allowed_email_domains: "허용 이메일 도메인",
  document_automation_enabled: "문서 자동화",
};
const settingLabel = (k) => SETTING_LABELS[k] || k;
// object 설정 편집 시 필요한 키·단위를 알려 준다(비개발자 관리자가 raw JSON을 추측하지 않게).
const OBJECT_SCHEMA_HELP = {
  password_policy: 'JSON 예: {"min_length": 12, "min_classes": 3}, min_length(최소 글자 수), min_classes(문자 종류 수, 1~4).',
  session_policy: 'JSON 예: {"idle_timeout_seconds": 1800, "absolute_timeout_seconds": 28800}, 값은 초 단위입니다(30분=1800, 8시간=28800).',
  // 백엔드(_email_domains)는 빈 목록([])을 '도메인 제한 없음'으로 허용한다(round10 감사 C 반영).
  allowed_email_domains: 'JSON 예: ["goodmit.co.kr"], 로그인 허용 이메일 도메인 목록. 빈 목록([])이면 도메인 제한 없이 모든 이메일을 허용합니다.',
  ui_branding: 'JSON 예: {"product_name": "ClovirONE", "support_email": "help@goodmit.co.kr"}, 제품명, 지원 이메일 등 브랜딩 값.',
};
const WRITE_ROLES = ["admin", "system_admin"];
// maintenance_mode·maintenance_message는 전용 '유지보수' 화면(/maintenance)에서만 관리한다.
// 같은 안전 스위치를 두 화면에서 서로 다른 방식으로 다루지 않도록 설정 표에서는 숨긴다.
const MAINTENANCE_KEYS = ["maintenance_mode", "maintenance_message"];
// /maintenance 라우트의 실제 접근 역할(App.jsx RequireRole/NAV와 일치) — operator·auditor도 조회는
// 할 수 있다(쓰기만 canWrite로 서버가 막는다). 아래 안내 링크는 이 화면 자체의 canWrite(설정 편집 권한)가
// 아니라 이 목록으로 게이트해야, 조회만 가능한 역할도 403 없이 실제로 열 수 있는 화면을 클릭할 수 있다.
const MAINTENANCE_READ_ROLES = ["operator", "admin", "system_admin", "auditor"];
// 이 object 설정들은 정해진 스키마가 있어 타입에 맞는 입력(숫자·분/시간·칩 목록)으로 편집할 수 있다.
// 비개발자 관리자가 raw JSON을 손으로 추측하지 않게 하려는 목적(registry.py 주석과 동일 취지) —
// 그 외 미지의 object 키는 여전히 JSON 텍스트로만 편집한다(스키마가 없으므로).
const STRUCTURED_OBJECT_KEYS = ["password_policy", "session_policy", "allowed_email_domains", "ui_branding"];
// 평범한 int 설정도 상한이 있다(registry.py _positive_int(3650)) — object 설정들처럼 min/max와 범위
// 힌트를 붙여, 값을 저장 왕복 없이도 눈치챌 수 있게 한다(이전엔 이 둘만 아무 제약 없는 숫자 입력이었다).
const INT_BOUNDS = { conversation_retention_days: [1, 3650], notification_retention_days: [1, 3650], trash_retention_days: [1, 365] };

// 강조색 프리셋의 한국어 이름 — 색만으로 고르게 두면 색각 이상 사용자는 무엇을 골랐는지 알 수 없고,
// 스크린리더는 아무것도 읽을 게 없다(WCAG 1.4.1). 이름을 모르면 hex를 그대로 읽어 준다.
const ACCENT_NAMES = {
  "#536CD6": "기본 파랑",
  "#4058BD": "진한 파랑",
  "#6B5BC7": "보라",
  "#327C98": "청록",
};

// 초 단위 값을 왜곡 없이 표시한다 — 딱 떨어질 때만 상위 단위로, 아니면 하위 단위로 내려간다.
// (예전엔 Math.round로 90초를 '2분'처럼 보여 요약이 실제 저장값과 어긋났다.)
export function fmtDuration(sec) {
  if (sec == null) return "";
  if (sec % 3600 === 0) return sec / 3600 + "시간";
  if (sec % 60 === 0) return sec / 60 + "분";
  // 정확히 시간/분 단위로 안 떨어지는 값(예: JSON 고급 편집으로 만들어진 1830초)도 raw seconds로
  // 새지 않게, 복합 단위(N시간 M분 / N분 M초)로 표시한다.
  if (sec >= 3600) { const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60); return m ? h + "시간 " + m + "분" : h + "시간"; }
  if (sec >= 60) { const m = Math.floor(sec / 60), s = sec % 60; return s ? m + "분 " + s + "초" : m + "분"; }
  return sec + "초";
}

// object 설정은 raw JSON 대신 사람이 읽을 수 있는 한국어 요약을 보여준다(읽기 전용 역할 포함).
export function summarizeSetting(key, v) {
  // 나머지 object 설정은 이미 완결된 한국어 요약('최소 12자' 등)을 보여주는데, 정수 타입인 이
  // 두 보존 기간 키만 '값' 칸에 단위 없는 맨숫자('90')로 떨어져 옆 행들과 표기가 어긋났다.
  if ((key === "conversation_retention_days" || key === "notification_retention_days" || key === "trash_retention_days") && typeof v === "number") return v + "일";
  if (v == null || typeof v !== "object") return null;
  if (key === "password_policy") {
    const parts = [];
    if (v.min_length != null) parts.push("최소 " + v.min_length + "자");
    if (v.min_classes != null) parts.push(v.min_classes + "종류 이상");
    return parts.length ? parts.join(" / ") : null;
  }
  if (key === "session_policy") {
    const parts = [];
    if (v.idle_timeout_seconds != null) parts.push("유휴 " + fmtDuration(v.idle_timeout_seconds));
    if (v.absolute_timeout_seconds != null) parts.push("최대 " + fmtDuration(v.absolute_timeout_seconds));
    return parts.length ? parts.join(", ") : null;
  }
  if (key === "allowed_email_domains") {
    // 백엔드는 빈 목록([])을 '도메인 제한 없음'으로 허용한다, 빈 값은 그 뜻을 분명히 요약한다.
    if (Array.isArray(v)) return v.length ? "도메인: " + v.join(", ") : "제한 없음(모든 도메인 허용)";
  }
  if (key === "ui_branding") {
    const parts = [];
    if (v.product_name) parts.push("제품명: " + String(v.product_name));
    if (v.support_email) parts.push("지원: " + String(v.support_email));
    return parts.length ? parts.join(", ") : null;
  }
  return null;
}

// 보안을 '약화'시키는 설정 변경을 감지해 확인 문구를 돌려준다(해당 없으면 null).
// 검증만 통과하면 한 클릭으로 커밋되던 위험, 롤백, 유지보수 토글처럼 확인 단계를 둔다.
function securityDowngradeWarning(setting, value) {
  if (setting.key === "allowed_email_domains") {
    // 빈 목록([])은 백엔드에서 '모든 도메인 허용'이라 로그인 제한이 통째로 풀린다.
    if (Array.isArray(value) && value.length === 0)
      return "허용 이메일 도메인을 비우면 도메인 제한이 사라져 모든 이메일 도메인의 로그인이 허용됩니다. 계속할까요?";
    return null;
  }
  if (setting.key === "password_policy") {
    const cur = setting.value || {};
    const reasons = [];
    if (value && cur.min_length != null && value.min_length != null && value.min_length < cur.min_length)
      reasons.push("최소 글자 수 " + cur.min_length + " → " + value.min_length);
    if (value && cur.min_classes != null && value.min_classes != null && value.min_classes < cur.min_classes)
      reasons.push("문자 종류 수 " + cur.min_classes + " → " + value.min_classes);
    if (reasons.length)
      return "비밀번호 정책을 약화합니다(" + reasons.join(", ") + "). 인증 강도가 낮아집니다, 계속할까요?";
    return null;
  }
  // 세션 제한 시간을 늘리는 것도 password_policy 약화·도메인 제한 해제와 같은 성격의 보안 완화다 —
  // 로그인 세션이 더 오래 살아남는다(탈취된 세션의 유효 기간이 늘어난다). 이전엔 이 키만 확인 없이
  // 한 클릭 저장돼 다른 두 보안 설정과 다르게 취급됐다.
  if (setting.key === "session_policy") {
    const cur = setting.value || {};
    const reasons = [];
    if (value && cur.idle_timeout_seconds != null && value.idle_timeout_seconds != null && value.idle_timeout_seconds > cur.idle_timeout_seconds)
      reasons.push("유휴 제한 " + fmtDuration(cur.idle_timeout_seconds) + " → " + fmtDuration(value.idle_timeout_seconds));
    if (value && cur.absolute_timeout_seconds != null && value.absolute_timeout_seconds != null && value.absolute_timeout_seconds > cur.absolute_timeout_seconds)
      reasons.push("최대 세션 길이 " + fmtDuration(cur.absolute_timeout_seconds) + " → " + fmtDuration(value.absolute_timeout_seconds));
    if (reasons.length)
      return "세션 정책을 완화합니다(" + reasons.join(", ") + "). 세션이 더 오래 유지됩니다, 계속할까요?";
    return null;
  }
  return null;
}

function displayValue(v) {
  if (v == null || v === "") return "-";
  if (typeof v === "object") { const s = JSON.stringify(v); return s.length > 72 ? s.slice(0, 72) + "…" : s; }
  if (typeof v === "boolean") return v ? "켜짐" : "꺼짐";
  return String(v);
}

/* 화면 강조색 — 다크/라이트 모드와 같은 성격의 '이 브라우저에만' 저장되는 개인 취향이다
 * (ui/ThemeModeProvider.jsx가 localStorage에 넣는다). 서버 설정으로 만들면 한 사람의 취향이
 * 전원에게 적용되므로 위의 설정 표(시스템 값)와는 일부러 분리해 둔다.
 *
 * 선택 표시를 색만으로 하지 않는다(WCAG 1.4.1) — 이름 굵게 + 체크 글리프 + 테두리 강조를 함께 준다. */
function AccentPicker() {
  const { accent, setAccent } = useThemeMode();
  const current = normalizeAccent(accent);
  return (
    <Card sx={{ mb: 2.5 }}>
      <Typography component="h2" variant="h6" sx={{ fontSize: "1.0625rem" }}>화면 강조색</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2, maxWidth: "70ch" }}>
        버튼·링크·선택 표시에 쓰는 색입니다. 밝게/어둡게 설정과 마찬가지로 <strong>지금 쓰는 브라우저에만</strong> 저장되는 개인 설정이라,
        다른 사람이 보는 화면은 바뀌지 않습니다(위 표의 시스템 설정과 다릅니다).
      </Typography>
      <Box role="group" aria-label="화면 강조색" sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        {ACCENT_PRESETS.map((hex) => {
          const value = normalizeAccent(hex);
          const selected = value === current;
          const name = ACCENT_NAMES[value] || value;
          return (
            <Box
              key={value}
              component="button"
              type="button"
              aria-pressed={selected}
              onClick={() => setAccent(value)}
              sx={{
                display: "flex", alignItems: "center", gap: 1, px: 2, py: 1, minHeight: 44,
                cursor: "pointer", font: "inherit", color: "inherit", bgcolor: "transparent",
                border: 2, borderStyle: "solid", borderColor: selected ? "primary.main" : "divider",
                borderRadius: "10px",
                "&:hover": { borderColor: "primary.main" },
              }}
            >
              <Box
                aria-hidden="true"
                /* minWidth를 함께 준다 — 폭이 빠지면 원이 테두리만 남은 2px 세로선으로 찌부러진다
                   (색 견본이 사라지면 이 선택기는 글자만 남아 의미의 절반을 잃는다). */
                sx={{ width: "1.25rem", minWidth: "1.25rem", height: "1.25rem", borderRadius: "50%", bgcolor: value, border: 1, borderColor: "divider", flex: "none" }}
              />
              <Box component="span" sx={{ fontSize: "0.875rem", fontWeight: selected ? 780 : 550 }}>{name}</Box>
              {selected ? <Box component="span" aria-hidden="true" sx={{ fontWeight: 800, color: "primary.main" }}>✓</Box> : null}
              {selected ? <span className="sr-only">(현재 색)</span> : null}
            </Box>
          );
        })}
      </Box>
    </Card>
  );
}

// 스키마가 정해진 object 설정을 타입에 맞는 입력으로 편집한다. 값의 참(source of truth)은 여전히
// SettingEditor의 JSON 문자열(val)이다 — 여기선 그 문자열을 파싱해 보여주고, 바뀌면 다시
// JSON.stringify해 onChange(=changeVal)로 돌려보낸다. 이렇게 하면 coerce()/dirty/저장 로직을
// 그대로 재사용하면서 입력만 사람이 읽는 필드로 바꿀 수 있다.
function StructuredObjectFields({ settingKey, val, onChange, canWrite, describedBy, invalid }) {
  const [draft, setDraft] = useState(""); // 도메인 추가 입력칸(허용 이메일 도메인 전용) — 훅은 분기 밖에서 항상 호출
  const [domainErr, setDomainErr] = useState(""); // 위와 같은 이유로 분기 밖에서 항상 호출(Hooks 규칙)
  let obj;
  try { obj = JSON.parse(val); } catch (e) { obj = null; }
  // FormField(kit.jsx)의 id="ff-"+name 관례와 같은 방식으로 각 필드에 안정적인 id를 준다 —
  // label에 htmlFor가 없으면 스크린리더가 입력의 접근 가능한 이름을 못 읽고, 라벨 클릭도 입력에 포커스하지 않는다.
  const fieldId = (name) => "sf-" + settingKey + "-" + name;
  const ariaInvalid = invalid ? true : undefined;
  // 짧은 숫자 입력 두 개를 넓은 화면에서 나란히 둔다 — 한 열로 쌓으면 드로어가 세로로만 길어진다.
  const pairGrid = { display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))" } };

  if (settingKey === "allowed_email_domains") {
    const domains = Array.isArray(obj) ? obj : [];
    // 백엔드 검증(registry.py _email_domains)이 요구하는 최소 형태(점 하나 이상)를 저장 왕복 전에
    // 먼저 잡는다 — 안 그러면 오타 칩이 조용히 추가됐다가 저장 시점에야 "도메인 문자열 목록이어야
    // 합니다" 같은, 어떤 칩이 문제인지 알 수 없는 일반 오류로만 드러난다.
    function addDomain() {
      const d = draft.trim().toLowerCase();
      // 빈 입력은 버튼 disabled(draft.trim() 없으면 클릭 자체가 안 됨)로 대부분 막히지만, Enter
      // 키 경로는 이 disabled 가드를 거치지 않고 곧장 addDomain을 부른다 — 공백만 친 뒤 Enter를
      // 치면 예전엔 여기서 조용히 no-op이라(관찰 가능한 결과 없음) 버튼 경로가 약속한 '항상 뭔가
      // 반응한다'는 보장이 깨졌다.
      if (!d) { setDomainErr(draft ? "공백만으로는 추가할 수 없습니다." : "도메인을 입력하세요."); return; }
      if (!d.includes(".") || d.startsWith(".") || d.endsWith(".")) {
        setDomainErr("도메인 형식이 아닙니다(예: goodmit.co.kr), 점(.)을 포함해야 합니다.");
        return;
      }
      if (domains.includes(d)) { setDomainErr("이미 등록된 도메인입니다."); return; }
      setDomainErr("");
      onChange(JSON.stringify([...domains, d], null, 2));
      setDraft("");
    }
    function removeDomain(d) { onChange(JSON.stringify(domains.filter((x) => x !== d), null, 2)); }
    const domainInputId = fieldId("domain-add");
    const domainErrId = fieldId("domain-add-err");
    const domainDescribedBy = [describedBy, domainErr ? domainErrId : null].filter(Boolean).join(" ") || undefined;
    return (
      <Box sx={{ mb: 2.5 }}>
        <Typography component="span" variant="body2" sx={{ fontWeight: 700, display: "block", mb: 1 }}>허용 이메일 도메인</Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 1.5 }}>
          {domains.length ? domains.map((d) => (
            <Chip
              key={d}
              label={d}
              size="small"
              variant="outlined"
              onDelete={canWrite ? () => removeDomain(d) : undefined}
              // MUI 기본 삭제 아이콘의 접근 가능한 이름은 비어 있다 — 어떤 칩을 지우는지 읽히게 한다.
              deleteIcon={canWrite ? <Box component="span" aria-label={d + " 제거"} role="button" sx={{ px: 0.5, cursor: "pointer", fontSize: "0.75rem" }}>✕</Box> : undefined}
            />
          )) : <Typography variant="body2" color="text.secondary">제한 없음(모든 이메일 도메인 허용)</Typography>}
        </Box>
        {canWrite ? (
          <>
            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", flexWrap: "wrap" }}>
              <TextField
                id={domainInputId} size="small" placeholder="예: goodmit.co.kr" value={draft}
                error={!!domainErr} sx={{ minWidth: "16rem", flex: "1 1 16rem" }}
                inputProps={{ "aria-label": "도메인 추가", "aria-invalid": domainErr ? true : ariaInvalid, "aria-describedby": domainDescribedBy }}
                onChange={(e) => { setDraft(e.target.value); if (domainErr) setDomainErr(""); }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addDomain(); } }}
              />
              {/* 빈 입력으로 누르면 addDomain이 조용히 no-op이라(if(!d)return) 아무 피드백 없이
                  아무 일도 안 일어난 것처럼 보였다, 비어 있으면 버튼 자체를 비활성화해 클릭이
                  항상 관찰 가능한 결과를 내게 한다. */}
              <Button size="sm" onClick={addDomain} disabled={!draft.trim()}>추가</Button>
            </Box>
            {domainErr ? <Typography color="error" variant="body2" id={domainErrId} role="alert" sx={{ mt: 1 }}>{domainErr}</Typography> : null}
          </>
        ) : null}
      </Box>
    );
  }

  const safe = obj && typeof obj === "object" && !Array.isArray(obj) ? obj : {};
  function patch(next) { onChange(JSON.stringify({ ...safe, ...next }, null, 2)); }

  if (settingKey === "password_policy") {
    const minLenId = fieldId("min_length");
    const minClassesId = fieldId("min_classes");
    return (
      <Box sx={pairGrid}>
        {/* 옆 '문자 종류 수(1~4)' 필드처럼 허용 범위를 라벨에 직접 접어 넣는다, 백엔드(registry.py
            _password_policy)가 실제로 강제하는 8~128 범위를 저장 왕복 전까지 알 길이 없었다. */}
        <TextField
          id={minLenId} label="최소 글자 수(8~128자)" type="number" size="small" fullWidth disabled={!canWrite}
          error={!!invalid}
          inputProps={{ min: 8, max: 128, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
          value={safe.min_length != null ? safe.min_length : ""}
          onChange={(e) => patch({ min_length: e.target.value === "" ? null : Number(e.target.value) })}
        />
        <TextField
          id={minClassesId} label="문자 종류 수(1~4)" type="number" size="small" fullWidth disabled={!canWrite}
          error={!!invalid}
          inputProps={{ min: 1, max: 4, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
          value={safe.min_classes != null ? safe.min_classes : ""}
          onChange={(e) => patch({ min_classes: e.target.value === "" ? null : Number(e.target.value) })}
        />
      </Box>
    );
  }
  if (settingKey === "session_policy") {
    // 저장값은 초 단위지만, 사람은 분/시간으로 생각한다, 입력은 분/시간으로 받고 초로 변환해 저장한다.
    const idleMin = safe.idle_timeout_seconds != null ? Math.round(safe.idle_timeout_seconds / 60) : "";
    // 이전엔 이 필드만 시간 단위(min=0.5, step=0.5)라 라벨의 '최소 1분'을 실제로 입력할 수 없었다
    // (스피너가 30분 단위로만 움직인다), 바로 위 유휴 필드와 같은 분 단위로 맞춰, 라벨이 약속하는
    // 최소값을 컨트롤로도 실제로 도달할 수 있게 한다(백엔드 _session_policy는 두 필드 모두 60초 이상만 요구).
    const absMin = safe.absolute_timeout_seconds != null ? Math.round(safe.absolute_timeout_seconds / 60) : "";
    const idleId = fieldId("idle_timeout_minutes");
    const absId = fieldId("absolute_timeout_minutes");
    return (
      <Box sx={pairGrid}>
        <Box>
          <TextField
            id={idleId} label="유휴 제한(분, 최소 1분)" type="number" size="small" fullWidth disabled={!canWrite}
            error={!!invalid}
            inputProps={{ min: 1, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={idleMin}
            onChange={(e) => patch({ idle_timeout_seconds: e.target.value === "" ? null : Math.round(Number(e.target.value) * 60) })}
          />
          {/* 분 단위 숫자만으론 시간 규모(예: 480 = 8시간)를 확인하기 어렵다, 표 요약과 같은
              fmtDuration으로 사람이 읽는 값을 바로 옆에 함께 보여준다. */}
          {safe.idle_timeout_seconds != null ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>= {fmtDuration(safe.idle_timeout_seconds)}</Typography> : null}
        </Box>
        <Box>
          <TextField
            id={absId} label="최대 세션 길이(분, 최소 1분)" type="number" size="small" fullWidth disabled={!canWrite}
            error={!!invalid}
            inputProps={{ min: 1, step: 1, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={absMin}
            onChange={(e) => patch({ absolute_timeout_seconds: e.target.value === "" ? null : Math.round(Number(e.target.value) * 60) })}
          />
          {safe.absolute_timeout_seconds != null ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>= {fmtDuration(safe.absolute_timeout_seconds)}</Typography> : null}
        </Box>
      </Box>
    );
  }
  if (settingKey === "ui_branding") {
    const nameId = fieldId("product_name");
    const emailId = fieldId("support_email");
    return (
      <Box sx={pairGrid}>
        <TextField
          id={nameId} label="제품명" size="small" fullWidth disabled={!canWrite} error={!!invalid}
          inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
          value={safe.product_name || ""} onChange={(e) => patch({ product_name: e.target.value })}
        />
        <TextField
          id={emailId} label="지원 이메일" size="small" fullWidth disabled={!canWrite} error={!!invalid}
          inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
          value={safe.support_email || ""} onChange={(e) => patch({ support_email: e.target.value })}
        />
      </Box>
    );
  }
  return null;
}

export function Settings() {
  const [sel, setSel] = useState(null);
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const auth = useAuth();
  const canWrite = (auth.data && WRITE_ROLES.includes(auth.data.role)) || false;
  const canReachMaintenance = (auth.data && MAINTENANCE_READ_ROLES.includes(auth.data.role)) || false;
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/api/admin/settings"), retry: false });

  const map = (q.data && q.data.settings) || {};
  // SETTING_LABELS/OBJECT_SCHEMA_HELP/STRUCTURED_OBJECT_KEYS/INT_BOUNDS는 백엔드 registry.py의
  // REGISTRY와 같은 키를 손으로 따로 유지한다(공유 소스가 없다) — 새 키가 registry.py에 추가되고
  // 여기 라벨이 빠지면, 원시 영문 키가 표에 그대로 새어 나가는데도 조용히(에러 없이) 넘어간다.
  // 개발 중 눈에 띄도록 최소한의 드리프트 경고를 남긴다.
  React.useEffect(() => {
    // 이 드리프트 경고는 개발자용 유지보수 힌트다 — 프로덕션 사용자의 devtools 콘솔로 새지 않도록
    // 개발 빌드에서만 낸다('no console.log in production' 규칙, typescript/coding-style.md).
    if (!(import.meta && import.meta.env && import.meta.env.DEV)) return;
    Object.keys(map).forEach((k) => {
      if (!SETTING_LABELS[k]) console.warn("[Settings] SETTING_LABELS에 없는 설정 키: " + k + ", registry.py에 새 키를 추가했다면 SETTING_LABELS(Settings.jsx)에도 한국어 라벨을 추가하세요.");
      // displayValue()의 raw-JSON(JSON.stringify) 폴백은 summarizeSetting이 그 키를 모를 때만 쓰인다 -
      // 지금은 등록된 4개 object 설정이 전부 요약 분기를 갖고 있어 이 폴백이 죽은 코드다. 새 object
      // 설정이 registry.py에 추가되고 summarizeSetting에 짝이 되는 한국어 분기가 빠지면, SETTING_LABELS
      // 드리프트와 같은 방식으로 콘솔에 알려 raw JSON이 조용히 화면에 새지 않게 한다.
      const row = map[k];
      if (row && row.value != null && (row.type === "object" || row.type === "json") && summarizeSetting(k, row.value) == null) {
        console.warn("[Settings] summarizeSetting에 한국어 요약 분기가 없는 object 설정 키: " + k + ", 추가하지 않으면 값 열에 raw JSON이 그대로 노출됩니다.");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data]);
  // "설정" 열의 원시 값 자체를 이미 사람이 읽는 한국어 라벨로 만든다, 커스텀 render 대신 원시
  // 값을 그대로 보여주면, kit.jsx의 DataTable이 그 값으로 '상세 보기: <라벨>'을 만들어 스크린리더/
  // 음성 제어 사용자가 행마다 다른 aria-label을 듣는다(예전엔 render가 있어 모든 행이 동일하게
  // '상세 보기'로만 들렸다). raw 키는 옆의 별도 열로 유지해 정보 손실 없이 보인다.
  const rows = Object.keys(map).filter((k) => !MAINTENANCE_KEYS.includes(k)).map((k) => ({ key: k, label: settingLabel(k), ...map[k] }));
  /* 열에 width를 주지 않는다(DataTable이 지원하긴 한다). 이 표는 '설명'만 길고 나머지는 짧은데,
   * 앞 네 열에 고정 폭을 주면 요청 폭 합이 1366px 화면의 가용 폭을 넘겨 브라우저가 폭을 지정하지
   * 않은 '설명' 열을 0에 가깝게 짜부라뜨린다 — 실제로 설명 글자가 한 줄에 한 자씩 세로로 흘렀다.
   * 폭 배분은 브라우저 auto 레이아웃에 맡긴다(내용에 비례해 나눈다). */
  const columns = [
    { key: "label", label: "설정" },
    { key: "key", label: "키", render: (r) => <Typography component="span" variant="caption" color="text.secondary">{r.key}</Typography> },
    { key: "value", label: "값", render: (r) => summarizeSetting(r.key, r.value) || displayValue(r.value) },
    // '변경됨'은 기본값과 다를 뿐 문제 상태가 아니다 — warn(주황)은 이상으로 오독되므로 info로 표시한다.
    { key: "is_default", label: "상태", render: (r) => <Badge value={r.is_default ? "기본값" : "변경됨"} kind={r.is_default ? "neutral" : "info"} /> },
    { key: "description", label: "설명" },
  ];

  return (
    <div className="c-screen">
      <PageHeader area="운영" title="설정" />
      {/* 다른 관리 화면(DataScreen)의 help 인트로와 같은 패턴, 처음 오는 관리자에게 화면 사용법을 안내한다. */}
      {/* '즉시 적용됩니다'는 사실이 아니었다, 세션 정책은 신규 세션부터, 허용 도메인은 사용자 생성 시, 보존 기간은 다음 정리 작업 때 반영된다. 적용 시점은 항목별 '설명'을 따르도록 문구를 완화한다. */}
      {/* 예전엔 이 안내가 인트로 Callout, '열람만 가능' 안내, '유지보수' 안내로 3개의 서로 떨어진
          시각 블록이었다, 개별로는 다 맞는 말이지만 함께 있으면 세 조각 난 도입부처럼 읽혀 아래
          진짜 콘텐츠(설정 표)를 더 밀어냈다. 한 Callout 안의 문단으로 한 덩어리로 묶는다. */}
      <Box sx={{ mb: 2.5, "& p": { m: 0 }, "& p + p": { mt: 0.75 } }}>
        <Callout tone="info">
          {/* 버전 기록은 읽기 전용 역할(operator, auditor)도 편집기의 '버전 기록' 버튼으로 열람할 수
              있다(롤백만 canWrite), 예전엔 canWrite일 때만 언급해, 읽기 역할은 이력의 존재조차 몰랐다. */}
          <p>시스템 동작 값을 관리합니다. 항목을 클릭하면 편집기가 열립니다. 저장 시 유효성 검증 후 반영되며, 적용 시점은 항목마다 다를 수 있습니다(각 항목의 ‘설명’ 참고).{canWrite ? " 각 항목의 ‘버전 기록’에서 이전 값으로 되돌릴 수 있습니다." : " 각 항목의 ‘버전 기록’에서 이전 변경 이력을 볼 수 있습니다."}</p>
          {!canWrite ? <p>설정 값은 열람만 가능합니다. 변경은 관리자, 시스템 관리자만 할 수 있습니다.</p> : null}
          {/* maintenance_mode, maintenance_message는 이 표에서 의도적으로 숨겨진다(위 MAINTENANCE_KEYS) -
              숨긴 이유만 있고 어디로 갔는지 안내가 없으면 관리자가 '유지보수 스위치가 없어졌다'고 오인한다.
              /maintenance는 operator, admin, system_admin, auditor가 조회할 수 있다(App.jsx RequireRole/NAV) -
              쓰기만 canWrite(admin/system_admin)로 서버가 막으므로, 이 안내 링크는 canWrite가 아니라
              MAINTENANCE_READ_ROLES로 게이트해야 조회만 가능한 역할도 실제로 열 수 있는 화면을 클릭할 수 있다. */}
          <p>유지보수 모드, 점검 공지는 {canReachMaintenance
            ? <Link component="button" type="button" underline="hover" sx={{ font: "inherit", verticalAlign: "baseline" }} onClick={() => nav("/maintenance")}>‘유지보수’ 화면</Link>
            : "‘유지보수’ 화면"}에서 관리합니다.</p>
        </Callout>
      </Box>
      {q.isLoading ? <Card><Skeleton lines={5} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        /* effective_settings()는 항상 REGISTRY의 모든 키를 반환하므로 정상 경로에선 도달하지 않는다.
           응답이 비정상(빈 형태)일 때를 위한 방어적 폴백으로만 남긴다. */
        /* effective_settings()가 항상 전 키를 돌려주므로 이 빈 상태는 비정상 응답에서만 뜬다 -
           막다른 안내 대신 원인(비어 있음)과 다시 불러오기 경로를 준다(오류에 가깝게 취급). */
        : rows.length === 0 ? <EmptyState title="설정을 표시할 수 없습니다" help="설정을 불러왔지만 항목이 비어 있습니다, 일시적인 문제일 수 있습니다." action={<Button onClick={() => q.refetch()}>다시 불러오기</Button>} />
        : <Card sx={{ mb: 2.5 }}><DataTable columns={columns} rows={rows} rowKey={(r) => r.key} onRow={setSel} /></Card>}
      {/* 시스템 설정 표 아래에 개인 취향 설정을 둔다 — 위와 성격이 달라(서버 저장 아님) 카드를 나눈다. */}
      <AccentPicker />
      <SettingEditor setting={sel} canWrite={canWrite} onClose={() => setSel(null)}
        onSaved={(res) => {
          qc.invalidateQueries({ queryKey: ["settings"] });
          // 버전 기록 쿼리도 함께 무효화한다 — SettingVersions.doRollback과 동일한 이유: 기본
          // staleTime(30초) 안에 '버전 기록'을 열면 방금 저장한 변경이 빠진 캐시를 보여준다.
          if (sel) qc.invalidateQueries({ queryKey: ["settings", sel.key, "versions"] });
          setSel(null);
          // 재시작이 필요한 키는 저장만으로 적용되지 않는다 — 수동 재시작 안내를 분명히 남긴다(현재는 해당 키 없음, 향후 대비).
          if (res && res.restart_required) toast("설정을 저장했습니다, 적용하려면 서비스를 수동으로 재시작하세요.", "info");
          else toast("설정을 저장했습니다.", "success");
        }} />
    </div>
  );
}

// object 타입 판정 — 타입 문자열이 object이거나 값 자체가 객체/배열이면 JSON 편집기를 쓴다.
function isObjectSetting(setting) {
  return setting.type === "object" || setting.type === "json" || (setting.value !== null && typeof setting.value === "object");
}

function SettingEditor({ setting, canWrite, onClose, onSaved }) {
  const [val, setVal] = useState("");
  const [err, setErr] = useState("");
  const [checked, setChecked] = useState("");
  const [showVersions, setShowVersions] = useState(false);
  const [advanced, setAdvanced] = useState(false); // 구조화된 입력 대신 raw JSON을 직접 편집(고급)
  const confirm = useConfirm();
  // onCheck()의 비동기 dryRun이 끝나기 전에 사용자가 이 편집기를 다른 설정으로 바꿔 열 수 있다
  // (드로어가 언마운트되지 않고 setting prop만 바뀐다) — 그 사이 도착한 응답이 지금 열린 설정과
  // 짝이 맞는지 이 ref로 확인한다(라이브 참조, useEffect의 setting은 클로저에 갇혀 낡을 수 있다).
  const settingKeyRef = React.useRef(setting && setting.key);
  // onCheck()의 비동기 dryRun이 도는 사이 같은 설정 안에서 값이 바뀔 수도 있다(예: 검증 중 타자를
  // 계속 침) — settingKeyRef만으로는 '다른 설정으로 전환'만 잡고 '같은 설정, 다른 값'은 못 잡아,
  // 이미 바뀐 값 옆에 옛 검증 결과('통과'/오류)가 계속 다시 표시됐다. 값도 함께 라이브 참조한다.
  const valRef = React.useRef(val);
  React.useEffect(() => { valRef.current = val; }, [val]);
  React.useEffect(() => {
    settingKeyRef.current = setting && setting.key;
    if (!setting) return;
    if (isObjectSetting(setting)) setVal(JSON.stringify(setting.value, null, 2));
    else setVal(String(setting.value));
    setErr("");
    setChecked("");
    setShowVersions(false);
    setAdvanced(false);
  }, [setting]);
  const save = useMutation({
    mutationFn: (body) => api("/api/admin/settings/" + setting.key, { method: "PUT", body }),
  });
  const dryRun = useMutation({
    mutationFn: (body) => api("/api/admin/settings/" + setting.key + "/dry-run", { method: "POST", body }), });
  if (!setting) return null;

  // 값이 바뀌면 이전 '검증 통과' 상태, 오류를 지운다, 검증하지 않은 값에 성공 표시가 남지 않도록.
  function changeVal(next) { setVal(next); setChecked(""); setErr(""); }

  function coerce() {
    if (setting.type === "bool") return val === "true" || val === true;
    if (setting.type === "int") {
      if (String(val).trim() === "") throw new Error("정수를 입력하세요.");
      const n = Number(val);
      if (!Number.isInteger(n)) throw new Error("정수를 입력하세요.");
      // Save는 커스텀 버튼이라 브라우저 내장 min/max 검증이 동작하지 않는다(네이티브 폼 제출이 아님) -
      // 범위 밖 값이 서버 왕복(422) 없이 여기서 먼저 잡히게 INT_BOUNDS를 직접 확인한다.
      const bounds = INT_BOUNDS[setting.key];
      if (bounds && (n < bounds[0] || n > bounds[1])) throw new Error(`허용 범위(${bounds[0]}~${bounds[1]})를 벗어났습니다.`);
      return n;
    }
    if (isObjectSetting(setting)) {
      let parsed;
      try { parsed = JSON.parse(val); } catch (e) { throw new Error("JSON 형식이 올바르지 않습니다."); }
      // 구조화 입력이 아닌 고급(raw JSON) 편집으로도 범위를 벗어난 값을 넣을 수 있다, 저장 전에
      // 문서화된 범위(OBJECT_SCHEMA_HELP)와 같은 기준으로 한 번 더 확인한다.
      if (setting.key === "password_policy" && parsed && typeof parsed === "object") {
        // 필수 숫자 필드를 비우면 구조화 입력이 null을 보내는데(min_length: null), 예전엔 != null
        // 가드 때문에 범위 검사를 통째로 건너뛰어 서버 422로만 드러났다, 존재, 정수 여부를 먼저 잡는다.
        if (parsed.min_length == null || !Number.isInteger(parsed.min_length)) throw new Error("최소 글자 수를 입력하세요(8~128).");
        if (parsed.min_classes == null || !Number.isInteger(parsed.min_classes)) throw new Error("문자 종류 수를 입력하세요(1~4).");
        if (parsed.min_length < 8 || parsed.min_length > 128) throw new Error("최소 글자 수는 8~128 사이여야 합니다.");
        if (parsed.min_classes < 1 || parsed.min_classes > 4) throw new Error("문자 종류 수는 1~4 사이여야 합니다.");
      }
      // password_policy와 같은 이유(서버 왕복 422 전에 한국어로 먼저 잡는다), session_policy만
      // 이 확인이 없어 registry.py가 요구하는 60초 이상 제약을 저장 시점에야 알 수 있었다.
      if (setting.key === "session_policy" && parsed && typeof parsed === "object") {
        // 필수 숫자 필드를 비우면 null이 전송된다, password_policy와 같은 이유로 존재, 정수부터 잡는다.
        if (parsed.idle_timeout_seconds == null || !Number.isInteger(parsed.idle_timeout_seconds)) throw new Error("유휴 제한(분)을 입력하세요.");
        if (parsed.absolute_timeout_seconds == null || !Number.isInteger(parsed.absolute_timeout_seconds)) throw new Error("최대 세션 길이(분)를 입력하세요.");
        if (parsed.idle_timeout_seconds < 60) throw new Error("유휴 제한은 60초(1분) 이상이어야 합니다.");
        if (parsed.absolute_timeout_seconds < 60) throw new Error("최대 세션 길이는 60초(1분) 이상이어야 합니다.");
      }
      // ui_branding의 product_name은 백엔드가 비어 있으면 거부한다(app/settings/registry.py
      // _ui_branding) — password_policy/session_policy와 같은 이유로 서버 왕복(422) 전에 먼저 잡는다.
      if (setting.key === "ui_branding" && parsed && typeof parsed === "object") {
        if (!parsed.product_name || !String(parsed.product_name).trim()) throw new Error("제품명은 비워둘 수 없습니다.");
      }
      // 구조화된 입력(StructuredObjectFields의 addDomain)은 이 형식 검사를 이미 하는데, 고급(raw JSON)
      // 모드로 편집하면 같은 값이 검사 없이 그대로 통과해 서버 422로만 드러났다 — 같은 규칙을 여기서도 적용한다.
      if (setting.key === "allowed_email_domains") {
        if (!Array.isArray(parsed)) throw new Error("도메인 목록은 배열([...]) 형식이어야 합니다.");
        for (const d of parsed) {
          if (typeof d !== "string" || !d.includes(".") || d.startsWith(".") || d.endsWith("."))
            throw new Error("도메인 형식이 올바르지 않습니다(예: goodmit.co.kr), 점(.)을 포함하고 앞뒤에 점이 없어야 합니다: " + JSON.stringify(d));
        }
      }
      return parsed;
    }
    return val;
  }
  async function onCheck() {
    setErr(""); setChecked("");
    let value;
    try { value = coerce(); } catch (e) { setErr(e.message); return; }
    const requestedKey = setting.key;
    const requestedVal = val; // 이 시점의 값을 캡처 — 응답이 오면 '지금' 값과 비교해 낡았는지 판단한다.
    try {
      await dryRun.mutateAsync({ value });
      // 검증이 도는 사이 다른 설정으로 전환됐거나(settingKeyRef), 같은 설정 안에서 값이 바뀌었으면
      // (valRef) 이 결과는 지금 화면과 무관하다 — setChecked/setErr을 지금 값에 잘못 붙이지 않는다.
      if (settingKeyRef.current !== requestedKey || valRef.current !== requestedVal) return;
      // '저장할 수 있습니다'는 dirty일 때만 사실이다 — 값이 현재 저장된 값과 같으면 Save 버튼은
      // (아래 disabled={!dirty}로) 계속 비활성인 채라, 그 문구가 바로 옆 버튼 상태와 모순됐다.
      setChecked(dirty ? "검증 통과, 저장할 수 있습니다." : "검증 통과, 현재 값과 동일합니다.");
    }
    catch (e) { if (settingKeyRef.current === requestedKey && valRef.current === requestedVal) setErr(e.message); }
  }
  async function onSave() {
    setErr(""); setChecked("");
    let value;
    try { value = coerce(); } catch (e) { setErr(e.message); return; }
    // maintenance_mode/message는 이 표에서 필터링되어(위 MAINTENANCE_KEYS) 여기 편집기로 열리지 않으므로
    // 예전의 maintenance_mode 전용 확인 분기는 도달 불가라 제거했다(유지보수 편집은 /maintenance 화면 전담).
    // 보안 완화(도메인 제한 해제·비밀번호 정책 약화)는 저장 직전 한 번 더 확인받는다.
    const warnMsg = securityDowngradeWarning(setting, value);
    if (warnMsg) {
      const ok = await confirm(warnMsg, { danger: true, title: "보안 설정 변경 확인", confirmLabel: "변경" });
      if (!ok) return;
    }
    try { const res = await save.mutateAsync({ value }); onSaved(res); }
    catch (e) { setErr(e.message); }
  }
  // 미저장 변경 보호 — 오버레이 클릭·Esc로 편집(특히 여러 줄 JSON)을 조용히 날리지 않게 확인을 받는다
  // (공통 FormModal.requestClose와 동일 패턴). 초기 직렬화 값은 위 useEffect가 val에 넣는 규칙과 같다.
  const initialVal = isObjectSetting(setting) ? JSON.stringify(setting.value, null, 2) : String(setting.value);
  const dirty = val !== initialVal;
  async function requestClose() {
    // 저장 요청이 진행 중이면 닫기(취소·Esc·백드롭 클릭 전부 이 함수를 거친다)를 막는다 — 진행 중인
    // PUT을 취소할 수단이 없으므로, 조용히 드로어만 닫으면 요청은 그대로 완료되고 onSaved(무효화·
    // 성공 토스트)가 이미 닫힌 화면 뒤에서 실행되는 혼란스러운 상태가 된다.
    if (save.isPending) return;
    if (dirty) {
      const ok = await confirm("변경한 내용이 저장되지 않았습니다. 닫을까요?", { danger: true, confirmLabel: "닫기" });
      if (!ok) return;
    }
    onClose();
  }
  // 고급(raw JSON) → 구조화된 입력으로 되돌아갈 때, val이 지금 유효한 JSON이 아니면 되돌아갈 수 없다 —
  // StructuredObjectFields는 파싱 실패 시 obj=null로 두고 안전 폴백으로 {}/[]를 쓰므로, 그대로
  // 전환을 허용하면 편집 중이던 값이 빈 값으로 조용히 대체된다(그 시점의 patch()가 {}를 기준으로 병합).
  let advancedJsonValid = true;
  if (isObjectSetting(setting)) { try { JSON.parse(val); } catch (e) { advancedJsonValid = false; } }
  const intBounds = setting.type === "int" ? INT_BOUNDS[setting.key] : null;
  // 'setting-help' 노드는 비구조화/고급 편집일 때만 렌더된다(아래 조건과 동일) — describedBy가
  // 항상 이 id를 참조하면 구조화 입력 모드에선 존재하지 않는 노드를 가리키는 dangling
  // aria-describedby가 된다. 실제로 렌더될 때만 포함한다.
  const helpShown = isObjectSetting(setting) && (!STRUCTURED_OBJECT_KEYS.includes(setting.key) || advanced);
  // 입력과 설명/도움말/오류를 잇는 aria-describedby(존재하는 노드만 포함) — 스크린리더가 값 편집 시 설명·제약을 함께 읽는다.
  const describedBy = [setting.description ? "setting-desc" : null, helpShown ? "setting-help" : null, intBounds ? "setting-range" : null, err ? "setting-err" : null].filter(Boolean).join(" ") || undefined;

  const footer = (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Box className="k-footer-extra">
        <Button variant="ghost" onClick={requestClose} disabled={save.isPending}>취소</Button>
        <Button variant="ghost" onClick={() => setShowVersions(true)}>버전 기록</Button>
      </Box>
      <Box className="k-footer-main">
        {canWrite ? <Button onClick={onCheck} disabled={dryRun.isPending}>{dryRun.isPending ? "검증 중…" : "미리 검증"}</Button> : null}
        {/* 변경이 없으면 저장을 막는다, 같은 값 재저장은 config_versions, 감사 로그에 no-op을 쌓는다. */}
        {canWrite ? <Button variant="primary" onClick={onSave} disabled={save.isPending || !dirty}>{save.isPending ? "저장 중…" : "저장"}</Button> : null}
      </Box>
    </Box>
  );
  return (
    <>
    <Drawer open={!!setting} onClose={requestClose} title={settingLabel(setting.key)} footer={footer}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{setting.key} ({setting.is_default ? "기본값" : "변경됨"})</Typography>
      <Typography variant="body2" id="setting-desc" sx={{ mt: 0.5, mb: 2.5, maxWidth: "70ch" }}>{setting.description}</Typography>
      {/* 읽기 전용 역할에겐 이 서랍이 '잠긴 편집 폼'이 아니라 '상세 보기'임을 분명히 한다(입력은 비활성). */}
      {!canWrite ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>열람 전용입니다, 값은 변경할 수 없습니다. 변경은 관리자, 시스템 관리자만 할 수 있습니다.</Typography> : null}
      {/* bool select, document_automation_enabled(SETTING_LABELS에 라벨 추가됨, MAINTENANCE_KEYS로
          걸러지지 않음)가 이 표에 노출되는 실제 bool 설정이라 이 분기는 지금 실사용된다. 입력은
          FormField와 동일하게 aria-invalid, aria-describedby로 오류/도움말과 프로그래매틱하게 연결한다.
          native select를 쓴다 — 값이 두 개뿐이라 팝업 메뉴보다 가볍고, 키보드/모바일 동작이 OS 기본이다. */}
      {/* save.isPending인 동안엔 !canWrite와 마찬가지로 값 입력을 잠근다, 예전엔 PUT이 도는 사이에도
          계속 타이핑할 수 있어, onSave()가 이미 보낸(제출 시점) 값과 화면에 남은 값이 어긋난 채로
          onSaved()가 그 편집을 조용히 버리고 드로어를 닫을 수 있었다. */}
      {setting.type === "bool" ? (
        <TextField
          select fullWidth size="small" SelectProps={{ native: true }}
          value={String(val)} onChange={(e) => changeVal(e.target.value)}
          error={!!err} disabled={!canWrite || save.isPending}
          inputProps={{ "aria-label": "값", "aria-invalid": !!err, "aria-describedby": describedBy }}
        >
          <option value="true">켜기</option>
          <option value="false">끄기</option>
        </TextField>
      ) : isObjectSetting(setting) ? (
        STRUCTURED_OBJECT_KEYS.includes(setting.key) && !advanced ? (
          <StructuredObjectFields settingKey={setting.key} val={val} onChange={changeVal} canWrite={canWrite && !save.isPending}
            describedBy={describedBy} invalid={!!err} />
        ) : (
          <TextField
            fullWidth multiline minRows={10} size="small"
            value={val} onChange={(e) => changeVal(e.target.value)}
            error={!!err} disabled={!canWrite || save.isPending}
            inputProps={{ "aria-label": "값(JSON)", "aria-invalid": !!err, "aria-describedby": describedBy, spellCheck: false }}
            /* JSON은 사람이 중첩 구조를 손으로 편집한다 — 가변폭 폰트로는 중괄호·들여쓰기가 안 맞는다. */
            InputProps={{ sx: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: "0.8125rem" } }}
          />
        )
      ) : (
        <>
          <TextField
            fullWidth size="small" value={val} onChange={(e) => changeVal(e.target.value)}
            type={setting.type === "int" ? "number" : "text"}
            error={!!err} disabled={!canWrite || save.isPending}
            inputProps={{
              min: intBounds ? intBounds[0] : undefined, max: intBounds ? intBounds[1] : undefined,
              "aria-label": "값", "aria-invalid": !!err, "aria-describedby": describedBy,
            }}
            sx={{ maxWidth: "24rem" }}
          />
          {intBounds ? <Typography variant="caption" color="text.secondary" id="setting-range" sx={{ display: "block", mt: 0.5 }}>허용 범위: {intBounds[0]}~{intBounds[1]}</Typography> : null}
        </>
      )}
      {/* 정해진 스키마가 있는 object 설정은 구조화된 입력↔raw JSON을 오갈 수 있다, 대부분은 구조화된
          입력만으로 충분하지만, 스키마 밖 값을 손봐야 하는 드문 경우를 위해 고급 전환을 남겨둔다. */}
      {isObjectSetting(setting) && STRUCTURED_OBJECT_KEYS.includes(setting.key) ? (
        <Box sx={{ mt: 1.5 }}>
          <Button variant="ghost" size="sm" disabled={advanced && !advancedJsonValid}
            onClick={() => setAdvanced((v) => !v)}>{advanced ? "구조화된 입력으로 전환" : "JSON으로 직접 편집(고급)"}</Button>
        </Box>
      ) : null}
      {advanced && !advancedJsonValid ? <Typography color="error" variant="body2" role="alert" sx={{ mt: 1 }}>JSON 형식이 올바르지 않아 구조화된 입력으로 전환할 수 없습니다, 먼저 JSON을 고치세요.</Typography> : null}
      {isObjectSetting(setting) && (!STRUCTURED_OBJECT_KEYS.includes(setting.key) || advanced) ? <Typography variant="caption" color="text.secondary" id="setting-help" sx={{ display: "block", mt: 1, maxWidth: "70ch" }}>{OBJECT_SCHEMA_HELP[setting.key] || "JSON 형식으로 입력하세요."}</Typography> : null}
      {setting.restart_required ? <Typography variant="body2" sx={{ mt: 1.5 }}>이 설정은 저장 후 서비스를 수동으로 재시작해야 적용됩니다.</Typography> : null}
      {/* 검증 통과는 성공 신호이므로 흐린 힌트 대신 Callout로 확실히 표시한다.
          tone="success"로 '이 항목 저장 시도 예정' 같은 평범한 안내(info)와 구분한다. */}
      {checked ? <Box role="status" sx={{ mt: 2 }}><Callout tone="success">{checked}</Callout></Box> : null}
      {/* 오류는 앱 공통 오류 색(error)으로 — 예전 .k-empty-help는 색이 없어 일반 텍스트로 보였다. */}
      {err ? <Typography color="error" variant="body2" id="setting-err" role="alert" sx={{ mt: 2 }}>{err}</Typography> : null}
    </Drawer>
    {showVersions ? (
      // 롤백 후 부모 편집기를 닫을 때도 requestClose()(같은 미저장 변경 확인)를 거친다, onClose()를
      // 바로 부르면, 편집기에 아직 저장하지 않은 입력(dirty)이 있어도 확인 없이 조용히 버려졌다
      // (오버레이 클릭, Esc, '취소'는 모두 requestClose를 거치는데 이 경로만 예외였다).
      <SettingVersions settingKey={setting.key} label={settingLabel(setting.key)} canWrite={canWrite} currentSetting={setting}
        onClose={() => setShowVersions(false)} onRolledBack={() => { setShowVersions(false); requestClose(); }} />
    ) : null}
    </>
  );
}

/* 버전 기록 + 롤백 — 백엔드는 모든 설정 변경마다 이전 값 스냅샷을 config_versions에 남긴다.
 * GET /{key}/versions로 목록을, POST /{key}/rollback {version}으로 되돌린다(연동·러너·워크플로의
 * '버전 기록' 패턴과 동일). 조회는 읽기 역할도 가능, 롤백은 쓰기 역할만. */
// currentSetting은 선택 — SettingEditor에서 열릴 때만 넘어온다(Ops.jsx의 유지보수 공지 버전
// 기록은 보안 완화 대상 키가 아니므로 넘기지 않아도 안전, securityDowngradeWarning은 아래에서
// currentSetting이 있을 때만 호출한다).
export function SettingVersions({ settingKey, label, canWrite, onClose, onRolledBack, currentSetting }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const vq = useQuery({
    queryKey: ["settings", settingKey, "versions"],
    queryFn: () => api("/api/admin/settings/" + settingKey + "/versions"),
    retry: false,
  });
  const roll = useMutation({
    mutationFn: (version) => api("/api/admin/settings/" + settingKey + "/rollback", { method: "POST", body: { version } }),
  });
  const items = (vq.data && vq.data.items) || [];

  async function doRollback(version, snapshotValue) {
    // 직접 편집(SettingEditor.onSave)은 저장 직전 securityDowngradeWarning으로 보안 완화(도메인 제한
    // 해제·비밀번호 정책 약화·세션 완화)를 danger 확인으로 한 번 더 막는데, 롤백 경로는 그 확인을
    // 전혀 거치지 않고 일반 '버전 N으로 롤백할까요?' 확인만으로 같은 완화를 그대로 적용할 수 있었다 —
    // 옛 버전으로 되돌아가는 것도 지금 값보다 약한 값으로 덮어쓸 수 있는 같은 종류의 위험이다.
    const warnMsg = currentSetting ? securityDowngradeWarning(currentSetting, snapshotValue) : null;
    const ok = await confirm(
      warnMsg ? warnMsg + " (버전 " + version + "(으)로 롤백)" : "버전 " + version + "(으)로 롤백할까요? 현재 값을 이 버전의 값으로 되돌립니다.",
      { danger: true, title: warnMsg ? "보안 설정 변경 확인" : "버전 롤백", confirmLabel: warnMsg ? "변경" : "롤백" });
    if (!ok) return;
    try {
      await roll.mutateAsync(version);
      qc.invalidateQueries({ queryKey: ["settings"] });
      // 롤백 자체가 새 버전 행을 하나 더 만든다 — 이 목록("settings", settingKey, "versions")도 함께
      // 무효화하지 않으면, 기본 30초 staleTime 안에 다시 열었을 때 방금 만든 그 행이 빠진 캐시를 보여준다.
      qc.invalidateQueries({ queryKey: ["settings", settingKey, "versions"] });
      toast("버전 " + version + "(으)로 롤백했습니다.", "success");
      onRolledBack();
    } catch (e) { toast(e.message, "error"); }
  }

  const columns = [
    { key: "version", label: "버전" },
    // 스냅샷은 '교체된(이전) 값'이라 '값'으로 두면 '그 시각에 설정된 값'으로 오독된다 — '이전 값'으로 명확히 한다.
    { key: "value", label: "이전 값", render: (r) => { const v = r.snapshot ? r.snapshot.value : undefined; return summarizeSetting(settingKey, v) || displayValue(v); } },
    { key: "created_at", label: "변경 시각", render: (r) => (r.created_at ? fmtDateTime(r.created_at) : "-") },
  ];
  if (canWrite) columns.push({
    key: "__roll", label: "", align: "right",
    // 직접 편집(SettingEditor.onSave)은 securityDowngradeWarning이 참일 때만 danger 확인을 쓰고,
    // 평범한 저장(예: conversation_retention_days 90→30)은 기본 톤이다 — 롤백 버튼만 종류와 무관하게
    // 항상 빨간색이라, 보안과 무관한 설정도 위험해 보이는 경보 피로를 줬다. 같은 판정 함수로 톤을 맞춘다.
    render: (r) => {
      const snapshotValue = r.snapshot ? r.snapshot.value : undefined;
      const warnMsg = currentSetting ? securityDowngradeWarning(currentSetting, snapshotValue) : null;
      return <Button variant={warnMsg ? "danger" : "default"} size="sm" disabled={roll.isPending} onClick={() => doRollback(r.version, snapshotValue)}>이 버전으로 롤백</Button>;
    },
  });

  const footer = (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Box className="k-footer-main"><Button variant="ghost" onClick={onClose}>닫기</Button></Box>
    </Box>
  );
  return (
    <Drawer open onClose={onClose} title={label + ", 버전 기록"} size="lg" footer={footer}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: "70ch" }}>
        각 버전은 그 시점으로 되돌릴 수 있는 값 스냅샷입니다. 롤백은 현재 값을 선택한 버전으로 되돌리며 새 변경으로 다시 기록됩니다.
      </Typography>
      {/* 목록 자체는 페이지네이션 없이 전체를 보여준다(app/core/versioning.py list_versions에 상한 없음) —
          자주 손보는 설정은 기록이 눈에 안 띄게 계속 늘어날 수 있어, 최소한 개수라도 먼저 보여준다
          (DataScreen의 capWarning과 같은 취지 — '이 목록이 얼마나 긴지' 모르는 채로 스크롤하지 않게). */}
      {!vq.isLoading && !vq.isError && items.length > 0 ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>{items.length}건</Typography> : null}
      {vq.isLoading ? <Skeleton lines={4} />
        : vq.isError ? <ErrorState error={vq.error} onRetry={() => vq.refetch()} />
        : items.length === 0 ? <EmptyState title="버전 기록이 없습니다" help="이 설정을 아직 변경한 적이 없습니다." />
        : <Card><DataTable columns={columns} rows={items} rowKey={(r) => r.version} /></Card>}
    </Drawer>
  );
}
