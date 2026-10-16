import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import {
  Badge, Button, Callout, DataTable, EmptyState, ErrorState, FormModal, RowActions, useConfirm, useToast,
} from "../ui/kit.jsx";
import { HeaderActions } from "../ui/HeaderSlot.jsx";
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
  not_mounted: "마운트되지 않음",
  wrong_fstype: "다른 파일 시스템",
  unreadable: "읽지 못함",
};

/* 이 탭의 `?` 도움말 — 그릇(`settings/SettingsShell.jsx`)이 제목 옆에 그린다(D-453).
   예전에는 본문 첫 줄에 `Note` 문단으로 그렸다. */
export const HELP = "업로드한 파일과 백업이 실제로 어디에 쌓이는지, 그 자리가 지금 쓸 수 있는 상태인지 보여 줍니다. 마운트는 서버가 하고 이 화면은 설정과 지금 상태만 다룹니다.";

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
    help: "NFS와 SMB는 반드시 적습니다. 로컬 디스크는 비워 둡니다." },
  { name: "source", label: "원본", type: "text",
    help: "NFS는 nas.example:/export, SMB는 //nas.example/share 형식입니다." },
  { name: "options", label: "마운트 옵션", type: "text" },
  // 비밀번호를 여기 적지 않는다는 사실은 입력 옆에 있어야 한다 — 폼을 채우는 사람이
  // 그 순간 실제로 값을 붙여 넣으려 하기 때문이다(불변규칙 §6-3).
  { name: "credentials_ref", label: "인증 정보 이름", type: "text",
    help: "서버 secrets 디렉터리의 파일 이름입니다. 비밀번호 자체를 적지 않습니다." },
  { name: "enabled", label: "사용", type: "checkbox", value: false,
    checkLabel: "사용(먼저 추가하고 ‘상태 확인’으로 마운트되었는지 본 뒤 활성화할 수 있습니다)" },
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
  return MOUNT_KO[state.status] || state.status || "알 수 없음";
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
  /* 이 편집 창이 409 를 한 번 받았는가.
   *
   * 🔴 예전에는 409 뒤에 목록만 다시 받고 창은 그대로 뒀다. 그런데 `editing` 은 「수정」을
   * 누른 순간의 스냅샷이라 `version` 이 낡은 채로 얼어 있었고, 사람이 적은 값을 지키려고
   * 「저장」을 다시 누르면 **같은 낡은 판을 다시 보내** 영원히 409 였다. 서버 문구는
   * 「새로 고친 뒤 다시 시도해 주세요」인데 화면에는 새로 고치는 길이 창을 닫는 것뿐이었다.
   * 이제 그 새로 고침을 화면이 대신 한다: 409 를 받으면 목록을 다시 받고, 다음 저장은
   * **방금 받은 판**을 싣는다. 사람이 적은 값은 그대로 남는다(FormModal 은 `open` 이
   * 바뀔 때만 초기값을 다시 읽는다).
   *
   * 처음 저장에는 여전히 편집을 시작한 시점의 판을 보낸다 — 매번 최신 판을 실어 보내면
   * 낙관적 잠금이 아무것도 막지 못한다(D-240 이 없애려던 그 상태로 돌아간다). */
  const [conflicted, setConflicted] = React.useState(false);
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
      /* 쓸 수 있는지는 표 아래 확인 결과 상자(`probed`)가 말한다 — 같은 사실을 토스트로 겹쳐 말하지 않는다. */
      setProbed(res);
      refresh();
    },
  });

  /* 수정은 **편집을 시작한 시점의 판**을 함께 보낸다 (D-240 · settings-07).
   *
   * 서버에는 낙관적 잠금이 처음부터 있었다(`ProviderUpdate.base_version` → 낡으면 409
   * 「다른 사람이 먼저 저장했습니다」). 그런데 화면이 그 값을 안 보내서 잠금이 한 번도
   * 걸리지 않았다 — 두 관리자가 같은 저장소를 손보면 나중 저장이 앞 저장을 말없이 덮었고,
   * 토스트는 양쪽 다 「저장했습니다」였다. 실측으로 다른 탭의 마운트 옵션이 그렇게 사라졌다.
   *
   * 값은 목록 응답의 `version` 이다(`app/storage/service.py::provider_status`). 서버가 그
   * 값을 안 싣는 판에서는 안 보낸다 — 스키마가 `int | None` 이라 예전과 똑같이 동작한다
   * (없는 값을 0 이나 1 로 지어내면 멀쩡한 저장이 409 로 막힌다). */
  const save = useMutation({
    mutationFn: ({ id, body, baseVersion }) => (
      id
        ? api("/api/storage/providers/" + id, {
            method: "PATCH",
            body: typeof baseVersion === "number" ? { ...body, base_version: baseVersion } : body,
          })
        : api("/api/storage/providers", { method: "POST", body })
    ),
    onSuccess: (_res, vars) => {
      setCreating(false); setEditing(null); setConflicted(false);
      toast(vars.id ? "저장했습니다." : "저장소를 추가했습니다.", "success");
      refresh();
    },
    /* 409 면 내가 들고 있던 판이 이미 낡았다 — 목록을 새로 받는다. 폼은 열어 둔 채 서버가
       준 이유를 그대로 보여 준다(`FormModal` 이 오류 문구를 폼 위에 그린다) — 사람이 방금
       적은 값을 잃지 않는다. 그리고 **다음 저장이 실제로 통하도록** 이 창을 「충돌을 한 번
       본 창」으로 표시한다(아래 `baseVersion` 계산) — 표시하지 않으면 사람은 같은 낡은 판을
       계속 다시 보내고, 창을 닫는 것 말고는 빠져나갈 길이 없다. */
    onError: (e) => { if (e && e.status === 409) { setConflicted(true); refresh(); } },
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }) => api("/api/storage/providers/" + id, { method: "PATCH", body: { enabled } }),
    onSuccess: (_res, vars) => {
      toast(vars.enabled ? "저장소를 활성화했습니다." : "저장소를 비활성화했습니다.", "success");
      refresh();
    },
  });
  /* 확인 · 사용 전환의 실패는 표 바로 아래에 남는다 — 가장 나중에 누른 동작 하나만 말한다. */
  const rowFailure = failureText([probe, "저장소 상태를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."], [toggle, "저장소 설정을 바꾸지 못했습니다. 잠시 후 다시 시도해 주세요."]);

  const data = query.data || {};
  const rows = data.providers || [];
  const busy = probe.isPending || save.isPending || toggle.isPending;

  /* 다음 저장이 실을 판. 평소에는 편집을 시작한 시점의 값이고(그래야 잠금이 실제로 잠근다),
     409 를 한 번 받은 뒤에는 방금 다시 받은 목록의 값이다 — 그 한 번의 거절이 「지금 판을
     보고 다시 결정하라」는 뜻이고, 사람은 이미 그 문구를 읽었다. 그 행이 목록에서 사라졌으면
     원래 값을 그대로 쓴다(없는 값을 지어내지 않는다). */
  const editingRow = editing ? rows.find((r) => r.id === editing.id) : null;
  const nextBaseVersion = (conflicted && editingRow && typeof editingRow.version === "number")
    ? editingRow.version
    : (editing ? editing.version : undefined);

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
      help: "이 경로가 있는 파일 시스템의 사용량과 전체 용량입니다.",
      render: capacityText },
    /* 행 동작은 `RowActions` 다 — 셋이라 30 「더 보기」 하나로 접힌다(핸드오프 RULES §5 · 조합 계약 C-4). 예전에는 34
       아이콘 단추가 행 높이를 밀었다. */
    { key: "_actions", label: "", type: "actions", render: (r) => (
      <RowActions
        ariaLabel={r.name + " 작업"}
        actions={[
          { key: "probe", label: "상태 확인", disabled: busy, onClick: () => probe.mutate(r.id) },
          { key: "edit", label: "수정", disabled: busy, onClick: () => { setConflicted(false); setEditing(r); } },
          {
            key: "toggle",
            label: r.enabled ? "비활성화" : "활성화",
            // 운영 저장소를 끄면 업로드가 그 순간부터 실패한다 — 확인 문구가 그 파급을
            // 말해야 한다(연동 비활성화와 같은 관용).
            variant: r.enabled ? "danger" : undefined,
            disabled: busy,
            onClick: async () => {
              const ok = await confirm(
                r.enabled
                  ? (r.role === "OPERATIONAL"
                      ? "이 저장소를 비활성화하면 새 파일 업로드가 실패합니다. 계속할까요?"
                      : "이 저장소를 비활성화할까요? 이 저장소로 보내던 백업 사본이 멈춥니다.")
                  : "이 저장소를 활성화할까요?",
                { danger: r.enabled, title: r.enabled ? "비활성화" : "활성화", confirmLabel: r.enabled ? "비활성화" : "활성화" }
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

  /* `/storage` 라우트는 **없다** — 이 화면은 설정 껍데기의 탭으로만 열린다.
     머리와 `.c-screen` 은 그 껍데기가 그린다. */
  return (
    <>

      {query.isLoading ? (
        <DataTable placement="surface" columns={columns} rows={[]} loading />
      ) : query.isError ? (
        <ErrorState layout="region" error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          {/* 「운영과 백업이 같은 장치」는 이 화면에서 가장 값진 한 문장이다 — 장치가
              고장 나면 백업도 함께 잃는다는 뜻이고, 목록만 보고는 알 수 없다. */}
          {data.warning ? <Callout tone="warn">{data.warning}</Callout> : null}

          {rows.length === 0 ? (
            /* 탭 전체가 빈 상태다 — 화면 가운데 구성(C1 · `EmptyState layout`). 예전에는 왼쪽 위에
               붙는 `region` 이라 큰 흰 면 구석에 두 줄만 놓였다. */
            <EmptyState
              layout="page"
              art="settings"
              title="등록된 파일 저장소가 없습니다."
              help="파일 저장소를 추가하면 업로드한 파일과 백업이 쌓이는 자리를 여기서 관리할 수 있습니다."
              situation="설치기가 기본 저장소를 만들어 둡니다. 하나도 없다면 설치가 끝나지 않았거나 저장소 설정이 삭제된 것입니다."
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

              {/* 「저장소 추가」는 그릇 머리의 오른쪽에 선다 — 다른 목록 화면의 「추가」와 같은
                  자리다(D-454). 그릇이 없으면 예전 자리(오른쪽 정렬 줄)에 남는다. */}
              {embedded ? (
                <HeaderActions fallback={<Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2 }}>{addButton}</Box>}>
                  {addButton}
                </HeaderActions>
              ) : null}

              {/* 목록 판 — 판이 곧 표 상자다(조합 계약 C-3). */}
              <Box sx={{ mt: 2 }}>
                <DataTable placement="surface" columns={columns} rows={rows} rowKey={(r) => r.id} />
              </Box>
              {rowFailure ? <Callout tone="danger" compact>{rowFailure}</Callout> : null}

              {probed ? (
                /* 확인 결과의 한마디(쓸 수 있다 · 없다)가 이 상자의 제목이다 — 예전에는 같은 말이 토스트로 따로 떴다. */
                <Callout tone={probed.writable ? "success" : "warn"} title={probed.writable ? "지금 쓸 수 있습니다." : "지금은 쓸 수 없습니다."}>
                  {"‘" + probed.name + "’: " + mountText(probed) + "."}
                  {probed.mount && probed.mount.detail ? " " + probed.mount.detail : ""}
                  {/* 안 붙어 있을 때 다음에 칠 명령을 준다. 유닛 이름은 이 응답에만 있다. */}
                  {!probed.writable && probed.mount_unit
                    ? " 서버에서 systemctl start " + probed.mount_unit + " 로 마운트할 수 있습니다."
                    : ""}
                </Callout>
              ) : null}
              {/* 「마운트는 서버가 한다」는 문장은 탭 `?` 도움말(HELP)이 이미 말한다 — 표 아래에 한 번 더
                  적지 않는다(같은 사실을 두 번 말하는 자리를 걷었다). */}
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
          onSubmit={(values) => save.mutateAsync({
            id: editing.id, body: values, baseVersion: nextBaseVersion,
          })}
          onClose={() => { setConflicted(false); setEditing(null); }}
        />
      ) : null}
    </>
  );
}

export default StorageProviders;
