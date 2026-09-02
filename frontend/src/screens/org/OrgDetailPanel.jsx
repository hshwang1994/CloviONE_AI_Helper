import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import {
  Badge, Button, Card, MetricStrip, Section, TechDetail, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { KO_WORD_BREAK } from "../../ui/theme.js";
import { useInvalidateOrgCaches } from "./orgQueries.js";
import { OrgEditModal } from "./orgModals.jsx";

/* 조직 상세 판 — 트리에서 조직을 고르면 오른쪽이 이것으로 반응한다.
 *
 * 옛 화면의 오른쪽은 조직 **전체 표**(1행짜리 DataScreen)였다 — 트리를 눌러도 상세가
 * 아니라 같은 목록이 다시 섰고, 계획서가 그것을 이 화면의 결함으로 지목했다(«우측 pane 이
 * 트리 선택에 상세로 반응하지 않는다»). 지금은 고른 조직 하나의 사실과 그 조직에 할 수
 * 있는 일이 선다.
 *
 * 조직에 삭제가 없는 것은 서버 계약이다 — 사용자와 부서가 org_id 로 이 행을 가리키고
 * 있어 지우면 그 참조가 통째로 끊긴다. 대신 「비활성화」가 새 사용을 막는다. */

function MetaRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", gap: 1, py: 0.5 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" component="div" sx={KO_WORD_BREAK}>{children}</Typography>
    </Box>
  );
}

export function OrgDetailPanel({ org, treeRow }) {
  const toast = useToast();
  const confirm = useConfirm();
  const invalidate = useInvalidateOrgCaches();
  const [editing, setEditing] = React.useState(false);

  const setStatus = useMutation({
    mutationFn: (status) =>
      api("/api/admin/organizations/" + org.id, { method: "PATCH", body: { status } }),
    onSuccess: (_r, status) => {
      invalidate();
      toast(status === "active" ? "활성화했습니다." : "비활성화했습니다.");
    },
    onError: (e) => handleApiError(e, toast),
  });

  const active = org.status === "active";
  const unassigned = treeRow ? treeRow.user_count || 0 : null;

  const suspend = async () => {
    /* 이 버튼 하나가 그 조직 전원을 즉시 밖으로 내보낸다 — 서버가 살아 있는 세션을 전부
       끊고(시스템 관리자는 제외) 그 뒤로는 로그인 자체가 막힌다. 몇 명이 끊기는지를 확인
       문구가 말해야 0명과 200명이 같은 경고를 받지 않는다(admin-uiux 계약). */
    const ok = await confirm(
      "이 조직을 비활성화하면 소속 사용자 " + (org.user_count || 0)
        + "명이 지금 즉시 로그아웃되고, 다시 로그인할 수 없게 됩니다(시스템 관리자는 제외). "
        + "사용자와 부서 데이터 자체는 지워지지 않으며 ‘활성화’로 되돌릴 수 있습니다. 계속 비활성화할까요?",
      { title: org.name + " 비활성화", confirmLabel: "비활성화", danger: true },
    );
    if (ok) setStatus.mutate("suspended");
  };

  return (
    <Card sx={{ display: "grid", gap: 2, alignContent: "start" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ ...KO_WORD_BREAK, minWidth: 0 }}>
          {org.name}
        </Typography>
        <Badge value="조직" kind="info" />
        <Badge value={active ? "사용 중" : "미사용"} kind={active ? "ok" : "warn"} />
        <Box sx={{ flex: 1 }} />
        <Button size="sm" onClick={active ? suspend : () => setStatus.mutate("active")}
                variant={active ? "danger" : "default"} loading={setStatus.isPending}>
          {active ? "비활성화" : "활성화"}
        </Button>
        <Button size="sm" variant="primary" onClick={() => setEditing(true)}>수정</Button>
      </Box>

      <MetricStrip
        ariaLabel={org.name + " 요약"}
        items={[
          { key: "departments", label: "부서", value: org.department_count ?? 0 },
          { key: "users", label: "사용자", value: org.user_count ?? 0 },
          /* 계획서가 이 화면에서 가장 값진 숫자로 꼽은 값 — 어디에도 안 속한 계정 수다.
             12px 회색 부제로 눕혀 두던 것을 요약 타일로 세운다. 0 이면 조용히 0 이다. */
          {
            key: "unassigned", label: "부서 미지정", value: unassigned ?? "-",
            primary: (unassigned || 0) > 0,
          },
        ]}
      />

      <Section title="정보">
        <MetaRow label="식별자">{org.slug}</MetaRow>
        <MetaRow label="포함 관계">
          {"부서 " + (org.department_count || 0) + "개, 사용자 " + (org.user_count || 0) + "명"}
        </MetaRow>
        {unassigned ? (
          <MetaRow label="부서 미지정">
            <Link href="#/users" underline="hover">
              {"부서가 지정되지 않은 사용자 " + unassigned + "명을 사용자 화면에서 확인합니다."}
            </Link>
          </MetaRow>
        ) : null}
        <MetaRow label="삭제 안내">
          조직은 지울 수 없습니다. 사용자와 부서가 이 조직을 가리키고 있어 지우면 그 연결이
          끊깁니다. 대신 ‘비활성화’로 새 사용을 막으세요.
        </MetaRow>
      </Section>

      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
        <Button size="sm" variant="ghost"
                href={"#/audit?object_type=organization&object_id=" + org.id}>
          감사 로그에서 보기
        </Button>
        <Box sx={{ flex: 1 }} />
        <TechDetail label="조직 ID">{org.id}</TechDetail>
      </Box>

      <OrgEditModal open={editing} org={org} onClose={() => setEditing(false)} />
    </Card>
  );
}
