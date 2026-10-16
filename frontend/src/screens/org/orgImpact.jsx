import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { fmtDateTime, objectParticle } from "../../lib/format.js";
import { Button, DetailGrid, DetailRow, ErrorState, Modal, ModalFooter, Skeleton, useToast } from "../../ui/kit.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, NUMERIC } from "../../ui/theme.js";
import { useDeptImpact, useInvalidateOrgCaches, useOrgImpact } from "./orgQueries.js";

/* 영향 확인 창들 (O1 · D-533) — 지우거나 비활성화하기 **전에** 무엇이 달라지는지 서버에 묻는다.
 *
 * 예전 부서 판은 상세 응답에 실린 삭제 판정을 늘 보여 줬다(「조직은 지울 수 없습니다…」 · 「이 부서에 … 연결되어 있어」). 평소
 * 화면이 쓰지 않는 사실로 판이 길어졌고, 고를 때마다 서버가 COUNT 열두어 번을 돌았다. 이제 「삭제」 · 「비활성화」를 누를 때
 * `/impact` 가 답하고, 창이 그 답을 그린다 — 판정은 서버 한 곳이다(409 와 같은 문장).
 *
 *   DeptDeleteDialog      지울 수 있으면 확인(떼어 낼 것 한 줄씩, 취소가 기본 초점, 채움 위험 단추 「삭제」), 못 지우면 막는 항목만
 *                         한 줄씩 + 그 조건으로 걸러진 화면 링크 + 「비활성화하기」
 *   DeptDeactivateDialog  그대로 남는 것들의 수 — 새 배치와 새 하위 부서만 막힌다
 *   OrgSuspendDialog      로그아웃될 정확한 인원과 빠지는 시스템 관리자 수
 *   OrgDetailsDialog      평소 화면에서 걷은 기술 정보(ID 와 복사 · 식별자 · 하위 부서 수 · 만든 날)
 */

function countText(count, unit) {
  return `${Number(count || 0).toLocaleString("ko-KR")}${unit}`;
}

/* 막는 항목마다 그 조건으로 걸러진 화면 — 갈 곳이 없는 갈래(지식 공간 안 문서 · 관리 범위)는 링크를 달지 않는다.
   사람은 지금 목록에 보이는 사람과 보관된 계정을 따로 연다(사용자 목록의 기본 화면은 보관 계정을 숨긴다). 하위 부서는
   바로 왼쪽 트리가 그 목록이라 창을 닫고 트리에서 편다. */
function blockerLinks(item, deptId, onShowChildren) {
  const id = encodeURIComponent(deptId);
  const archived = item.archived_count || 0;
  switch (item.kind) {
    case "users": {
      const out = [];
      if ((item.count || 0) > archived) out.push({ key: "users", label: "사용자 보기", href: `#/users?department_id=${id}` });
      if (archived) out.push({ key: "archived", label: "보관된 계정 보기", href: `#/users?department_id=${id}&archived=true` });
      return out;
    }
    case "child_departments":
      return onShowChildren ? [{ key: "tree", label: "트리에서 보기", onClick: onShowChildren }] : [];
    case "projects": return [{ key: "projects", label: "프로젝트 보기", href: `#/projects?dept=${id}${archived ? "&archived=true" : ""}` }];
    case "open_sprints": return [{ key: "sprints", label: "회차 보기", href: `#/sprint?team=${id}` }];
    default: return [];
  }
}

function ImpactLines({ items, links }) {
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.5, display: "grid", gap: 0.75 }}>
      {items.map((it) => {
        const ls = links ? links(it) : [];
        return (
          <Box component="li" key={it.kind} sx={{ ...KO_WORD_BREAK }}>
            <Box component="span" sx={{ display: "inline-flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 1.5 }}>
              <span>
                {it.label} <Box component="span" sx={{ ...NUMERIC, fontWeight: FONT_WEIGHT.semibold }}>{countText(it.count, it.unit || "건")}</Box>
                {it.archived_count ? ` (보관 ${countText(it.archived_count, it.unit || "건")} 포함)` : null}
              </span>
              {ls.map((l) => (l.href ? (
                <Link key={l.key} href={l.href} underline="hover" sx={{ fontSize: FONT_SIZE.bodySm }}>{l.label}</Link>
              ) : (
                <Link key={l.key} component="button" type="button" onClick={l.onClick} underline="hover" sx={{ fontSize: FONT_SIZE.bodySm, verticalAlign: "baseline" }}>{l.label}</Link>
              )))}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

function ImpactBody({ query, children }) {
  if (query.isPending) return <Skeleton lines={3} />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  return children(query.data || {});
}

export function DeptDeleteDialog({ dept, open, onClose, onDeleted, onDeactivate, onShowChildren }) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  const impact = useDeptImpact(dept && dept.id, open);
  const remove = useMutation({
    mutationFn: () => api("/api/admin/departments/" + dept.id, { method: "DELETE" }),
    onSuccess: (res) => {
      invalidate();
      toast((res && res.message) ? `삭제했습니다. ${res.message}` : "삭제했습니다.");
      onClose();
      if (onDeleted) onDeleted(dept);
    },
    onError: (e) => handleApiError(e, toast),
  });
  const verdict = (impact.data && impact.data.delete) || null;
  const deletable = !!(verdict && verdict.deletable);
  const name = (dept && dept.name) || "";
  const title = !verdict ? "삭제 확인" : deletable ? `${name}${objectParticle(name)} 삭제하시겠습니까?` : "이 부서는 삭제할 수 없습니다.";
  /* 발은 판정마다 새로 선다(`key`) — 답을 기다리는 동안의 「닫기」가 그대로 남으면 확인 발로 바뀔 때 `autoFocus` 가 다시 돌지 않아
     초점이 새로 선 채움 위험 단추로 간다. 지울 수 있다는 답이 오면 초점은 언제나 「취소」다. */
  const footer = !verdict ? (
    <ModalFooter key="pending" onCancel={onClose} cancelLabel="닫기" />
  ) : deletable ? (
    <ModalFooter
      key="confirm"
      onCancel={onClose} onSubmit={() => remove.mutate()} submitLabel="삭제" submitVariant="dangerConfirm"
      busy={remove.isPending} cancelAutoFocus
    />
  ) : (
    <ModalFooter
      key="blocked"
      onCancel={onClose} cancelLabel="닫기"
      onSubmit={dept && dept.active && onDeactivate ? () => { onClose(); onDeactivate(); } : undefined}
      submitLabel="비활성화" submitVariant="default"
    />
  );
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm" footer={footer}>
      <ImpactBody query={impact}>
        {(data) => {
          const v = data.delete || {};
          if (v.deletable) {
            const detach = v.detachables || [];
            return (
              <Box sx={{ display: "grid", gap: 1.5 }}>
                {detach.length ? (
                  <>
                    <Typography sx={KO_WORD_BREAK}>삭제하면 아래 항목은 이 부서와의 연결만 끊기고 그대로 남습니다.</Typography>
                    <ImpactLines items={detach} />
                  </>
                ) : null}
                <Typography color="text.secondary" sx={KO_WORD_BREAK}>삭제한 부서는 되돌릴 수 없습니다.</Typography>
              </Box>
            );
          }
          return (
            <Box sx={{ display: "grid", gap: 1.5 }} data-impact-blockers="">
              <Typography sx={KO_WORD_BREAK}>아래 항목이 이 부서를 쓰고 있습니다. 먼저 옮기거나 정리하면 삭제할 수 있습니다.</Typography>
              <ImpactLines
                items={v.blockers || []}
                links={(it) => blockerLinks(it, dept.id, onShowChildren ? () => { onClose(); onShowChildren(); } : null)}
              />
              {dept && dept.active ? (
                <Typography color="text.secondary" sx={KO_WORD_BREAK}>지금 쓰지 않는 부서라면 비활성화해서 새 배치를 막을 수 있습니다.</Typography>
              ) : null}
            </Box>
          );
        }}
      </ImpactBody>
    </Modal>
  );
}

export function DeptDeactivateDialog({ dept, open, onClose }) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  const impact = useDeptImpact(dept && dept.id, open);
  const save = useMutation({
    mutationFn: () => api("/api/admin/departments/" + dept.id, { method: "PATCH", body: { active: false } }),
    onSuccess: () => { invalidate(); toast("비활성화했습니다."); onClose(); },
    onError: (e) => handleApiError(e, toast),
  });
  const name = (dept && dept.name) || "";
  return (
    <Modal
      open={open} onClose={onClose} size="sm"
      title={`${name}${objectParticle(name)} 비활성화하시겠습니까?`}
      footer={<ModalFooter onCancel={onClose} onSubmit={() => save.mutate()} submitLabel="비활성화" busy={save.isPending} disabled={impact.isPending} cancelAutoFocus />}
    >
      <ImpactBody query={impact}>
        {(data) => {
          const d = data.deactivate || {};
          const kept = [
            { kind: "members", label: "구성원", count: d.members, unit: "명" },
            { kind: "child_departments", label: "하위 부서", count: d.child_departments, unit: "개" },
            { kind: "projects", label: "프로젝트", count: d.projects, unit: "개" },
            { kind: "open_sprints", label: "진행 중이거나 예정된 회차", count: d.open_sprints, unit: "개" },
            { kind: "scoped_admins", label: "이 부서를 관리 범위로 가진 관리자", count: d.scoped_admins, unit: "명" },
          ].filter((k) => k.count);
          return (
            <Box sx={{ display: "grid", gap: 1.5 }}>
              <Typography sx={KO_WORD_BREAK}>비활성화하면 이 부서에 새로 사람을 배치하거나 하위 부서를 추가할 수 없습니다.</Typography>
              {kept.length ? (
                <>
                  <Typography sx={KO_WORD_BREAK}>지금 연결된 것은 그대로 남습니다.</Typography>
                  <ImpactLines items={kept} />
                </>
              ) : null}
              <Typography color="text.secondary" sx={KO_WORD_BREAK}>「활성화」로 언제든 되돌릴 수 있습니다.</Typography>
            </Box>
          );
        }}
      </ImpactBody>
    </Modal>
  );
}

export function OrgSuspendDialog({ org, open, onClose }) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  const impact = useOrgImpact(org && org.id, open);
  const save = useMutation({
    mutationFn: () => api("/api/admin/organizations/" + org.id, { method: "PATCH", body: { status: "suspended" } }),
    onSuccess: () => { invalidate(); toast("비활성화했습니다."); onClose(); },
    onError: (e) => handleApiError(e, toast),
  });
  const name = (org && org.name) || "";
  return (
    <Modal
      open={open} onClose={onClose} size="sm"
      title={`${name}${objectParticle(name)} 비활성화하시겠습니까?`}
      footer={<ModalFooter onCancel={onClose} onSubmit={() => save.mutate()} submitLabel="비활성화" submitVariant="dangerConfirm" busy={save.isPending} disabled={impact.isPending} cancelAutoFocus />}
    >
      <ImpactBody query={impact}>
        {(data) => {
          const s = data.suspend || {};
          return (
            <Box sx={{ display: "grid", gap: 1.5 }} data-impact-suspend="">
              <Typography sx={KO_WORD_BREAK}>
                비활성화하면 이 조직 사람 <Box component="span" sx={{ ...NUMERIC, fontWeight: FONT_WEIGHT.semibold }}>{countText(s.signed_out_users, "명")}</Box>이
                지금 바로 로그아웃되고 다시 로그인할 수 없습니다.
              </Typography>
              {s.exempt_system_admins ? (
                <Typography sx={KO_WORD_BREAK}>시스템 관리자 {countText(s.exempt_system_admins, "명")}은 로그아웃되지 않습니다.</Typography>
              ) : null}
              <Typography color="text.secondary" sx={KO_WORD_BREAK}>사용자와 부서 데이터는 지워지지 않으며 「활성화」로 되돌릴 수 있습니다.</Typography>
            </Box>
          );
        }}
      </ImpactBody>
    </Modal>
  );
}

export function OrgDetailsDialog({ open, onClose, item, kind, childCount }) {
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(item.id);
      toast("ID를 복사했습니다.");
    } catch (e) {
      toast("복사하지 못했습니다. ID를 직접 골라 복사하세요.");
    }
  };
  if (!item) return null;
  return (
    <Modal open={open} onClose={onClose} title="상세 정보" size="sm" footer={<ModalFooter onCancel={onClose} cancelLabel="닫기" />}>
      <DetailGrid>
        <DetailRow label={kind === "organization" ? "조직 ID" : "부서 ID"}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
            <Box component="code" sx={{ fontSize: FONT_SIZE.bodySm, userSelect: "all", wordBreak: "break-all" }}>{item.id}</Box>
            <Button size="sm" onClick={copy}>복사</Button>
          </Box>
        </DetailRow>
        {item.slug ? <DetailRow label="식별자">{item.slug}</DetailRow> : null}
        <DetailRow label="하위 부서">{childCount ? `${childCount}개` : "없음"}</DetailRow>
        {item.created_at ? <DetailRow label="만든 날">{fmtDateTime(item.created_at)}</DetailRow> : null}
      </DetailGrid>
    </Modal>
  );
}
