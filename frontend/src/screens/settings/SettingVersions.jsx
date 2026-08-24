import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { fmtDateTime } from "../../lib/format.js";
import { Card, Button, DataTable, Modal, EmptyState, ErrorState, useConfirm, useToast } from "../../ui/kit.jsx";
import { summarizeSetting, securityDowngradeWarning, displayValue } from "./settingsRegistry.js";
import { DateCell } from "../../ui/cells.jsx";

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
    { key: "created_at", label: "변경 시각", nowrap: true, render: (r) => <DateCell value={r.created_at} /> },
  ];
  if (canWrite) columns.push({
    key: "__roll", label: "", type: "actions",
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
    <Modal open onClose={onClose} title={label + ", 버전 기록"} size="lg" footer={footer}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        각 버전은 그 시점의 값입니다. 롤백하면 현재 값이 그 버전으로 돌아가고, 그 사실이 새 기록으로 남습니다.
      </Typography>
      {/* 목록 자체는 페이지네이션 없이 전체를 보여준다(app/core/versioning.py list_versions에 상한 없음) —
          자주 손보는 설정은 기록이 눈에 안 띄게 계속 늘어날 수 있어, 최소한 개수라도 먼저 보여준다
          (DataScreen의 capWarning과 같은 취지 — '이 목록이 얼마나 긴지' 모르는 채로 스크롤하지 않게). */}
      {!vq.isLoading && !vq.isError && items.length > 0 ? <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>{items.length}건</Typography> : null}
      {vq.isLoading ? <DataTable columns={columns} rows={[]} loading />
        : vq.isError ? <ErrorState error={vq.error} onRetry={() => vq.refetch()} />
        : items.length === 0 ? <EmptyState title="버전 기록이 없습니다" help="이 설정을 아직 변경한 적이 없습니다." />
        : <Card><DataTable columns={columns} rows={items} rowKey={(r) => r.version} /></Card>}
    </Modal>
  );
}
