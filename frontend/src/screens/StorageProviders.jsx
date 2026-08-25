import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, DataTable, EmptyState, ErrorState, FormModal,
  OverflowMenu, PageHeader, Skeleton, useConfirm, useToast,
} from "../ui/kit.jsx";
import { Note } from "../ui/adminKit.jsx";
import { fmtBytes } from "./registry/shared.js";

/* 파일 저장소 (S8 · S20).
 *
 * ## 왜 이 화면이 이제야 생겼나
 *
 * S8 이 저장소 계약(`/api/storage/*`)과 마운트 판정과 용량 조회를 전부 만들었는데
 * **부르는 화면이 없었다.** 그래서 관리자는 업로드가 어디로 가는지, 그 자리가 지금 실제로
 * 붙어 있는지, 운영과 백업이 같은 장치에 있는지를 서버에 들어가야만 알 수 있었다 —
 * 그리고 «같은 장치» 는 장치가 죽는 순간 백업도 함께 죽는다는 뜻이라, 사람이 봐야 하는
 * 사실이다. 목표 IA(`MASTER_PLAN.md` §14.1)도 이 항목을 「시스템」 묶음에 적어 두었다.
 *
 * ## 이 화면이 답하는 질문 하나
 *
 * **«지금 파일을 쓸 수 있는가.»** 그래서 첫 줄이 운영 저장소의 쓰기 가부이고, 표의 상태
 * 열은 «설정돼 있는가» 가 아니라 «지금 붙어 있는가» 다(서버가 요청마다 실제로 `stat` 한다 —
 * app/storage/router.py 의 「마운트 상태는 요청할 때마다 실제로 본다」).
 *
 * ## 마운트가 안 붙어 있으면 다음에 칠 명령을 준다
 *
 * 「지금 확인」(`POST /providers/{id}/probe`)은 상태 조회와 달리 **마운트 유닛 이름**까지
 * 함께 준다. 안 붙어 있을 때 관리자가 다음에 할 일이 `systemctl start <그 유닛>` 이기
 * 때문이다 — 그 이름을 안 주면 이 화면은 문제만 말하고 끝난다.
 *
 * ## 여기서 마운트하지 않는다
 *
 * 웹 프로세스는 `/etc` 도 `mount` 도 못 만진다(SystemOps 와 같은 하드닝). 이 화면은 설정
 * 행을 고치고 지금 상태를 읽을 뿐이고, 실제 마운트는 서버의 유닛이 한다. 없는 능력을
 * 버튼으로 그리지 않는다.
 */

const ROLE_KO = { OPERATIONAL: "운영", BACKUP: "백업" };
const KIND_KO = { LOCAL: "로컬 디스크", NFS: "NFS", SMB: "SMB" };

/* 마운트 판정 여섯 가지(app/storage/mount.py)를 그대로 옮긴다. 원문 슬러그가 화면에
   새면 관리자는 `not_mounted` 와 `wrong_fstype` 의 차이를 추측해야 한다.
   배지에 들어가는 값이라 **낱말**이다 — 문장은 아래 「지금 확인」 결과가 말한다. */
const MOUNT_KO = {
  ok: "쓸 수 있음",
  missing: "경로 없음",
  not_dir: "디렉터리 아님",
  not_mounted: "안 붙어 있음",
  wrong_fstype: "다른 종류",
  unreadable: "읽지 못함",
};

const HELP = "업로드한 파일과 백업이 실제로 어디에 쌓이는지, 그 자리가 지금 쓸 수 있는 상태인지 보여 줍니다. 마운트는 서버가 하고 이 화면은 설정과 지금 상태만 다룹니다.";

// 절대 경로만 받는다(app/storage/schemas.py 와 DB CHECK 가 같은 규칙을 건다) — 화면에서
// 먼저 말해 주지 않으면 사람은 422 를 보고서야 안다.
const PATH_HELP = "절대 경로로 적습니다. 예: /srv/clovirassist/files";

const CREATE_FIELDS = [
  { name: "name", label: "이름", type: "text", required: true },
  { name: "role", label: "역할", type: "select", value: "OPERATIONAL", required: true,
    options: [{ value: "OPERATIONAL", label: "운영" }, { value: "BACKUP", label: "백업" }],
    help: "운영은 사용자가 올린 파일이, 백업은 데이터베이스 백업 세트가 쌓이는 자리입니다." },
  { name: "kind", label: "종류", type: "select", value: "LOCAL", required: true,
    options: [{ value: "LOCAL", label: "로컬 디스크" }, { value: "NFS", label: "NFS" }, { value: "SMB", label: "SMB" }] },
  { name: "base_path", label: "경로", type: "text", required: true, help: PATH_HELP },
  { name: "mount_point", label: "마운트 지점", type: "text",
    help: "NFS, SMB 는 반드시 적습니다. 로컬 디스크는 비웁니다." },
  { name: "source", label: "원본", type: "text",
    help: "NFS 는 nas.example:/export, SMB 는 //nas.example/share 형식입니다." },
  { name: "options", label: "마운트 옵션", type: "text" },
  // 비밀번호를 여기 적지 않는다는 사실은 입력 옆에 있어야 한다 — 폼을 채우는 사람이
  // 그 순간 실제로 값을 붙여 넣으려 하기 때문이다(불변규칙 §6-3).
  { name: "credentials_ref", label: "인증 정보 이름", type: "text",
    help: "서버 secrets 디렉터리의 파일 이름입니다. 비밀번호 자체를 적지 않습니다." },
  { name: "enabled", label: "사용", type: "checkbox", value: false,
    checkLabel: "사용(먼저 추가하고 ‘지금 확인’으로 붙어 있는지 본 뒤 켤 수 있습니다)" },
];

// 수정은 역할과 종류를 안 바꾼다 — 백엔드 `ProviderUpdate` 도 그 둘을 안 받는다. 이미
// 쌓인 파일이 그 성질 위에 있어서, 바꾸면 같은 행이 다른 자리를 가리키게 된다.
const EDIT_FIELDS = [
  { name: "name", label: "이름", type: "text" },
  { name: "base_path", label: "경로", type: "text", help: PATH_HELP },
  { name: "mount_point", label: "마운트 지점", type: "text" },
  { name: "source", label: "원본", type: "text" },
  { name: "options", label: "마운트 옵션", type: "text" },
  { name: "credentials_ref", label: "인증 정보 이름", type: "text",
    help: "서버 secrets 디렉터리의 파일 이름입니다. 비밀번호 자체를 적지 않습니다." },
];

function mountText(row) {
  const state = row.mount || {};
  return MOUNT_KO[state.status] || state.status || "알 수 없습니다";
}

/** 용량 한 칸. 셋 다 못 읽는 환경(statvfs 없는 개발 머신)에서는 «모른다» 고 말한다. */
function capacityText(row) {
  if (row.total_bytes == null) return "-";
  return fmtBytes(row.used_bytes) + " / " + fmtBytes(row.total_bytes);
}

export function StorageProviders({ embedded = false }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  // 「지금 확인」의 결과는 목록 값과 다른 것을 하나 더 준다(마운트 유닛 이름). 그 한 번의
  // 답을 화면에 남겨 두지 않으면 관리자는 토스트가 사라지는 순간 유닛 이름을 잃는다.
  const [probed, setProbed] = React.useState(null);

  const query = useQuery({
    queryKey: ["storage", "status"],
    queryFn: () => api("/api/storage/status"),
    retry: false,
  });

  const refresh = React.useCallback(() => {
    qc.invalidateQueries({ queryKey: ["storage"] });
  }, [qc]);

  /* ⚠️ `useToast()` 는 `{success, error}` 를 가진 객체가 아니라 `(message, kind)` 두 인자를
     받는 **함수 하나**다(`ui/kit.jsx` 의 `ToastCtx.Provider value={push}`). `toast.error(…)`
     로 부르면 없는 메서드를 부르는 셈이라 TypeError 로 죽고, 그 죽음은 rejected promise 안에
     있어 화면에는 «아무 일도 안 일어남» 으로 보인다 — `SystemOps.jsx` 가 실제로 그 자리에
     있었다(그 화면의 모든 쓰기가 결과를 한 번도 못 알렸다). 같은 호출 모양을 쓴다. */
  const probe = useMutation({
    mutationFn: (id) => api("/api/storage/providers/" + id + "/probe", { method: "POST", body: {} }),
    onSuccess: (res) => {
      setProbed(res);
      const ok = !!(res && res.writable);
      toast(ok ? "지금 쓸 수 있습니다." : "지금은 쓸 수 없습니다.", ok ? "success" : "error");
      refresh();
    },
    onError: (e) => toast((e && e.message) || "확인하지 못했습니다.", "error"),
  });

  const save = useMutation({
    mutationFn: ({ id, body }) => (
      id
        ? api("/api/storage/providers/" + id, { method: "PATCH", body })
        : api("/api/storage/providers", { method: "POST", body })
    ),
    onSuccess: (_res, vars) => {
      setCreating(false); setEditing(null);
      toast(vars.id ? "저장했습니다." : "저장소를 추가했습니다.", "success");
      refresh();
    },
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }) => api("/api/storage/providers/" + id, { method: "PATCH", body: { enabled } }),
    onSuccess: (_res, vars) => {
      toast(vars.enabled ? "사용으로 바꿨습니다." : "사용 안 함으로 바꿨습니다.", "success");
      refresh();
    },
    onError: (e) => toast((e && e.message) || "바꾸지 못했습니다.", "error"),
  });

  const data = query.data || {};
  const rows = data.providers || [];
  const busy = probe.isPending || save.isPending || toggle.isPending;

  /* 열은 폭이 아니라 **의미**를 말한다(D-288 · `ui/columnTypes.js`). 남는 폭을 갖는 열은
     하나뿐이어야 하고(D-308) 여기서는 경로다 — 값이 가장 길고 잘리면 가장 아쉽다. */
  const columns = [
    { key: "name", label: "이름", type: "name", rowName: (r) => r.name },
    { key: "role", label: "역할", type: "enum", render: (r) => ROLE_KO[r.role] || r.role },
    { key: "kind", label: "종류", type: "enum", render: (r) => KIND_KO[r.kind] || r.kind },
    { key: "writable", label: "지금 상태", type: "status",
      help: "요청할 때마다 서버가 그 경로를 실제로 확인한 결과입니다.",
      render: (r) => <Badge value={mountText(r)} kind={r.writable ? "ok" : "danger"} /> },
    { key: "enabled", label: "사용", type: "status", render: (r) => <Badge value={r.enabled ? "사용" : "사용 안 함"} kind={r.enabled ? "ok" : "neutral"} /> },
    { key: "base_path", label: "경로", type: "text" },
    { key: "capacity", label: "사용량", type: "number",
      help: "이 경로가 올라앉은 파일시스템의 사용량과 전체 용량입니다.",
      render: capacityText },
    { key: "_actions", label: "", type: "actions", render: (r) => (
      <OverflowMenu
        ariaLabel={r.name + " 작업"}
        items={[
          { key: "probe", label: "지금 확인", disabled: busy, onClick: () => probe.mutate(r.id) },
          { key: "edit", label: "수정", disabled: busy, onClick: () => setEditing(r) },
          {
            key: "toggle",
            label: r.enabled ? "사용 안 함으로" : "사용으로",
            // 운영 저장소를 끄면 업로드가 그 순간부터 실패한다 — 확인 문구가 그 파급을
            // 말해야 한다(연동 비활성화와 같은 관용).
            tone: r.enabled ? "danger" : undefined,
            disabled: busy,
            onClick: async () => {
              const ok = await confirm(
                r.enabled
                  ? (r.role === "OPERATIONAL"
                      ? "이 저장소를 사용 안 함으로 바꾸면 새 파일 업로드가 실패합니다. 계속할까요?"
                      : "이 저장소를 사용 안 함으로 바꿀까요? 이 자리로 보내던 백업 사본이 멈춥니다.")
                  : "이 저장소를 사용으로 바꿀까요?",
                { danger: r.enabled, title: r.enabled ? "사용 안 함" : "사용", confirmLabel: r.enabled ? "사용 안 함" : "사용" }
              );
              if (ok) toggle.mutate({ id: r.id, enabled: !r.enabled });
            },
          },
        ]}
      />
    ) },
  ];

  const addButton = (
    <Button variant="primary" disabled={busy} onClick={() => setCreating(true)}>저장소 추가</Button>
  );

  return (
    <Box className="c-screen">
      {embedded ? null : <PageHeader area="설정" title="파일 저장소" help={HELP} actions={addButton} />}

      {query.isLoading ? (
        <Skeleton kind="table" rows={3} cols={6} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          {embedded ? <Note sx={{ mt: 0 }}>{HELP}</Note> : null}

          {/* 「운영과 백업이 같은 장치」는 이 화면에서 가장 값진 한 문장이다 — 장치가
              고장 나면 백업도 함께 잃는다는 뜻이고, 목록만 보고는 알 수 없다. */}
          {data.warning ? <Callout tone="warn">{data.warning}</Callout> : null}

          {rows.length === 0 ? (
            <EmptyState
              art="settings"
              title="등록된 파일 저장소가 없습니다"
              help="파일 저장소를 추가하면 업로드한 파일과 백업이 쌓이는 자리를 여기서 관리할 수 있습니다."
              situation="설치기가 기본 저장소를 만들어 둡니다. 하나도 없다면 설치가 끝나지 않았거나 행이 지워진 것입니다."
              action={embedded ? addButton : null}
            />
          ) : (
            <>
              {/* 판단 순서를 위에서 아래로 만든다: 지금 쓸 수 있는가 → 무엇이 쌓여 있는가. */}
              <Callout tone={data.operational_ok ? "success" : "danger"}>
                {data.operational_ok
                  ? "운영 저장소에 지금 파일을 쓸 수 있습니다."
                  : "운영 저장소에 지금 파일을 쓸 수 없습니다. 새 업로드가 실패합니다."}
                {data.file_count != null ? ` 저장된 파일은 ${data.file_count}건입니다.` : ""}
              </Callout>

              {embedded ? (
                <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2 }}>{addButton}</Box>
              ) : null}

              <Box sx={{ mt: 2 }}>
                <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} />
              </Box>

              {probed ? (
                <Callout tone={probed.writable ? "success" : "warn"}>
                  {"‘" + probed.name + "’: " + mountText(probed) + "."}
                  {probed.mount && probed.mount.detail ? " " + probed.mount.detail : ""}
                  {/* 안 붙어 있을 때 다음에 칠 명령을 준다. 유닛 이름은 이 응답에만 있다. */}
                  {!probed.writable && probed.mount_unit
                    ? " 서버에서 systemctl start " + probed.mount_unit + " 로 붙일 수 있습니다."
                    : ""}
                </Callout>
              ) : null}

              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
                마운트는 서버의 유닛이 합니다. 이 화면에서는 설정을 고치고 지금 상태를 확인할 수 있습니다.
              </Typography>
            </>
          )}
        </>
      )}

      {creating ? (
        <FormModal
          open
          title="저장소 추가"
          fields={CREATE_FIELDS}
          submitLabel="추가"
          onSubmit={(values) => save.mutateAsync({ id: null, body: values })}
          onClose={() => setCreating(false)}
        />
      ) : null}

      {editing ? (
        <FormModal
          open
          title={"‘" + editing.name + "’ 수정"}
          fields={EDIT_FIELDS}
          initial={editing}
          onSubmit={(values) => save.mutateAsync({ id: editing.id, body: values })}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </Box>
  );
}

export default StorageProviders;
