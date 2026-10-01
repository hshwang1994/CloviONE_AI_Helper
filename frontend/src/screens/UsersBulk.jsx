import React, { useState } from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { api } from "../lib/api.js";
import { expireSession } from "../lib/sessionRedirect.js";
import { Badge, Button, DataTable, Modal, Callout, useConfirm, useToast, ActionFooter, Field } from "../ui/kit.jsx";
import { Note } from "../ui/adminKit.jsx";
import { FilterRowContext, FilterSelect, PrefixLabel, kindSx } from "../ui/filters.jsx";

const ASSIGN_OPTIONS = [
  { value: "set_department", label: "부서" },
  { value: "set_title", label: "직책" },
];

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

/* 선택한 사용자에게 할 수 있는 일 — 목록 판 발의 선택 묶음이 그린다(`DataTable selection`, 조합 계약 C-3).
 *
 * 예전에는 이 줄(`BulkBar`)이 필터 바와 목록 사이에 따로 섰다 — 고른 행과 그 행에 할 일이 판 밖 두 줄로 갈라졌고, 긴
 * 목록을 내려가며 고르면 동작이 화면 위에 남았다. 이제 선택 묶음(「N명 선택」 · 일괄 동작 · 일괄 지정 · 「선택 해제」)은
 * 목록 판 안 마지막 줄이다. 일괄 동작은 30 이고, 채움(「적용」)은 이 묶음 **안에서만** 하나다.
 *
 * 돌려주는 것:
 *   selection  `DataTable selection` 에 그대로 넘기는 값
 *   notice     일괄 작업의 실패와 일부 실패 — 선택을 비운 뒤에도 남아 말한다(발은 선택이 없으면 오른쪽이 비므로
 *              이 줄은 목록 위에 따로 선다). 다음 작업을 누르면 걷힌다. */
export function useUserBulk({ selection, deptOptions, titleOptions, onDone }) {
  const [busy, setBusy] = useState(null);
  const [assign, setAssign] = useState({ action: "", value: UNASSIGNED_VALUE });
  const confirm = useConfirm();
  const toast = useToast();
  const [notice, setNotice] = useState("");
  const ids = Array.from(selection.selected);

  // danger — 호출자가 그 작업의 실제 위험도를 넘긴다(BULK_ACTIONS의 danger 속성, 또는 지정 작업은 false).
  // 예전엔 여기서 무조건 true였다: 활성화·보관 복구·잠금 해제·부서/직책 지정처럼 되돌리기 쉬운 작업까지
  // 확인 버튼이 '위험' 스타일로 떠서, 정말 위험한 작업(비활성화·보관·세션 해제)과 구분이 안 됐다.
  async function apply(action, value, confirmMsg, danger) {
    if (confirmMsg && !(await confirm(confirmMsg + `\n\n대상 ${ids.length}명.`, { danger: !!danger }))) return;
    setBusy(action);
    setNotice("");
    try {
      const res = await api("/api/admin/users/bulk/apply", {
        method: "POST", body: { user_ids: ids, action, value: value || null },
      });
      const changed = (res.applied || []).filter((r) => r.changed).length;
      const failed = (res.failed || []).length;
      // 실패를 성공 토스트로 덮지 않는다 — 몇 명이 왜 안 됐는지 숫자와 첫 사유를 함께 말한다.
      if (failed) {
        setNotice(`${changed}명 적용, ${failed}명 실패: ${res.failed[0].error}`);
      } else {
        toast(`${res.action_label}: ${changed}명 적용(${ids.length - changed}명은 이미 그 상태)`, "success");
      }
      selection.clear();
      onDone();
    } catch (e) {
      if (e && e.status === 401) { expireSession(); return; }
      setNotice(e.message);
    } finally { setBusy(null); }
  }

  const assignOptions = assign.action === "set_department" ? deptOptions : titleOptions;
  // '적용'을 누르기 전에 실제로 어떤 값이 걸리는지 확인창에 못박는다 — 일반 문구("부서를 일괄
  // 변경할까요?")만으로는 관리자가 무슨 값이 들어가는지 모른 채 확인을 누르게 된다.
  const chosenLabel = (assignOptions || []).find((o) => o.value === assign.value);
  const assignConfirmMsg = assign.action === "set_department"
    ? `선택한 계정의 부서를 "${chosenLabel ? chosenLabel.label : ""}"(으)로 일괄 변경할까요?`
    : `선택한 계정의 직책을 "${chosenLabel ? chosenLabel.label : ""}"(으)로 일괄 변경할까요?`;

  const actions = ids.length ? (
    <>
      {BULK_ACTIONS.map((a) => (
        <Button key={a.value} size="sm" variant={a.danger ? "danger" : "default"} disabled={!!busy}
          loading={busy === a.value}
          onClick={() => apply(a.value, null, a.confirm, a.danger)}>
          {a.label}
        </Button>
      ))}
      {/* 일괄 지정의 두 칸은 줄 칸이다(34 · 칸 안 이름) — 노치 라벨이 떠 있으면 옆 단추와 윗선이 어긋났다
          (핸드오프 RULES §3 · §7). */}
      <FilterRowContext.Provider value>
        <FilterSelect
          label="일괄 지정" value={assign.action} options={ASSIGN_OPTIONS} allLabel="지정 안 함"
          onChange={(v) => setAssign({ action: v, value: UNASSIGNED_VALUE })}
        />
        {/* 「값」은 `FilterSelect` 가 아니다 — 그 부품의 빈 항목(`""`)은 «전체» 인데 여기서 `""`
            는 실제 옵션(없음 = 지운다)이고, 자리표시자는 그와 다른 `UNASSIGNED_VALUE` 다.
            같은 부품으로 그리면 두 뜻이 한 값에 겹친다(위 상수 주석). */}
        {assign.action ? (
          <TextField select size="small" value={assign.value}
            inputProps={{ "aria-label": "값" }}
            SelectProps={{
              displayEmpty: true,
              renderValue: (v) => (
                <>
                  <PrefixLabel>값</PrefixLabel>
                  {v === UNASSIGNED_VALUE
                    ? "값을 선택하세요"
                    : ((assignOptions || []).find((o) => o.value === v) || { label: String(v) }).label}
                </>
              ),
            }}
            sx={kindSx("enum", { minWidth: "12rem" }, undefined, true)}
            onChange={(e) => setAssign((s) => ({ ...s, value: e.target.value }))}>
            {/* 자리표시자는 목록에 남겨 두되 다시 고를 수 없게 disabled — 관리자가 실제 옵션(없음 포함)을
                능동적으로 고르기 전까지는 이 값이 유지되어 '적용'이 비활성 상태를 유지한다. */}
            <MenuItem value={UNASSIGNED_VALUE} disabled>값을 선택하세요</MenuItem>
            {(assignOptions || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        ) : null}
      </FilterRowContext.Provider>
      {assign.action ? (
        <Button size="sm" variant="primary" disabled={!!busy || assign.value === UNASSIGNED_VALUE}
          onClick={() => apply(assign.action, assign.value, assignConfirmMsg, false)}>
          적용
        </Button>
      ) : null}
    </>
  ) : null;

  return {
    selection: { count: ids.length, unit: "명", clearLabel: "선택 해제", onClear: selection.clear, actions },
    notice: notice ? <Callout tone="danger" compact>{notice}</Callout> : null,
  };
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
  // useUserBulk의 busy===a.value 관례와 같다. 불리언 하나를 두 버튼(미리 보기/만들기)이 공유하면,
  // '만들기'를 눌러도 실행되지 않는 '미리 보기' 버튼이 "확인 중…"으로 바뀌고, 정작 요청이
  // 나가는 '만들기' 버튼에는 아무 진행 표시도 없어 사용자에게 엉뚱한 동작이 진행 중이라고
  // 말하는 셈이었다.
  const [busyAction, setBusyAction] = useState(null);
  const toast = useToast();
  const confirm = useConfirm();
  /* 요청 자체가 실패한 사실 — 모달 안에 남는다. 다시 누르면 걷힌다. */
  const [sendFailure, setSendFailure] = useState("");

  async function send(dryRun) {
    setBusyAction(dryRun ? "preview" : "create");
    setSendFailure("");
    try {
      const res = await api("/api/admin/users/import/csv", {
        method: "POST", body: { csv_text: text, dry_run: dryRun },
      });
      setPreview(res);
      if (!dryRun) {
        // 실패한 행이 있으면 아래 결과 상자(오류 톤)가 이미 그 사실을 말한다 — 토스트로 겹쳐 말하지 않는다.
        if (!res.failed) toast(`${res.created}명을 추가했습니다(건너뜀 ${res.skipped}, 실패 ${res.failed}).`, "success");
        onImported();
      }
    } catch (e) { setSendFailure(e.message); }
    finally { setBusyAction(null); }
  }

  const columns = [
    { key: "line", label: "줄", type: "count" },
    { key: "email", label: "이메일", type: "identifier" },
    { key: "display_name", label: "이름", type: "name" },
    { key: "status", label: "결과", type: "status", render: (r) => {
      const s = IMPORT_STATUS[r.status] || { label: r.status, kind: "neutral" };
      return <Badge value={s.label} kind={s.kind} />;
    } },
    { key: "message", label: "설명", type: "text" },
    /* 적용한 뒤에만 선다 — 만든 계정마다 초대 메일이 큐에 들어갔는지(계획 3.3). 못 들어갔으면 그 까닭이 칸의 힌트다. */
    preview && preview.dry_run === false ? {
      key: "invite", label: "초대 메일", type: "status",
      render: (r) => (r.invite_mail
        ? <Badge value={r.invite_mail.queued ? "보냄" : "못 보냄"} kind={r.invite_mail.queued ? "ok" : "warn"} />
        : "-"),
      hint: (r) => (r.invite_mail && !r.invite_mail.queued ? r.invite_mail.reason || "" : ""),
    } : null,
  ].filter(Boolean);
  const invites = preview && preview.dry_run === false ? preview.invites : null;
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
    <ActionFooter placement="modal">
        <Button onClick={requestClose}>{applied ? "닫기" : "취소"}</Button>
        {!applied ? (
          <>
            <Button disabled={!!busyAction || !text.trim()} loading={busyAction === "preview"} onClick={() => send(true)}>
              미리 보기
            </Button>
            <Button variant="primary" disabled={!!busyAction || !preview || !preview.created}
              loading={busyAction === "create"}
              onClick={() => send(false)}>
              {preview ? `${preview.created}명 추가` : "미리 보기를 먼저 하세요"}
            </Button>
          </>
        ) : null}
    </ActionFooter>
  );

  return (
    <Modal open onClose={onClose} title="CSV로 사용자 가져오기" size="lg" dirty={dirty} footer={footer}>
      {/* 형식 설명은 경고가 아니다 - 상자와 `안내` 라벨을 걷어내고 부연 문단으로 둔다(지시 35 · 44).
          `Note` 는 문단(p)이라 예전처럼 안에 문단을 다시 넣을 수 없다 - 문단마다 하나씩 둔다. */}
      <Note sx={{ mt: 0 }}>
        <strong>이메일</strong>과 <strong>이름</strong> 열이 필요합니다. 역할, 부서, 직책은 선택입니다(부서, 직책은 <em>이름</em>으로 씁니다).
      </Note>
      <Note sx={{ mt: 0.75 }}>
        가져오기는 <strong>새 계정만 추가합니다</strong>: 이미 있는 이메일은 건너뜁니다(기존 계정을 조용히 덮어쓰지 않습니다).
      </Note>
      <Note sx={{ mt: 0.75 }}>
        추가된 계정에는 비밀번호를 직접 정하는 초대 메일이 나갑니다. 첫 로그인 때 비밀번호를 바꾸게 합니다.
      </Note>
      <Box sx={{ minWidth: 0, mt: 2 }}>
        <Field
          label="CSV 내용" htmlFor="users-csv-text" helpId="users-csv-text-help"
          help="내보내기 파일을 열어 복사해 붙여 넣어도 됩니다(헤더 이름이 같습니다)."
        >
          <TextField id="users-csv-text"
            multiline minRows={6} fullWidth
            placeholder={SAMPLE_CSV}
            inputProps={{ "aria-describedby": "users-csv-text-help" }}
            value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }}
          />
        </Field>
      </Box>
      {sendFailure ? <Callout tone="danger" compact>{sendFailure}</Callout> : null}
      {preview ? (
        <Box sx={{ mt: 2 }}>
          {/* 실패한 행이 있다는 것은 "그 계정이 만들어지지 않았다"는 뜻이다 — 주의가 아니라
              오류다(D-155). 미리 보기에서의 실패도 마찬가지로 적용하면 그대로 실패한다.
              건너뜀(이미 있는 이메일)은 설계된 정상 동작이라 등급을 올리지 않는다. */}
          {/* 적용했는데 실패한 행이 있으면 그 사실이 이 상자의 제목이다 — 예전에는 같은 문장이 토스트로 따로 떴다. */}
          <Callout
            tone={preview.failed ? "danger" : "info"}
            title={!preview.dry_run && preview.failed ? `${preview.created}명을 추가했습니다(건너뜀 ${preview.skipped}, 실패 ${preview.failed}).` : undefined}
          >
            {preview.dry_run ? "미리 보기: " : "적용 결과: "}
            총 {preview.total}행, {preview.dry_run ? "추가 예정" : "추가"} {preview.created}
            {", 건너뜀 "}{preview.skipped}{", 실패 "}{preview.failed}
          </Callout>
          {/* 초대 메일이 못 나간 계정이 있으면 그 사실과 까닭을 말한다 — 조용히 넘기면 관리자는 초대가 나갔다고 믿는다. */}
          {invites && invites.not_queued ? (
            <Callout tone="warn" compact>
              {`초대 메일 ${invites.not_queued}건을 보내지 못했습니다. ${invites.reason || ""} 메일 발송 화면에서 설정을 확인하세요.`}
            </Callout>
          ) : invites && invites.queued ? (
            <Callout tone="success" compact>{`초대 메일 ${invites.queued}건을 보냈습니다.`}</Callout>
          ) : null}
          <Box sx={{ mt: 1.5 }}>
            <DataTable columns={columns} rows={preview.results} rowKey={(r) => r.line} />
          </Box>
        </Box>
      ) : null}
    </Modal>
  );
}
