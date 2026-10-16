import React, { useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import { Button, Callout, Tag, FieldLabel } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";
import { fmtDuration } from "./settingsRegistry.js";

// 스키마가 정해진 object 설정을 타입에 맞는 입력으로 편집한다. 값의 참(source of truth)은 여전히
// SettingEditor의 JSON 문자열(val)이다 — 여기선 그 문자열을 파싱해 보여주고, 바뀌면 다시
// JSON.stringify해 onChange(=changeVal)로 돌려보낸다. 이렇게 하면 coerce()/dirty/저장 로직을
// 그대로 재사용하면서 입력만 사람이 읽는 필드로 바꿀 수 있다.
const WEEKDAYS = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"];

/* cron 다섯 칸이 자주 쓰는 셋 중 하나인가. 아니면 `직접 입력` 으로 떨어진다 —
 * **표현력을 줄이지 않는 것이 이 판정의 목적이다**: 못 알아보는 표현식을 만나면 화면이
 * 그것을 지우거나 근사하지 않고 원문 그대로 편집하게 둔다. */
function cronPreset(parts) {
  if (parts.length !== 5) return null;
  const [m, h, dom, mon, dow] = parts;
  const num = (v) => /^\d+$/.test(v);
  if (!num(m) || !num(h) || mon !== "*") return null;
  if (dom === "*" && dow === "*") return "daily";
  if (dom === "*" && num(dow)) return "weekly";
  if (num(dom) && dow === "*") return "monthly";
  return null;
}

export function StructuredObjectFields({ settingKey, val, onChange, canWrite, describedBy, invalid }) {
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
        setDomainErr("도메인 형식이 아닙니다. 점(.)을 포함해야 합니다(예: example.com).");
        return;
      }
      if (domains.includes(d)) { setDomainErr("이미 추가된 도메인입니다."); return; }
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
        <Typography component="span" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, display: "block", mb: 1 }}>허용 이메일 도메인</Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 1.5 }}>
          {domains.length ? domains.map((d) => (
            // MUI Chip의 onDelete 아이콘은 tabIndex=-1이라 키보드로 못 뗀다(AssistantDrawer.jsx의
            // 첨부 제거 버튼과 같은 이유로 이미 이 저장소에 적힌 함정) — 칩 옆에 독립적으로
            // 포커스되는 IconButton을 따로 둔다.
            <Box key={d} sx={{ display: "inline-flex", alignItems: "center", gap: 0.25 }}>
              <Tag label={d} />
              {canWrite ? (
                /* 크기는 테마의 작은 아이콘 단추(30)다 — 여백을 손으로 줄이면 누를 자리가 24 아래로 줄었다. */
                <IconButton size="small" aria-label={d + " 삭제"} onClick={() => removeDomain(d)}>
                  <CloseRoundedIcon sx={{ fontSize: FONT_SIZE.body }} />
                </IconButton>
              ) : null}
            </Box>
          )) : <Typography variant="body2" color="text.secondary">제한 없음(모든 이메일 도메인 허용)</Typography>}
        </Box>
        {canWrite ? (
          <>
            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", flexWrap: "wrap" }}>
              <TextField
                id={domainInputId} size="small" placeholder="예: example.com" value={draft}
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
            {domainErr ? <Box id={domainErrId} sx={{ mt: 1 }}><Callout tone="danger" compact>{domainErr}</Callout></Box> : null}
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
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={minLenId}>최소 글자 수(8~128자)</FieldLabel>
          <TextField
            id={minLenId} type="number" size="small" fullWidth disabled={!canWrite}
            error={!!invalid}
            inputProps={{ min: 8, max: 128, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.min_length != null ? safe.min_length : ""}
            onChange={(e) => patch({ min_length: e.target.value === "" ? null : Number(e.target.value) })}
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={minClassesId}>문자 종류 수(1~4)</FieldLabel>
          <TextField
            id={minClassesId} type="number" size="small" fullWidth disabled={!canWrite}
            error={!!invalid}
            inputProps={{ min: 1, max: 4, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.min_classes != null ? safe.min_classes : ""}
            onChange={(e) => patch({ min_classes: e.target.value === "" ? null : Number(e.target.value) })}
          />
        </Box>
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
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={idleId}>유휴 제한(분, 최소 1분)</FieldLabel>
            <TextField
              id={idleId} type="number" size="small" fullWidth disabled={!canWrite}
              error={!!invalid}
              inputProps={{ min: 1, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={idleMin}
              onChange={(e) => patch({ idle_timeout_seconds: e.target.value === "" ? null : Math.round(Number(e.target.value) * 60) })}
            />
          </Box>
          {/* 분 단위 숫자만으론 시간 규모(예: 480 = 8시간)를 확인하기 어렵다, 표 요약과 같은
              fmtDuration으로 사람이 읽는 값을 바로 옆에 함께 보여준다. */}
          {safe.idle_timeout_seconds != null ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>= {fmtDuration(safe.idle_timeout_seconds)}</Typography> : null}
        </Box>
        <Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={absId}>최대 세션 길이(분, 최소 1분)</FieldLabel>
            <TextField
              id={absId} type="number" size="small" fullWidth disabled={!canWrite}
              error={!!invalid}
              inputProps={{ min: 1, step: 1, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={absMin}
              onChange={(e) => patch({ absolute_timeout_seconds: e.target.value === "" ? null : Math.round(Number(e.target.value) * 60) })}
            />
          </Box>
          {safe.absolute_timeout_seconds != null ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>= {fmtDuration(safe.absolute_timeout_seconds)}</Typography> : null}
        </Box>
      </Box>
    );
  }
  if (settingKey === "lockout_policy") {
    // ADM-05: 예전엔 env 전용이라 화면에서 볼 수도 바꿀 수도 없었다 — session_policy와 같은
    // 이유로 분 단위 입력 + 초 단위 저장(잠금 시간)을 쓴다. 실패 임계값은 그대로 정수.
    const lockMin = safe.lock_seconds != null ? Math.round(safe.lock_seconds / 60) : "";
    const maxId = fieldId("max_failures");
    const lockId = fieldId("lock_minutes");
    return (
      <Box sx={pairGrid}>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={maxId}>로그인 실패 임계값(1~20회)</FieldLabel>
          <TextField
            id={maxId} type="number" size="small" fullWidth disabled={!canWrite}
            error={!!invalid}
            inputProps={{ min: 1, max: 20, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.max_failures != null ? safe.max_failures : ""}
            onChange={(e) => patch({ max_failures: e.target.value === "" ? null : Number(e.target.value) })}
          />
        </Box>
        <Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={lockId}>잠금 시간(분, 최소 1분)</FieldLabel>
            <TextField
              id={lockId} type="number" size="small" fullWidth disabled={!canWrite}
              error={!!invalid}
              inputProps={{ min: 1, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={lockMin}
              onChange={(e) => patch({ lock_seconds: e.target.value === "" ? null : Math.round(Number(e.target.value) * 60) })}
            />
          </Box>
          {safe.lock_seconds != null ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>= {fmtDuration(safe.lock_seconds)}</Typography> : null}
        </Box>
      </Box>
    );
  }
  if (settingKey === "backup_schedule") {
    /* 백업 일정은 `cron` 이 정본이지만(백엔드가 저장 시점에 검증한다), **cron 문법이 화면의
       주된 인터페이스일 이유는 없다**(지시 32 · 36). `0 3 * * *` 를 읽을 줄 아는 사람만
       백업 시각을 바꿀 수 있는 상태였다.

       자주 쓰는 셋(매일 · 매주 · 매월)은 시각만 고르면 되게 하고, 그 밖은 `직접 입력` 으로
       cron 을 그대로 받는다 — 표현력을 줄이지 않으면서 흔한 경우를 쉽게 만든다. */
    const cron = String(safe.cron || "");
    const parts = cron.trim().split(/\s+/);
    const preset = cronPreset(parts);
    const hour = preset ? Number(parts[1]) : 3;
    const minute = preset ? Number(parts[0]) : 0;
    const weekday = preset === "weekly" ? String(parts[4]) : "0";
    const day = preset === "monthly" ? String(parts[2]) : "1";
    const setCron = (next) => patch({ cron: next });

    return (
      <Box sx={{ display: "grid", gap: 2.5 }}>
        <Box sx={pairGrid}>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={fieldId("enabled")}>자동 백업</FieldLabel>
            <TextField
              id={fieldId("enabled")} select size="small" fullWidth disabled={!canWrite}
              error={!!invalid} SelectProps={{ native: true }}
              inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={safe.enabled ? "true" : "false"}
              onChange={(e) => patch({ enabled: e.target.value === "true" })}
            >
              <option value="true">사용</option>
              <option value="false">사용 안 함</option>
            </TextField>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={fieldId("keep")}>남길 백업 개수(1~365)</FieldLabel>
            <TextField
              id={fieldId("keep")} type="number" size="small" fullWidth
              disabled={!canWrite} error={!!invalid}
              helperText="최근 이 개수만큼은 나이와 상관없이 남습니다."
              inputProps={{ min: 1, max: 365, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={safe.keep != null ? safe.keep : ""}
              onChange={(e) => patch({ keep: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </Box>
        </Box>

        {/* 🔴 **보관 기간을 화면에서 고칠 수 없었다** (2026-09-01).
            서버는 개수와 나이를 **둘 다** 보고 지운다(`app/backups/service.py::apply_retention`
            — 개수만 걸면 하루에 여러 번 돌린 날이 지난 주를 통째로 밀어낸다). 그런데 이
            편집기에는 개수 칸만 있었다. 그래서 「복구 리허설」 화면은 «보관 기간 7일» 이라는
            카드를 보여 주는데 그 값을 바꿀 자리가 제품 어디에도 없었고, 이 설정의 설명문
            («정한 개수와 기간만큼 남깁니다»)은 절반이 지킬 수 없는 약속이었다.
            0 은 「개수만으로 자른다」를 **명시적으로** 고르는 값이라 허용한다(서버도 그렇다). */}
        <Box sx={pairGrid}>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={fieldId("keep_days")}>보관 기간(0~365일)</FieldLabel>
            <TextField
              id={fieldId("keep_days")} type="number" size="small" fullWidth
              disabled={!canWrite} error={!!invalid}
              helperText="이 기간 안에 만든 백업은 개수를 넘어도 남습니다. 0이면 개수로만 정리합니다."
              inputProps={{ min: 0, max: 365, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={safe.keep_days != null ? safe.keep_days : ""}
              onChange={(e) => patch({ keep_days: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </Box>
        </Box>

        <Box sx={pairGrid}>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={fieldId("cron-preset")}>주기</FieldLabel>
            <TextField
              id={fieldId("cron-preset")} select size="small" fullWidth disabled={!canWrite}
              error={!!invalid} SelectProps={{ native: true }}
              inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
              value={preset || "custom"}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "daily") setCron(`${minute} ${hour} * * *`);
                else if (v === "weekly") setCron(`${minute} ${hour} * * ${weekday}`);
                else if (v === "monthly") setCron(`${minute} ${hour} ${day} * *`);
                // '직접 입력'으로 옮길 때는 지금 값을 그대로 둔다 — 고르는 순간 값이 사라지면
                // 사용자는 자기가 뭘 지웠는지 모른다.
              }}
            >
              <option value="daily">매일</option>
              <option value="weekly">매주</option>
              <option value="monthly">매월</option>
              <option value="custom">직접 입력</option>
            </TextField>
          </Box>
          {preset ? (
            <Box sx={{ minWidth: 0 }}>
              <FieldLabel htmlFor={fieldId("cron-time")}>시각</FieldLabel>
              <TextField
                id={fieldId("cron-time")} type="time" size="small" fullWidth
                disabled={!canWrite} error={!!invalid}
                inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
                value={`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`}
                onChange={(e) => {
                  const [h, m] = String(e.target.value || "0:0").split(":").map((x) => Number(x) || 0);
                  if (preset === "daily") setCron(`${m} ${h} * * *`);
                  else if (preset === "weekly") setCron(`${m} ${h} * * ${weekday}`);
                  else setCron(`${m} ${h} ${day} * *`);
                }}
              />
            </Box>
          ) : null}
        </Box>

        {preset === "weekly" ? (
          <Box sx={pairGrid}>
            <Box sx={{ minWidth: 0 }}>
              <FieldLabel htmlFor={fieldId("cron-weekday")}>요일</FieldLabel>
              <TextField
                id={fieldId("cron-weekday")} select size="small" fullWidth disabled={!canWrite}
                error={!!invalid} SelectProps={{ native: true }}
                inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
                value={weekday}
                onChange={(e) => setCron(`${minute} ${hour} * * ${e.target.value}`)}
              >
                {WEEKDAYS.map((w, i) => <option key={w} value={String(i)}>{w}</option>)}
              </TextField>
            </Box>
          </Box>
        ) : null}

        {preset === "monthly" ? (
          <Box sx={pairGrid}>
            <Box sx={{ minWidth: 0 }}>
              <FieldLabel htmlFor={fieldId("cron-day")}>날짜(1~28일)</FieldLabel>
              <TextField
                id={fieldId("cron-day")} type="number" size="small" fullWidth
                disabled={!canWrite} error={!!invalid}
                helperText="29~31일은 없는 달이 있어 그 달에는 실행되지 않습니다."
                inputProps={{ min: 1, max: 28, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
                value={day}
                onChange={(e) => setCron(`${minute} ${hour} ${e.target.value || 1} * *`)}
              />
            </Box>
          </Box>
        ) : null}

        {!preset ? (
          <Box sx={pairGrid}>
            <Box>
              <Box sx={{ minWidth: 0 }}>
                <FieldLabel htmlFor={fieldId("cron")}>Cron 식</FieldLabel>
                <TextField
                  id={fieldId("cron")} size="small" fullWidth disabled={!canWrite}
                  error={!!invalid} placeholder="0 3 * * *"
                  inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy, spellCheck: false }}
                  value={cron} onChange={(e) => setCron(e.target.value)}
                />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                분 시 일 월 요일 순서입니다. 예: <code>0 3 * * *</code> = 매일 새벽 3시.
              </Typography>
            </Box>
          </Box>
        ) : null}

        <Box sx={pairGrid}>
          <Box sx={{ minWidth: 0 }}>
            <FieldLabel htmlFor={fieldId("timezone")}>기준 시간대</FieldLabel>
            <TextField
              id={fieldId("timezone")} size="small" fullWidth disabled={!canWrite}
              error={!!invalid} placeholder="Asia/Seoul"
              inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy, spellCheck: false }}
              value={safe.timezone || ""} onChange={(e) => patch({ timezone: e.target.value })}
            />
          </Box>
        </Box>
      </Box>
    );
  }
  if (settingKey === "ui_branding") {
    const nameId = fieldId("product_name");
    const emailId = fieldId("support_email");
    return (
      <Box sx={pairGrid}>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={nameId}>제품명</FieldLabel>
          <TextField
            id={nameId} size="small" fullWidth disabled={!canWrite} error={!!invalid}
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.product_name || ""} onChange={(e) => patch({ product_name: e.target.value })}
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={emailId}>지원 이메일</FieldLabel>
          <TextField
            id={emailId} size="small" fullWidth disabled={!canWrite} error={!!invalid}
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.support_email || ""} onChange={(e) => patch({ support_email: e.target.value })}
          />
        </Box>
      </Box>
    );
  }
  return null;
}
