import React, { useState } from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Card, DataTable, Modal, Callout, useConfirm, useToast } from "../ui/kit.jsx";

/* 사용자 대량 작업 + CSV 가져오기/내보내기 (PLAN Phase 6)
 *
 * Users.jsx에서 떼어 낸 이유는 길이뿐이 아니다 — 이 두 기능은 목록 화면의 상태(검색·필터·
 * 페이지)와 얽히지 않는다. 선택 집합과 '지금 걸린 필터의 쿼리 문자열' 두 값만 받으면 된다.
 *
 * 설계 원칙 두 가지:
 *   * **부분 실패를 숨기지 않는다.** 서버가 건별 결과를 돌려주므로 실패 건을 그대로 보여 준다.
 *   * **가져오기는 미리보기가 먼저다.** dry-run 결과를 표로 보여 주고, 그 화면에서만 실제
 *     적용 버튼이 뜬다. 확인 없이 100명이 생기는 버튼은 아무도 못 누른다.
 */

const BULK_ACTIONS = [
  { value: "disable", label: "비활성화", danger: true, confirm: "선택한 계정을 비활성화할까요? 로그인할 수 없게 됩니다." },
  { value: "enable", label: "활성화", confirm: "선택한 계정을 다시 활성화할까요?" },
  { value: "archive", label: "보관", danger: true, confirm: "선택한 계정을 보관할까요? 목록에서 사라지지만 기록은 남고 복구할 수 있습니다." },
  { value: "unarchive", label: "보관 복구", confirm: "선택한 계정을 복구할까요?" },
  { value: "unlock", label: "잠금 해제", confirm: "선택한 계정의 잠금을 해제할까요?" },
  { value: "revoke_sessions", label: "세션 해제", danger: true, confirm: "선택한 계정의 모든 로그인 세션을 끊을까요?" },
];

const IMPORT_STATUS = {
  ready: { label: "생성 예정", kind: "ok" },
  created: { label: "생성됨", kind: "ok" },
  skipped: { label: "건너뜀", kind: "neutral" },
  failed: { label: "실패", kind: "danger" },
};

const SAMPLE_CSV = "이메일,이름,역할,부서,직책\nhong@example.com,홍길동,user,개발팀,팀원\n";

/* 선택 바 — 몇 명을 골랐는지와 그들에게 할 수 있는 일. 선택이 없으면 아무것도 그리지 않는다. */
export function BulkBar({ selection, deptOptions, titleOptions, onDone }) {
  const [busy, setBusy] = useState(null);
  const [assign, setAssign] = useState({ action: "", value: "" });
  const confirm = useConfirm();
  const toast = useToast();
  const ids = Array.from(selection.selected);
  if (!ids.length) return null;

  async function apply(action, value, confirmMsg) {
    if (confirmMsg && !(await confirm(confirmMsg + `\n\n대상 ${ids.length}명.`, { danger: true }))) return;
    setBusy(action);
    try {
      const res = await api("/api/admin/users/bulk/apply", {
        method: "POST", body: { user_ids: ids, action, value: value || null },
      });
      const changed = (res.applied || []).filter((r) => r.changed).length;
      const failed = (res.failed || []).length;
      // 실패를 성공 토스트로 덮지 않는다 — 몇 명이 왜 안 됐는지 숫자와 첫 사유를 함께 말한다.
      if (failed) {
        toast(`${changed}명 적용, ${failed}명 실패: ${res.failed[0].error}`, "error");
      } else {
        toast(`${res.action_label} — ${changed}명 적용(${ids.length - changed}명은 이미 그 상태)`, "success");
      }
      selection.clear();
      onDone();
    } catch (e) {
      if (e && e.status === 401) { toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error"); window.setTimeout(() => { window.location.href = "/login"; }, 1200); return; }
      toast(e.message, "error");
    } finally { setBusy(null); }
  }

  const assignOptions = assign.action === "set_department" ? deptOptions : titleOptions;
  return (
    <Card sx={{ p: 2, mb: 2.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>{ids.length}명 선택</Typography>
        {BULK_ACTIONS.map((a) => (
          <Button key={a.value} size="sm" variant={a.danger ? "danger" : "default"} disabled={!!busy}
            onClick={() => apply(a.value, null, a.confirm)}>
            {busy === a.value ? "처리 중…" : a.label}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={selection.clear}>선택 해제</Button>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1.5 }}>
        <TextField select size="small" label="일괄 지정" value={assign.action}
          SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
          sx={{ minWidth: "10rem" }}
          onChange={(e) => setAssign({ action: e.target.value, value: "" })}>
          <MenuItem value="">지정 안 함</MenuItem>
          <MenuItem value="set_department">부서</MenuItem>
          <MenuItem value="set_title">직책</MenuItem>
        </TextField>
        {assign.action ? (
          <TextField select size="small" label="값" value={assign.value}
            SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
            sx={{ minWidth: "12rem" }}
            onChange={(e) => setAssign((s) => ({ ...s, value: e.target.value }))}>
            {(assignOptions || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        ) : null}
        {assign.action ? (
          <Button size="sm" variant="primary" disabled={!!busy}
            onClick={() => apply(assign.action, assign.value,
              assign.action === "set_department" ? "선택한 계정의 부서를 일괄 변경할까요?" : "선택한 계정의 직책을 일괄 변경할까요?")}>
            적용
          </Button>
        ) : null}
      </Box>
    </Card>
  );
}

/* CSV 도구 — 내보내기는 지금 걸린 필터 그대로, 가져오기는 미리보기가 먼저다. */
export function CsvTools({ exportQuery, onImported }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {/* 내보내기는 실제 파일 다운로드라 fetch가 아니라 링크다(브라우저가 파일로 저장한다).
          세션 쿠키는 same-origin 요청에 그대로 실린다. */}
      {/* type={undefined} — kit의 Button은 기본 type="button"을 붙이는데, 앵커로 렌더될 때
          그 속성은 링크의 MIME 힌트로 읽혀 의미가 없다(rest 스프레드가 뒤라 여기서 지운다). */}
      <Button component="a" type={undefined}
        href={"/api/admin/users/export/csv" + (exportQuery ? "?" + exportQuery : "")}>
        CSV 내보내기
      </Button>
      <Button onClick={() => setOpen(true)}>CSV 가져오기</Button>
      {open ? <ImportModal onClose={() => setOpen(false)} onImported={onImported} /> : null}
    </>
  );
}

function ImportModal({ onClose, onImported }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function send(dryRun) {
    setBusy(true);
    try {
      const res = await api("/api/admin/users/import/csv", {
        method: "POST", body: { csv_text: text, dry_run: dryRun },
      });
      setPreview(res);
      if (!dryRun) {
        toast(`${res.created}명을 만들었습니다(건너뜀 ${res.skipped}, 실패 ${res.failed}).`,
          res.failed ? "error" : "success");
        onImported();
      }
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  const columns = [
    { key: "line", label: "줄" },
    { key: "email", label: "이메일" },
    { key: "display_name", label: "이름" },
    { key: "status", label: "결과", render: (r) => {
      const s = IMPORT_STATUS[r.status] || { label: r.status, kind: "neutral" };
      return <Badge value={s.label} kind={s.kind} />;
    } },
    { key: "message", label: "설명" },
  ];
  const applied = preview && preview.dry_run === false;

  const footer = (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Box className="k-footer-main">
        <Button onClick={onClose}>{applied ? "닫기" : "취소"}</Button>
        {!applied ? (
          <>
            <Button disabled={busy || !text.trim()} onClick={() => send(true)}>
              {busy ? "확인 중…" : "미리 보기"}
            </Button>
            <Button variant="primary" disabled={busy || !preview || !preview.created}
              onClick={() => send(false)}>
              {preview ? `${preview.created}명 만들기` : "미리 보기를 먼저 하세요"}
            </Button>
          </>
        ) : null}
      </Box>
    </Box>
  );

  return (
    <Modal open onClose={onClose} title="CSV로 사용자 가져오기" size="lg" footer={footer}>
      <Callout>
        <Box component="p" sx={{ m: 0 }}>
          <strong>이메일</strong>과 <strong>이름</strong> 열이 필요합니다. 역할·부서·직책은 선택입니다(부서·직책은 <em>이름</em>으로 씁니다).
        </Box>
        <Box component="p" sx={{ m: 0, mt: 0.75 }}>
          가져오기는 <strong>새 계정만 만듭니다</strong> — 이미 있는 이메일은 건너뜁니다(기존 계정을 조용히 덮어쓰지 않습니다).
        </Box>
        <Box component="p" sx={{ m: 0, mt: 0.75 }}>
          만들어진 계정은 임시 비밀번호가 발급되고 첫 로그인 시 변경을 요구합니다.
        </Box>
      </Callout>
      <TextField
        multiline minRows={6} fullWidth sx={{ mt: 2 }}
        label="CSV 내용" placeholder={SAMPLE_CSV}
        value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }}
        helperText="내보내기 파일을 열어 복사해 붙여 넣어도 됩니다(헤더 이름이 같습니다)."
      />
      {preview ? (
        <Box sx={{ mt: 2 }}>
          <Callout tone={preview.failed ? "warn" : "info"}>
            {preview.dry_run ? "미리 보기: " : "적용 결과: "}
            총 {preview.total}행 · {preview.dry_run ? "생성 예정" : "생성"} {preview.created}
            {" · 건너뜀 "}{preview.skipped}{" · 실패 "}{preview.failed}
          </Callout>
          <Box sx={{ mt: 1.5 }}>
            <DataTable columns={columns} rows={preview.results} rowKey={(r) => r.line} />
          </Box>
        </Box>
      ) : null}
    </Modal>
  );
}
