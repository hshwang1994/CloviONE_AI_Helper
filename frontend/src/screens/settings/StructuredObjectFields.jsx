import React, { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import { Button } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../../ui/theme.js";
import { fmtDuration } from "./settingsRegistry.js";

// 스키마가 정해진 object 설정을 타입에 맞는 입력으로 편집한다. 값의 참(source of truth)은 여전히
// SettingEditor의 JSON 문자열(val)이다 — 여기선 그 문자열을 파싱해 보여주고, 바뀌면 다시
// JSON.stringify해 onChange(=changeVal)로 돌려보낸다. 이렇게 하면 coerce()/dirty/저장 로직을
// 그대로 재사용하면서 입력만 사람이 읽는 필드로 바꿀 수 있다.
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
        setDomainErr("도메인 형식이 아닙니다(예: example.com), 점(.)을 포함해야 합니다.");
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
              <Chip label={d} size="small" variant="outlined" />
              {canWrite ? (
                <IconButton size="small" aria-label={d + " 제거"} onClick={() => removeDomain(d)}
                  sx={{ p: 0.25 }}>
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
  if (settingKey === "lockout_policy") {
    // ADM-05: 예전엔 env 전용이라 화면에서 볼 수도 바꿀 수도 없었다 — session_policy와 같은
    // 이유로 분 단위 입력 + 초 단위 저장(잠금 시간)을 쓴다. 실패 임계값은 그대로 정수.
    const lockMin = safe.lock_seconds != null ? Math.round(safe.lock_seconds / 60) : "";
    const maxId = fieldId("max_failures");
    const lockId = fieldId("lock_minutes");
    return (
      <Box sx={pairGrid}>
        <TextField
          id={maxId} label="로그인 실패 임계값(1~20회)" type="number" size="small" fullWidth disabled={!canWrite}
          error={!!invalid}
          inputProps={{ min: 1, max: 20, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
          value={safe.max_failures != null ? safe.max_failures : ""}
          onChange={(e) => patch({ max_failures: e.target.value === "" ? null : Number(e.target.value) })}
        />
        <Box>
          <TextField
            id={lockId} label="잠금 시간(분, 최소 1분)" type="number" size="small" fullWidth disabled={!canWrite}
            error={!!invalid}
            inputProps={{ min: 1, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={lockMin}
            onChange={(e) => patch({ lock_seconds: e.target.value === "" ? null : Math.round(Number(e.target.value) * 60) })}
          />
          {safe.lock_seconds != null ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>= {fmtDuration(safe.lock_seconds)}</Typography> : null}
        </Box>
      </Box>
    );
  }
  if (settingKey === "smtp") {
    /* 메일 설정은 이 저장소에서 마지막까지 **JSON 원문 편집**으로 남아 있었다(지시 32 · 36).
       그래서 관리자는 중괄호를 손으로 맞추고, `security` 에 무엇을 쓸 수 있는지는 힌트 문장을
       읽어야 알았고, 오타는 저장 왕복 뒤에야 드러났다. 필드마다 이름과 허용값을 준다.

       **비밀번호 자체는 여기서 받지 않는다.** 백엔드 검증기(registry.py::_smtp)가 `password`
       계열 키를 모양이 맞아도 거절한다 - DB 설정은 관리 API 와 진단 번들에 실리므로 값이
       들어오는 순간 평문이 응답을 타고 나간다(불변 §3). 화면도 같은 경계를 지켜, 서버에 둔
       파일의 **이름**만 받는다. */
    const secId = fieldId("security");
    return (
      <Box sx={{ display: "grid", gap: 2.5 }}>
        <Box sx={pairGrid}>
          <TextField
            id={fieldId("enabled")} select label="메일 발송" size="small" fullWidth disabled={!canWrite}
            error={!!invalid} SelectProps={{ native: true }}
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.enabled ? "true" : "false"}
            onChange={(e) => patch({ enabled: e.target.value === "true" })}
          >
            <option value="true">사용</option>
            <option value="false">사용 안 함</option>
          </TextField>
          <TextField
            id={secId} select label="보안 연결" size="small" fullWidth disabled={!canWrite}
            error={!!invalid} SelectProps={{ native: true }}
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.security || "starttls"}
            onChange={(e) => patch({ security: e.target.value })}
          >
            <option value="starttls">STARTTLS(587 포트에서 주로 씁니다)</option>
            <option value="ssl">SSL(465 포트에서 주로 씁니다)</option>
            <option value="none">사용 안 함(사내망에서만)</option>
          </TextField>
        </Box>
        <Box sx={pairGrid}>
          <TextField
            id={fieldId("host")} label="메일 서버 주소" size="small" fullWidth disabled={!canWrite} error={!!invalid}
            placeholder="smtp.example.com"
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy, spellCheck: false }}
            value={safe.host || ""} onChange={(e) => patch({ host: e.target.value })}
          />
          <TextField
            id={fieldId("port")} label="포트(1~65535)" type="number" size="small" fullWidth disabled={!canWrite} error={!!invalid}
            inputProps={{ min: 1, max: 65535, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.port != null ? safe.port : ""}
            onChange={(e) => patch({ port: e.target.value === "" ? null : Number(e.target.value) })}
          />
        </Box>
        <Box sx={pairGrid}>
          <TextField
            id={fieldId("from_address")} label="보내는 사람 주소" size="small" fullWidth disabled={!canWrite} error={!!invalid}
            placeholder="portal@example.com"
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy, spellCheck: false }}
            value={safe.from_address || ""} onChange={(e) => patch({ from_address: e.target.value })}
          />
          <TextField
            id={fieldId("from_name")} label="보내는 사람 이름" size="small" fullWidth disabled={!canWrite} error={!!invalid}
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.from_name || ""} onChange={(e) => patch({ from_name: e.target.value })}
          />
        </Box>
        <Box sx={pairGrid}>
          <TextField
            id={fieldId("username")} label="로그인 계정(필요할 때만)" size="small" fullWidth disabled={!canWrite} error={!!invalid}
            inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy, spellCheck: false }}
            value={safe.username || ""} onChange={(e) => patch({ username: e.target.value })}
          />
          <Box>
            <TextField
              id={fieldId("password_ref")} label="비밀번호 파일 이름" size="small" fullWidth disabled={!canWrite} error={!!invalid}
              inputProps={{ "aria-invalid": ariaInvalid, "aria-describedby": describedBy, spellCheck: false }}
              value={safe.password_ref || ""} onChange={(e) => patch({ password_ref: e.target.value })}
            />
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              비밀번호 자체는 적지 않습니다. 서버에 미리 둔 파일의 이름만 적습니다.
            </Typography>
          </Box>
        </Box>
        <Box sx={pairGrid}>
          <TextField
            id={fieldId("timeout_seconds")} label="응답 대기 시간(초, 1~300)" type="number" size="small" fullWidth disabled={!canWrite} error={!!invalid}
            inputProps={{ min: 1, max: 300, "aria-invalid": ariaInvalid, "aria-describedby": describedBy }}
            value={safe.timeout_seconds != null ? safe.timeout_seconds : ""}
            onChange={(e) => patch({ timeout_seconds: e.target.value === "" ? null : Number(e.target.value) })}
          />
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
