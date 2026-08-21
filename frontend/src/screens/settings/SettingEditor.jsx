import React, { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { Button, Callout, Modal, useConfirm } from "../../ui/kit.jsx";
import { FONT_SIZE } from "../../ui/theme.js";
import { settingLabel, OBJECT_SCHEMA_HELP, STRUCTURED_OBJECT_KEYS, INT_BOUNDS, securityDowngradeWarning } from "./settingsRegistry.js";
import { StructuredObjectFields } from "./StructuredObjectFields.jsx";
import { SettingVersions } from "./SettingVersions.jsx";

// object 타입 판정 — 타입 문자열이 object이거나 값 자체가 객체/배열이면 JSON 편집기를 쓴다.
export function isObjectSetting(setting) {
  return setting.type === "object" || setting.type === "json" || (setting.value !== null && typeof setting.value === "object");
}

export function SettingEditor({ setting, canWrite, onClose, onSaved }) {
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
            throw new Error("도메인 형식이 올바르지 않습니다(예: example.com), 점(.)을 포함하고 앞뒤에 점이 없어야 합니다: " + JSON.stringify(d));
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
      setChecked(dirty ? "검증을 통과했습니다. 저장할 수 있습니다." : "검증을 통과했습니다. 현재 값과 같습니다.");
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
      const ok = await confirm("수정한 내용이 저장되지 않았습니다. 닫을까요?", { danger: true, confirmLabel: "닫기" });
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
        {/* 쓰기 권한이 없어도 버튼을 지우지 않는다 — 비활성 + 위 안내문(aria-describedby)으로
            '있지만 지금은 못 누른다'를 보여 준다(Maintenance.jsx 가 같은 실수를 겪고 고친 관례). */}
        <Button onClick={onCheck} disabled={!canWrite || dryRun.isPending} aria-describedby={canWrite ? undefined : "setting-locked-reason"}>{dryRun.isPending ? "검증 중…" : "미리 검증"}</Button>
        {/* 변경이 없으면 저장을 막는다, 같은 값 재저장은 config_versions, 감사 로그에 no-op을 쌓는다. */}
        <Button variant="primary" onClick={onSave} disabled={!canWrite || save.isPending || !dirty} aria-describedby={canWrite ? undefined : "setting-locked-reason"}>{save.isPending ? "저장 중…" : "저장"}</Button>
      </Box>
    </Box>
  );
  return (
    <>
    <Modal open={!!setting} onClose={requestClose} title={settingLabel(setting.key)} footer={footer}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{setting.key} ({setting.is_default ? "기본값" : "수정됨"})</Typography>
      <Typography variant="body2" id="setting-desc" sx={{ mt: 0.5, mb: 2.5 }}>{setting.description}</Typography>
      {/* 읽기 전용 역할에겐 이 서랍이 '잠긴 편집 폼'이 아니라 '상세 보기'임을 분명히 한다(입력은 비활성). */}
      {!canWrite ? <Typography id="setting-locked-reason" variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>열람 전용입니다. 값은 수정할 수 없습니다. 수정은 관리자, 시스템 관리자만 할 수 있습니다.</Typography> : null}
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
          <option value="true">활성화</option>
          <option value="false">비활성화</option>
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
            InputProps={{ sx: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: FONT_SIZE.bodySm } }}
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
            onClick={() => setAdvanced((v) => !v)}>{advanced ? "구조화된 입력으로 전환" : "JSON으로 직접 수정(고급)"}</Button>
        </Box>
      ) : null}
      {advanced && !advancedJsonValid ? <Typography color="error" variant="body2" role="alert" sx={{ mt: 1 }}>JSON 형식이 올바르지 않아 구조화된 입력으로 전환할 수 없습니다. 먼저 JSON을 고치세요.</Typography> : null}
      {isObjectSetting(setting) && (!STRUCTURED_OBJECT_KEYS.includes(setting.key) || advanced) ? <Typography variant="caption" color="text.secondary" id="setting-help" sx={{ display: "block", mt: 1 }}>{OBJECT_SCHEMA_HELP[setting.key] || "JSON 형식으로 입력하세요."}</Typography> : null}
      {setting.restart_required ? <Typography variant="body2" sx={{ mt: 1.5 }}>이 설정은 저장 후 서비스를 수동으로 재시작해야 적용됩니다.</Typography> : null}
      {/* 검증 통과는 성공 신호이므로 흐린 힌트 대신 Callout로 확실히 표시한다.
          tone="success"로 '이 항목 저장 시도 예정' 같은 평범한 안내(info)와 구분한다. */}
      {checked ? <Box role="status" sx={{ mt: 2 }}><Callout tone="success">{checked}</Callout></Box> : null}
      {/* 오류는 앱 공통 오류 색(error)으로 — 예전 .k-empty-help는 색이 없어 일반 텍스트로 보였다. */}
      {err ? <Typography color="error" variant="body2" id="setting-err" role="alert" sx={{ mt: 2 }}>{err}</Typography> : null}
    </Modal>
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
