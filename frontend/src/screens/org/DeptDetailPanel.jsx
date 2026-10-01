import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import {
  Badge, Button, Card, DetailGrid, DetailRow, ErrorState, OverflowMenu, Section, Skeleton, TechDetail,
  useConfirm, useToast,
} from "../../ui/kit.jsx";
import { HeaderActions } from "../../ui/HeaderSlot.jsx";
import { OrgPath, PATH_SEP } from "../../ui/OrgPath.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { useDepartmentItem, useInvalidateOrgCaches } from "./orgQueries.js";
import { DeptCreateModal, DeptEditModal } from "./orgModals.jsx";
import { OrgMembersList } from "./OrgMembersList.jsx";
import { INFO_GRID_SX, INFO_WIDE_ROW, OrgPanelHead } from "./OrgPanelHead.jsx";

/* 부서 상세 판 — 트리에서 부서를 고르면 오른쪽이 이것으로 반응한다. **고른 부서 하나를 관리하는 자리**다.
 *
 * ## 무엇을 걷었나
 *
 * 옛 판은 같은 사실을 여러 번 말했다: 요약 타일 셋(소속 인원 · 하위 부서 · 하위 포함 인원 — 트리 줄의
 * 부제와 같은 수), 「조직」 · 「전체 경로」 · 「상위 부서」 세 줄(한 경로를 세 번), 그리고 판 폭만큼
 * 늘어난 인원 목록. 지금은:
 *
 *   머리   이름 · 상태 + 둘째 줄의 전체 경로(`OrgPath`) + 「수정」
 *   구성원 이 부서의 사람(검색 · 상태 · 하위 부서 포함, 페이지로 받는다 - `OrgMembersList`)
 *   정보   하위 부서 수 · 부서 ID · 상위 관계 오류 · 미사용 안내 · 삭제 판정(한 문장 + 「자세히」)
 *
 * ## 동작은 대상 옆에
 *
 * 「하위 부서 추가」가 이 판의 주 동작이다(화면의 채움은 이것 하나 — 조직 판에서는 「부서 추가」).
 * 창은 이 부서를 상위로, 이 부서의 조직을 고정한 채 열린다. 미사용 부서에서는 숨긴다 — 서버가 미사용
 * 부서를 새 상위로 받지 않는다(xb-08). 주 동작과 「더 보기」(감사 로그 · 사용자 화면 · 활성/비활성 · 삭제)는
 * 페이지 머리에 선다(`HeaderActions`, 계획 3.6) — 판 안의 30px 주 동작이 머리의 34px 보조 단추보다 작아 위계가
 * 거꾸로 읽혔다. 판 머리에는 「수정」 하나만 남는다. 파괴적 항목은 메뉴가 실선으로 갈라 둔다. */

/* 막는 갈래 중 **갈 곳이 있는** 것 — 삭제 판정 문장 옆에 그 자리로 가는 링크를 단다. 나머지 갈래
 * (하위 부서 · 프로젝트 · 지식 공간 · 관리 범위)는 이 콘솔 안에 거르는 자리가 없거나(하위 부서는 바로 왼쪽
 * 트리가 그 목록이다) 다른 콘솔의 화면이라 링크를 만들지 않는다. */
function blockerLinks(precheck, deptId) {
  const blockers = (precheck && !precheck.deletable && precheck.blockers) || [];
  const users = blockers.find((b) => b.kind === "users");
  if (!users) return [];
  const base = "#/users?department_id=" + encodeURIComponent(deptId);
  const links = [{ key: "users", label: "소속 사용자 보기", href: base }];
  if (users.archived_count) links.push({ key: "archived", label: "보관된 계정 보기", href: base + "&archived=true" });
  return links;
}

/* 이 부서까지의 경로(조상만) — 트리 행의 부모 사슬을 따라 올라간다. 고리가 있으면(상위 관계 오류) 한 바퀴
 * 돌기 전에 멈춘다. 트리가 아직 없으면 빈 경로라 조직 이름만 선다. */
export function ancestorsOf(rows, id) {
  const byId = new Map((rows || []).map((r) => [r.id, r]));
  const out = [];
  const seen = new Set([id]);
  let cur = byId.get(id);
  while (cur && cur.parent_id && !seen.has(cur.parent_id)) {
    seen.add(cur.parent_id);
    const parent = byId.get(cur.parent_id);
    if (!parent) break;
    out.unshift({ id: parent.id, name: parent.name });
    cur = parent;
  }
  return out;
}

export function DeptDetailPanel({ deptId, treeRow, treeRows = [], headingRef, onCreated, onDeleted }) {
  const toast = useToast();
  const confirm = useConfirm();
  const invalidate = useInvalidateOrgCaches();
  const item = useDepartmentItem(deptId);
  const [editing, setEditing] = React.useState(false);
  const [adding, setAdding] = React.useState(false);

  const setActive = useMutation({
    mutationFn: (nextActive) =>
      api("/api/admin/departments/" + deptId, { method: "PATCH", body: { active: nextActive } }),
    onSuccess: (_r, nextActive) => {
      invalidate();
      toast(nextActive ? "활성화했습니다." : "비활성화했습니다.");
    },
    onError: (e) => handleApiError(e, toast),
  });

  const removeDept = useMutation({
    mutationFn: () => api("/api/admin/departments/" + deptId, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast("삭제했습니다.");
      /* 지운 부서의 판에 남으면 곧바로 「찾을 수 없습니다」가 선다 — 그 부서가 있던 자리(상위 부서, 없으면
         조직)로 옮겨 간다. */
      if (onDeleted) onDeleted(item.data || {});
    },
    /* 서버가 409 로 「무엇이 몇 건」과 대안을 말한다(app/org/service.py::dependents) —
       그 문장을 그대로 보여 준다. */
    onError: (e) => handleApiError(e, toast),
  });

  if (item.isPending) return <Card><Skeleton lines={6} /></Card>;
  if (item.isError) {
    /* 없는 id 딥링크(D-127) — 판 안에서 말하고 트리는 그대로 산다. */
    return <Card><ErrorState layout="region" error={item.error} onRetry={() => item.refetch()} /></Card>;
  }
  const dept = item.data || {};
  const row = treeRow || {};
  const userCount = dept.user_count || 0;
  const childCount = dept.child_department_count || 0;

  /* 🔴 **삭제 판정은 서버가 한 번 내리고 이 판은 그것을 그린다**(org-02 · xc-01).
   *
   * 예전에는 이 판이 스스로 셌다 — 소속 인원과 하위 부서 둘만 보고 「이 부서는 지금 삭제할
   * 수 있습니다」라고 단정했다. 서버의 `dependents` 는 여덟 갈래를 세므로 프로젝트·지식
   * 공간·그 안의 문서·관리 범위가 매달린 부서에서는 눌러 보면 409 였다. 하위 부서에
   * 대해서는 한술 더 떠 「최상위 부서로 올라갑니다」라고 서버와 **정반대**를 약속했다 —
   * 그 승격은 FK 가 `SET NULL` 이던 시절의 사실이고, 지금 서버는 하위 부서를 차단 사유로
   * 센다. 「되돌릴 수 없습니다」가 붙은 확인 창이 실제와 다른 말을 하는 것이 가장 위험한
   * 거짓말이라 그 문구는 지웠다.
   *
   * 그래서 이제 갈래·건수·라벨·이유 문장은 전부 상세 응답의 `delete_precheck` 에서 온다
   * (app/org/service.py::delete_precheck). 같은 규칙을 두 곳에 두면 반드시 어긋난다.
   * 막힌 이유 문장은 409 의 문장과 **같은 함수**가 만든 것이라, 눌러 보기 전과 눌러 본
   * 뒤가 같은 말을 한다(보관되어 목록에 안 보이는 건수도 그 문장이 말한다 — xc-04). */
  const precheck = dept.delete_precheck || null;
  const deletable = Boolean(precheck && precheck.deletable);
  /* 막지 않고 **연결만 끊는** 갈래(팀 채팅방·옛 문서 기록). 지워지지는 않지만 부서 표시를
     잃으므로, 누르기 전에 그 사실을 말한다. 라벨은 서버가 준 것을 그대로 쓴다. */
  const detachSummary = ((precheck && precheck.detachables) || [])
    .map((d) => d.label + " " + d.count + "건")
    .join(", ");
  const links = blockerLinks(precheck, deptId);

  const deactivate = async () => {
    const ok = await confirm(
      userCount
        ? "비활성화하면 이 항목을 쓰는 사용자 " + userCount
          + "명이 사용자 폼에서 더 이상 새로 고를 수 없게 됩니다. 계속할까요?"
        : "비활성화하면 사용자 폼에서 새로 고를 수 없게 됩니다. 계속할까요?",
      { title: dept.name + " 비활성화", confirmLabel: "비활성화", danger: true },
    );
    if (ok) setActive.mutate(false);
  };

  const removeConfirm = async () => {
    const ok = await confirm(
      detachSummary
        ? "이 부서를 지우면 " + detachSummary + "은 부서 연결만 끊고 그대로 남습니다."
          + " 되돌릴 수 없습니다. 계속할까요?"
        : "이 부서를 지울까요? 되돌릴 수 없습니다.",
      { title: dept.name + " 삭제", confirmLabel: "삭제", danger: true },
    );
    if (ok) removeDept.mutate();
  };

  const usersHref = "#/users?department_id=" + encodeURIComponent(deptId);
  /* 「더 보기」 — 옮겨 가는 링크 둘, 그 뒤로 상태를 바꾸는 일. 서버가 막는 부서는 삭제가 항상 409 라
     눌러도 실패하는 항목을 애초에 안 세운다(대신 정보의 「삭제」 줄이 서버의 이유를 그대로 말한다). */
  const menu = [
    { key: "audit", label: "감사 로그에서 보기", href: "#/audit?object_type=department&object_id=" + deptId },
    { key: "users", label: "사용자 화면에서 보기", href: usersHref },
    dept.active
      ? { key: "deactivate", label: "비활성화", tone: "danger", disabled: setActive.isPending, onClick: deactivate }
      : { key: "activate", label: "활성화", disabled: setActive.isPending, onClick: () => setActive.mutate(true) },
    deletable
      ? { key: "delete", label: "삭제", tone: "danger", disabled: removeDept.isPending, onClick: removeConfirm }
      : null,
  ];

  const ancestors = ancestorsOf(treeRows, deptId);
  const pathLine = [dept.org_name, ...ancestors.map((n) => n.name)].filter(Boolean).join(PATH_SEP);

  /* 판에는 한 문장이 선다(서버의 `summary`). 긴 이유(보관 계정 안내 · 대안)는 「자세히」가 편다 — 막힌 갈래가
     여럿이면 이유 문장이 네 줄을 넘어 정보 절이 그것으로 찼다. */
  const deleteSentence = deletable
    ? (detachSummary
      ? "이 부서는 지금 삭제할 수 있습니다. 삭제하면 " + detachSummary + "은 부서 연결만 끊고 그대로 남습니다."
      : "이 부서는 지금 삭제할 수 있습니다.")
    : ((precheck && (precheck.summary || precheck.reason)) || "");
  const deleteDetail = !deletable && precheck && precheck.summary && precheck.reason !== precheck.summary
    ? precheck.reason : null;

  return (
    <Card sx={{ display: "grid", gap: 3, alignContent: "start" }}>
      <OrgPanelHead
        title={dept.name}
        headingRef={headingRef}
        badges={(
          <>
            <Badge value={dept.active ? "사용 중" : "미사용"} kind={dept.active ? "ok" : "warn"} />
            {row.cycle ? <Badge value="상위 관계 오류" kind="danger" /> : null}
          </>
        )}
        /* 조직 · 전체 경로 · 상위 부서 세 줄이 말하던 것을 한 줄로 — 이 부서가 **어디에** 있는가. 경로는 한 줄로
           읽혀야 뜻이 있어 좁으면 말줄임이 되고, 전체는 `title` 이 든다. */
        identity={(
          <Box title={pathLine || undefined} sx={{ minWidth: 0 }}>
            <OrgPath
              variant="full"
              org={dept.org_name ? { name: dept.org_name } : null}
              path={ancestors}
              sx={{ fontSize: FONT_SIZE.bodySm }}
            />
          </Box>
        )}
        actionsLabel={dept.name + " 작업"}
        actions={<Button size="sm" onClick={() => setEditing(true)}>수정</Button>}
      />
      {/* 동작 순서는 제품의 머리 규칙과 같다 — 더 보기 → 채움(하위 부서 추가)이 오른쪽 끝이다(D-501). */}
      <HeaderActions
        fallback={(
          <>
            <OverflowMenu ariaLabel={dept.name + " 작업 더 보기"} items={menu} />
            {dept.active ? <Button variant="primary" onClick={() => setAdding(true)}>하위 부서 추가</Button> : null}
          </>
        )}
      >
        <OverflowMenu ariaLabel={dept.name + " 작업 더 보기"} items={menu} />
        {dept.active ? <Button variant="primary" onClick={() => setAdding(true)}>하위 부서 추가</Button> : null}
      </HeaderActions>

      <OrgMembersList
        key={deptId}
        scope={{ kind: "dept", deptId }}
        emptyText="이 부서에 배치된 사람이 없습니다. 사용자 화면에서 부서를 지정하면 여기에 나타납니다."
      />

      <Section flush title="정보">
        <DetailGrid sx={INFO_GRID_SX}>
          <DetailRow label="하위 부서">{childCount ? childCount + "개" : "없음"}</DetailRow>
          <DetailRow label="부서 ID">
            <TechDetail label="식별자 보기">{deptId}</TechDetail>
          </DetailRow>
          {row.cycle ? (
            <DetailRow label="상위 관계 오류" sx={INFO_WIDE_ROW}>
              이 부서는 상위 관계가 고리를 이루고 있어 최상위로 끌어올려 표시했습니다.
              ‘수정’에서 상위 부서를 다시 지정하세요.
            </DetailRow>
          ) : null}
          {/* 「하위 부서 추가」가 사라진 자리 대신 이 줄이 이유와 푸는 길을 말한다. */}
          {!dept.active ? (
            <DetailRow label="하위 부서 추가" sx={INFO_WIDE_ROW}>
              미사용 부서에는 하위 부서를 만들 수 없습니다. 먼저 활성화하세요.
            </DetailRow>
          ) : null}
          {/* 판정을 못 받았으면(아직 그 필드를 안 싣는 서버) 아무 말도 하지 않는다 —
              모르는 상태에서 「지금 삭제할 수 있습니다」라고 적는 것이 이 결함이었다. */}
          {precheck ? (
            <DetailRow label="삭제" sx={INFO_WIDE_ROW}>
              <Typography variant="body2" component="p" sx={{ m: 0, ...KO_WORD_BREAK }}>{deleteSentence}</Typography>
              {deleteDetail ? <TechDetail label="자세히" sx={{ mt: 0.5 }}>{deleteDetail}</TechDetail> : null}
              {links.length ? (
                <Box sx={{ display: "flex", flexWrap: "wrap", columnGap: 2, rowGap: 0.5, mt: 0.75 }}>
                  {links.map((l) => (
                    <Link key={l.key} href={l.href} underline="hover" variant="body2">{l.label}</Link>
                  ))}
                </Box>
              ) : null}
            </DetailRow>
          ) : null}
        </DetailGrid>
      </Section>

      <DeptEditModal open={editing} dept={dept} onClose={() => setEditing(false)} />
      <DeptCreateModal
        open={adding}
        onClose={() => setAdding(false)}
        fixedOrgId={dept.org_id || ""}
        defaultParentId={dept.id || deptId}
        defaultParentLabel={dept.name}
        title={dept.name + "에 하위 부서 추가"}
        onCreated={onCreated}
      />
    </Card>
  );
}
