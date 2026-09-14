import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import {
  Badge, Button, Card, ErrorState, MetricStrip, Section, Skeleton, TechDetail, FlatBadgeSurface,
  useConfirm, useToast,
} from "../../ui/kit.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { KO_WORD_BREAK, PROSE_MAX_WIDTH } from "../../ui/theme.js";
import { useDepartmentItem, useDepartmentPeople, useInvalidateOrgCaches } from "./orgQueries.js";
import { DeptEditModal } from "./orgModals.jsx";

/* 부서 상세 판 — 트리에서 부서를 고르면 오른쪽이 이것으로 반응한다.
 *
 * 옛 화면의 「소속 인원」은 **셋째 판**이었고 1920 미만에서는 통째로 사라졌다 — 1366 노트북
 * 관리자는 그 판이 있는 줄도 몰랐다. 인원은 부서의 사실이므로 부서 상세 안의 절로 들어와
 * **모든 폭에서** 보인다.
 *
 * 목록을 다시 만들지 않는다. 여기서 보여 주는 것은 여덟까지고, 그보다 많으면 그 조건이
 * 걸린 사용자 화면으로 보낸다 — 같은 목록을 두 화면이 각자 그리면 언젠가 다른 답을 한다. */

const PEOPLE_PREVIEW = 8;

/* 조직 판(`OrgDetailPanel`)과 **같은 규칙**이다 — 두 판이 나란히 쓰이는 화면에서 한쪽만
   다른 밀도를 가지면 그 차이가 정보의 차이로 읽힌다. 값 칸에 상한을 두고, 넓은 판에서는
   사실 목록을 두 줄기로 나눈다. */
function MetaRow({ label, children, span = false }) {
  return (
    <Box
      sx={{
        display: "grid", gridTemplateColumns: "7rem minmax(0, 1fr)", gap: 1, py: 0.5,
        ...(span ? { gridColumn: { lg: "1 / -1" } } : null),
      }}
    >
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" component="div" sx={{ ...KO_WORD_BREAK, maxWidth: PROSE_MAX_WIDTH }}>
        {children}
      </Typography>
    </Box>
  );
}

const META_GRID = {
  display: "grid",
  columnGap: 3,
  gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" },
};

function PeopleSection({ departmentId }) {
  const q = useDepartmentPeople(departmentId);
  const items = (q.data && q.data.items) || [];
  const total = q.data && q.data.total != null ? q.data.total : items.length;

  return (
    <Section title={"소속 인원" + (q.isPending ? "" : " " + total + "명")}>
      {q.isPending ? <Skeleton lines={3} /> : null}
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} layout="region" size="compact" /> : null}
      {!q.isPending && !q.isError && items.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          이 부서에 배치된 사람이 없습니다. 사용자 화면에서 부서를 지정하면 여기에 나타납니다.
        </Typography>
      ) : null}
      {items.length ? (
        <FlatBadgeSurface>
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}>
          {items.slice(0, PEOPLE_PREVIEW).map((u) => (
            <Box component="li" key={u.id}
                 sx={{ display: "flex", gap: 1, alignItems: "center", minWidth: 0 }}>
              <UserAvatar person={u} size="sm" />
              <Link href={"#/users/" + u.id} underline="hover"
                    sx={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {u.display_name || u.email}
              </Link>
              <Badge value={u.title || u.role} />
            </Box>
          ))}
        </Box>
        </FlatBadgeSurface>
      ) : null}
      {total > PEOPLE_PREVIEW ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
          {PEOPLE_PREVIEW}명만 표시했습니다.{" "}
          <Link href={"#/users?department_id=" + encodeURIComponent(departmentId)} underline="hover">
            사용자 화면에서 {total}명 모두 보기
          </Link>
        </Typography>
      ) : null}
    </Section>
  );
}

export function DeptDetailPanel({ deptId, treeRow }) {
  const toast = useToast();
  const confirm = useConfirm();
  const invalidate = useInvalidateOrgCaches();
  const item = useDepartmentItem(deptId);
  const [editing, setEditing] = React.useState(false);

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
    onSuccess: () => { invalidate(); toast("삭제했습니다."); },
    /* 서버가 409 로 「무엇이 몇 건」과 대안을 말한다(app/org/service.py::dependents) —
       그 문장을 그대로 보여 준다. */
    onError: (e) => handleApiError(e, toast),
  });

  if (item.isPending) return <Card><Skeleton lines={6} /></Card>;
  if (item.isError) {
    /* 없는 id 딥링크(D-127) — 판 안에서 말하고 트리는 그대로 산다. */
    return <Card><ErrorState error={item.error} onRetry={() => item.refetch()} /></Card>;
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

  return (
    <Card sx={{ display: "grid", gap: 2, alignContent: "start" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ ...KO_WORD_BREAK, minWidth: 0 }}>
          {dept.name}
        </Typography>
        <Badge value={dept.active ? "사용 중" : "미사용"} kind={dept.active ? "ok" : "warn"} />
        {row.cycle ? <Badge value="상위 관계 오류" kind="danger" /> : null}
        <Box sx={{ flex: 1 }} />
        {/* 이 부서로 가는 두 링크는 **동작 줄**에 있다 — 예전에는 카드 맨 아래에서
            「부서 ID」와 좌우로 갈라져 있었다(조직 판과 같은 자리, 같은 이유). */}
        <Button size="sm" variant="ghost"
                href={"#/audit?object_type=department&object_id=" + deptId}>
          감사 로그에서 보기
        </Button>
        <Button size="sm" variant="ghost"
                href={"#/users?department_id=" + encodeURIComponent(deptId)}>
          사용자 화면에서 보기
        </Button>
        {dept.active
          ? <Button size="sm" variant="danger" onClick={deactivate} loading={setActive.isPending}>비활성화</Button>
          : <Button size="sm" onClick={() => setActive.mutate(true)} loading={setActive.isPending}>활성화</Button>}
        {/* 서버가 막는 부서는 삭제가 항상 409 다 — 눌러도 실패하는 단추를 애초에 안
            그린다(대신 삭제 안내가 서버의 이유를 그대로 말한다). */}
        {deletable ? (
          <Button size="sm" variant="danger" onClick={removeConfirm} loading={removeDept.isPending}>
            삭제
          </Button>
        ) : null}
        <Button size="sm" variant="primary" onClick={() => setEditing(true)}>수정</Button>
      </Box>

      <MetricStrip
        ariaLabel={dept.name + " 요약"}
        items={[
          { key: "members", label: "소속 인원", value: userCount, note: "보관 계정 포함" },
          { key: "children", label: "하위 부서", value: childCount },
          {
            key: "subtree", label: "하위 포함 인원",
            value: row.subtree_user_count != null ? row.subtree_user_count : userCount,
          },
        ]}
      />

      <Section title="정보" sx={{ mb: 0 }}>
        <Box sx={META_GRID}>
          <MetaRow label="조직">{dept.org_name || "-"}</MetaRow>
          <MetaRow label="전체 경로">{row.path || dept.name}</MetaRow>
          <MetaRow label="상위 부서">{row.parent_name || "(최상위)"}</MetaRow>
          <MetaRow label="부서 ID">
            <TechDetail label="식별자 보기">{deptId}</TechDetail>
          </MetaRow>
          {row.cycle ? (
            <MetaRow label="상위 관계 오류" span>
              이 부서는 상위 관계가 고리를 이루고 있어 최상위로 끌어올려 표시했습니다.
              ‘수정’에서 상위 부서를 다시 지정하세요.
            </MetaRow>
          ) : null}
          {/* 판정을 못 받았으면(아직 그 필드를 안 싣는 서버) 아무 말도 하지 않는다 —
              모르는 상태에서 「지금 삭제할 수 있습니다」라고 적는 것이 이 결함이었다. */}
          {precheck ? (
            <MetaRow label="삭제 안내" span>
              {deletable
                ? (detachSummary
                  ? "이 부서는 지금 삭제할 수 있습니다. 삭제하면 " + detachSummary
                    + "은 부서 연결만 끊고 그대로 남습니다."
                  : "이 부서는 지금 삭제할 수 있습니다.")
                : precheck.reason}
            </MetaRow>
          ) : null}
        </Box>
      </Section>

      <PeopleSection departmentId={deptId} />

      <DeptEditModal open={editing} dept={dept} onClose={() => setEditing(false)} />
    </Card>
  );
}
