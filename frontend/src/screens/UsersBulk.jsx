import React, { useState } from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { redirectToLogin } from "../lib/sessionRedirect.js";
import { Badge, Button, Card, DataTable, Modal, Callout, useConfirm, useToast } from "../ui/kit.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";

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
  ready: { label: "추가 예정", kind: "ok" },
  created: { label: "추가됨", kind: "ok" },
  skipped: { label: "건너뜀", kind: "neutral" },
  failed: { label: "실패", kind: "danger" },
};

const SAMPLE_CSV = "이메일,이름,역할,부서,직책\nhong@example.com,홍길동,user,개발팀,팀원\n";

// '값' 드롭다운의 자리표시자 — deptOptions/titleOptions의 첫 항목은 항상 { value: "", label: "없음" }
// (Users.jsx의 useNameOptions)이라 assign.value를 ""로 초기화하면 드롭다운이 '아무것도 안 고름'이 아니라
// 이미 '없음'(= 지운다)을 고른 상태로 열린다. 관리자가 값을 건드리지 않고 '적용'을 누르면 선택한 전원의
// 부서/직책이 조용히 null로 지워진다. ""는 실제 옵션(없음)이라 자리표시자로 못 쓰고, 어떤 실제 옵션과도
// 겹치지 않는 이 상수를 써서 '아직 아무것도 고르지 않음'과 '없음을 일부러 고름'을 구분한다.
const UNASSIGNED_VALUE = "__unset__";

/* 선택 바 — 몇 명을 골랐는지와 그들에게 할 수 있는 일. 선택이 없으면 아무것도 그리지 않는다. */
export function BulkBar({ selection, deptOptions, titleOptions, onDone }) {
  const [busy, setBusy] = useState(null);
  const [assign, setAssign] = useState({ action: "", value: UNASSIGNED_VALUE });
  const confirm = useConfirm();
  const toast = useToast();
  const ids = Array.from(selection.selected);
  if (!ids.length) return null;

  // danger — 호출자가 그 작업의 실제 위험도를 넘긴다(BULK_ACTIONS의 danger 속성, 또는 지정 작업은 false).
  // 예전엔 여기서 무조건 true였다: 활성화·보관 복구·잠금 해제·부서/직책 지정처럼 되돌리기 쉬운 작업까지
  // 확인 버튼이 '위험' 스타일로 떠서, 정말 위험한 작업(비활성화·보관·세션 해제)과 구분이 안 됐다.
  async function apply(action, value, confirmMsg, danger) {
    if (confirmMsg && !(await confirm(confirmMsg + `\n\n대상 ${ids.length}명.`, { danger: !!danger }))) return;
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
        toast(`${res.action_label}: ${changed}명 적용(${ids.length - changed}명은 이미 그 상태)`, "success");
      }
      selection.clear();
      onDone();
    } catch (e) {
      if (e && e.status === 401) { toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error"); redirectToLogin({ delayMs: 1200 }); return; }
      toast(e.message, "error");
    } finally { setBusy(null); }
  }

  const assignOptions = assign.action === "set_department" ? deptOptions : titleOptions;
  // '적용'을 누르기 전에 실제로 어떤 값이 걸리는지 확인창에 못박는다 — 일반 문구("부서를 일괄
  // 변경할까요?")만으로는 관리자가 무슨 값이 들어가는지 모른 채 확인을 누르게 된다.
  const chosenLabel = (assignOptions || []).find((o) => o.value === assign.value);
  const assignConfirmMsg = assign.action === "set_department"
    ? `선택한 계정의 부서를 "${chosenLabel ? chosenLabel.label : ""}"(으)로 일괄 변경할까요?`
    : `선택한 계정의 직책을 "${chosenLabel ? chosenLabel.label : ""}"(으)로 일괄 변경할까요?`;
  return (
    <Card sx={{ p: 2, mb: 2.5 }}>
      {/* SEM-02(PA-F-031): 필터·목록 사이의 이 카드는 그 둘과 달리 선택이 있을 때만 나타나는
          독립된 블록이라(위 두 곳처럼 항상 있는 구역이 아니다) MyTickets/TeamDocs의 헤더
          내장형 BulkActions(role=toolbar)와는 다르게 실제 카드 하나를 통째로 차지한다 -
          h2로 구획한다. 시각은 그대로(.sr-only). */}
      <Typography component="h2" className="sr-only">일괄 작업</Typography>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>{ids.length}명 선택</Typography>
        {BULK_ACTIONS.map((a) => (
          <Button key={a.value} size="sm" variant={a.danger ? "danger" : "default"} disabled={!!busy}
            onClick={() => apply(a.value, null, a.confirm, a.danger)}>
            {busy === a.value ? "처리 중…" : a.label}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={selection.clear}>선택 해제</Button>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1.5 }}>
        <TextField select size="small" label="일괄 지정" value={assign.action}
          SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
          sx={{ minWidth: "10rem" }}
          onChange={(e) => setAssign({ action: e.target.value, value: UNASSIGNED_VALUE })}>
          <MenuItem value="">지정 안 함</MenuItem>
          <MenuItem value="set_department">부서</MenuItem>
          <MenuItem value="set_title">직책</MenuItem>
        </TextField>
        {assign.action ? (
          <TextField select size="small" label="값" value={assign.value}
            SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
            sx={{ minWidth: "12rem" }}
            onChange={(e) => setAssign((s) => ({ ...s, value: e.target.value }))}>
            {/* 자리표시자는 목록에 남겨 두되 다시 고를 수 없게 disabled — 관리자가 실제 옵션(없음 포함)을
                능동적으로 고르기 전까지는 이 값이 유지되어 '적용'이 비활성 상태를 유지한다. */}
            <MenuItem value={UNASSIGNED_VALUE} disabled>값을 선택하세요</MenuItem>
            {(assignOptions || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        ) : null}
        {assign.action ? (
          <Button size="sm" variant="primary" disabled={!!busy || assign.value === UNASSIGNED_VALUE}
            onClick={() => apply(assign.action, assign.value, assignConfirmMsg, false)}>
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

export function ImportModal({ onClose, onImported }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState(null);
  // 불리언 하나가 아니라 '어느 작업이 진행 중인가'를 담는다("preview" | "create" | null) — 위
  // BulkBar의 busy===a.value 관례와 같다. 불리언 하나를 두 버튼(미리 보기/만들기)이 공유하면,
  // '만들기'를 눌러도 실행되지 않는 '미리 보기' 버튼이 "확인 중…"으로 바뀌고, 정작 요청이
  // 나가는 '만들기' 버튼에는 아무 진행 표시도 없어 사용자에게 엉뚱한 동작이 진행 중이라고
  // 말하는 셈이었다.
  const [busyAction, setBusyAction] = useState(null);
  const toast = useToast();
  const confirm = useConfirm();

  async function send(dryRun) {
    setBusyAction(dryRun ? "preview" : "create");
    try {
      const res = await api("/api/admin/users/import/csv", {
        method: "POST", body: { csv_text: text, dry_run: dryRun },
      });
      setPreview(res);
      if (!dryRun) {
        toast(`${res.created}명을 추가했습니다(건너뜀 ${res.skipped}, 실패 ${res.failed}).`,
          res.failed ? "error" : "success");
        onImported();
      }
    } catch (e) { toast(e.message, "error"); }
    finally { setBusyAction(null); }
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
  // 붙여넣은 CSV가 있으면(아직 반영 전) Esc·바깥 클릭·X·'취소' 전부에서 확인을 받는다
  // (VIS-88) — 이미 만들어졌으면(applied) 더 잃을 게 없어 그냥 닫는다.
  const dirty = !applied && text.trim().length > 0;
  async function requestClose() {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  }

  const footer = (
    <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
      <Box className="k-footer-main">
        <Button onClick={requestClose}>{applied ? "닫기" : "취소"}</Button>
        {!applied ? (
          <>
            <Button disabled={!!busyAction || !text.trim()} onClick={() => send(true)}>
              {busyAction === "preview" ? "확인 중…" : "미리 보기"}
            </Button>
            <Button variant="primary" disabled={!!busyAction || !preview || !preview.created}
              onClick={() => send(false)}>
              {busyAction === "create" ? "추가하는 중…" : preview ? `${preview.created}명 추가` : "미리 보기를 먼저 하세요"}
            </Button>
          </>
        ) : null}
      </Box>
    </Box>
  );

  return (
    <Modal open onClose={onClose} title="CSV로 사용자 가져오기" size="lg" dirty={dirty} footer={footer}>
      <Callout>
        <Box component="p" sx={{ m: 0 }}>
          <strong>이메일</strong>과 <strong>이름</strong> 열이 필요합니다. 역할, 부서, 직책은 선택입니다(부서, 직책은 <em>이름</em>으로 씁니다).
        </Box>
        <Box component="p" sx={{ m: 0, mt: 0.75 }}>
          가져오기는 <strong>새 계정만 추가합니다</strong>: 이미 있는 이메일은 건너뜁니다(기존 계정을 조용히 덮어쓰지 않습니다).
        </Box>
        <Box component="p" sx={{ m: 0, mt: 0.75 }}>
          추가된 계정은 임시 비밀번호가 발급되고 첫 로그인 시 변경을 요구합니다.
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
            총 {preview.total}행, {preview.dry_run ? "추가 예정" : "추가"} {preview.created}
            {", 건너뜀 "}{preview.skipped}{", 실패 "}{preview.failed}
          </Callout>
          <Box sx={{ mt: 1.5 }}>
            <DataTable columns={columns} rows={preview.results} rowKey={(r) => r.line} />
          </Box>
        </Box>
      ) : null}
    </Modal>
  );
}
