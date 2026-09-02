import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import {
  Badge, Button, Card, ErrorState, MetricStrip, Section, Skeleton, TechDetail,
  useConfirm, useToast,
} from "../../ui/kit.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { KO_WORD_BREAK } from "../../ui/theme.js";
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

function MetaRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", gap: 1, py: 0.5 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" component="div" sx={KO_WORD_BREAK}>{children}</Typography>
    </Box>
  );
}

function PeopleSection({ departmentId }) {
  const q = useDepartmentPeople(departmentId);
  const items = (q.data && q.data.items) || [];
  const total = q.data && q.data.total != null ? q.data.total : items.length;

  return (
    <Section title={"소속 인원" + (q.isPending ? "" : " " + total + "명")}>
      {q.isPending ? <Skeleton lines={3} /> : null}
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} size="sm" /> : null}
      {!q.isPending && !q.isError && items.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          이 부서에 배치된 사람이 없습니다. 사용자 화면에서 부서를 지정하면 여기에 나타납니다.
        </Typography>
      ) : null}
      {items.length ? (
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
      childCount
        ? "이 부서를 지우면 하위 부서 " + childCount + "개가 최상위 부서로 올라갑니다"
          + "(하위 부서와 그 소속 인원은 지워지지 않습니다). 되돌릴 수 없습니다. 계속할까요?"
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
        {dept.active
          ? <Button size="sm" variant="danger" onClick={deactivate} loading={setActive.isPending}>비활성화</Button>
          : <Button size="sm" onClick={() => setActive.mutate(true)} loading={setActive.isPending}>활성화</Button>}
        {/* 사용 중(소속 인원>0)인 부서는 삭제가 항상 409 다 — 눌러도 실패하는 단추를
            애초에 안 그린다(대신 삭제 안내가 이유를 말한다). */}
        {!userCount ? (
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

      <Section title="정보">
        <MetaRow label="조직">{dept.org_name || "-"}</MetaRow>
        <MetaRow label="전체 경로">{row.path || dept.name}</MetaRow>
        <MetaRow label="상위 부서">{row.parent_name || "(최상위)"}</MetaRow>
        {row.cycle ? (
          <MetaRow label="상위 관계 오류">
            이 부서는 상위 관계가 고리를 이루고 있어 최상위로 끌어올려 표시했습니다.
            ‘수정’에서 상위 부서를 다시 지정하세요.
          </MetaRow>
        ) : null}
        <MetaRow label="삭제 안내">
          {userCount
            ? "사용 중인 부서(소속 인원 " + userCount + "명, 보관 계정 포함)는 삭제할 수 없습니다. 대신 ‘비활성화’를 이용하세요."
            : childCount
              ? "삭제하면 하위 부서 " + childCount + "개가 최상위 부서로 올라갑니다(하위 부서 자체는 지워지지 않습니다)."
              : "이 부서는 지금 삭제할 수 있습니다."}
        </MetaRow>
      </Section>

      <PeopleSection departmentId={deptId} />

      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
        <Button size="sm" variant="ghost"
                href={"#/audit?object_type=department&object_id=" + deptId}>
          감사 로그에서 보기
        </Button>
        <Button size="sm" variant="ghost"
                href={"#/users?department_id=" + encodeURIComponent(deptId)}>
          사용자 화면에서 보기
        </Button>
        <Box sx={{ flex: 1 }} />
        <TechDetail label="부서 ID">{deptId}</TechDetail>
      </Box>

      <DeptEditModal open={editing} dept={dept} onClose={() => setEditing(false)} />
    </Card>
  );
}
