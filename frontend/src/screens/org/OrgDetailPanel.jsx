import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import {
  Badge, Button, Card, DetailGrid, DetailRow, OverflowMenu, Section, TechDetail, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { useInvalidateOrgCaches, useUnassignedPeople } from "./orgQueries.js";
import { DeptCreateModal, OrgEditModal } from "./orgModals.jsx";
import { OrgPeopleSection } from "./OrgPeopleGrid.jsx";
import { INFO_GRID_SX, INFO_WIDE_ROW, OrgPanelHead } from "./OrgPanelHead.jsx";

/* 조직 상세 판 — 트리에서 조직을 고르면 오른쪽이 이것으로 반응한다. **고른 조직 하나를 관리하는 자리**다.
 *
 * ## 무엇을 걷었나
 *
 * 옛 판은 요약 타일 셋(부서 · 사용자 · 부서 미지정), 같은 수를 문장으로 되풀이한 「포함 관계」 줄, 그리고
 * 트리를 한 번 더 그린 「부서 N개」 두 줄기 목록을 들었다. 페이지 머리의 요약 타일 넷까지 더하면 한 화면이
 * 부서 수를 다섯 번, 구성원 수를 네 번 말했다. 지금은:
 *
 *   머리        이름 · 조직 · 상태 + 둘째 줄의 식별자 + 동작 묶음 하나
 *   부서 미지정  그런 사람이 있을 때만 「부서 미지정 N명」 절 — 수만이 아니라 그 사람들을 보여 준다
 *   정보        부서 수 · 조직 ID · 삭제 안내 · 비활성화 안내 · 변경 권한 안내
 *
 * 조직 전체의 구성원 수는 트리의 조직 줄이 말한다. 부서 목록은 트리가 그 목록이다.
 *
 * ## 조직을 바꾸는 권한은 서버가 말한다(`can_edit`)
 *
 * 조직 이름 · 상태 PATCH 는 전체 관리자만 통과한다(`require_global_management`). 서버가 그 답을 조직 응답에
 * 싣는데(`app/org/router.py::_org_view`) 아무 화면도 안 읽어서, 범위 관리자가 「수정」을 눌러 저장할 때가
 * 되어서야 403 을 봤다. 이제 그 값이 「수정」과 활성/비활성을 연다. 값을 모르는 옛 응답이면 이 화면이 이미
 * 쓰는 전역 판정(`management.kind`)으로 떨어진다.
 *
 * 조직에 삭제가 없는 것은 서버 계약이다 — 사용자와 부서가 org_id 로 이 행을 가리키고
 * 있어 지우면 그 참조가 통째로 끊긴다. 대신 「비활성화」가 새 사용을 막는다. */
export function OrgDetailPanel({ org, treeRow, singleOrg = false, headingRef, onCreated }) {
  const toast = useToast();
  const confirm = useConfirm();
  const invalidate = useInvalidateOrgCaches();
  const auth = useAuth();
  const [editing, setEditing] = React.useState(false);
  const [adding, setAdding] = React.useState(false);

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
  /* 조직 줄의 `user_count` 가 곧 부서가 지정되지 않은 사람이다(app/org/tree.py — 보관된 계정 포함). */
  const unassigned = treeRow ? treeRow.user_count || 0 : 0;
  /* 부서 미지정 명단은 **조직으로 좁혀지지 않는다**(`useUnassignedPeople`) — 보이는 조직이 하나일 때만
     받아 그린다. 여럿이면 수와 사용자 화면 링크만 둔다. */
  const people = useUnassignedPeople({ enabled: singleOrg && unassigned > 0 });

  const actor = auth.data || {};
  const mgmt = actor.management || {};
  const canEdit = typeof org.can_edit === "boolean" ? org.can_edit : (!mgmt.kind || mgmt.kind === "global");

  /* 🔴 **자기 조직 정지는 시스템 관리자만 할 수 있다**(org-09).
   *
   * 서버 판정은 `app/org/service.py::ensure_may_suspend_org` 다 — 역할과 조직 id 둘만 보는
   * 조건이라 화면이 그대로 재현할 수 있다. 재현하지 않던 동안에는 「소속 사용자 20명이 지금
   * 즉시 로그아웃됩니다」라는 **되돌릴 수 없는 예고**를 읽고 확인까지 누른 관리자가 그
   * 뒤에야 403 토스트를 받았다. 최악의 경우 정말 끊긴 줄 알고 대응을 시작한다.
   * 같은 콘솔이 「조직 추가」에 대해서는 이미 이 규칙을 쓴다(OrgConsole.jsx).
   *
   * 남의 조직 정지는 그대로 둔다 — 자기 세션이 안 끊기므로 서버도 막지 않는다. 활성화도
   * 그대로다(정지를 푸는 것은 이 함수의 대상이 아니다). 둘 다 `can_edit` 가 먼저다. */
  const canSuspend = actor.role === "system_admin" || actor.org_id !== org.id;

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

  const statusItem = !canEdit ? null
    : active
      ? (canSuspend
        ? { key: "suspend", label: "비활성화", tone: "danger", disabled: setStatus.isPending, onClick: suspend }
        : null)
      : { key: "activate", label: "활성화", disabled: setStatus.isPending, onClick: () => setStatus.mutate("active") };
  const menu = [
    { key: "audit", label: "감사 로그에서 보기", href: "#/audit?object_type=organization&object_id=" + org.id },
    statusItem,
  ];
  const departmentCount = org.department_count || 0;

  return (
    <Card sx={{ display: "grid", gap: 3, alignContent: "start" }}>
      <OrgPanelHead
        title={org.name}
        headingRef={headingRef}
        badges={(
          <>
            <Badge value="조직" kind="info" />
            <Badge value={active ? "사용 중" : "미사용"} kind={active ? "ok" : "warn"} />
          </>
        )}
        /* 조직의 정체는 식별자다 — 부서 판의 둘째 줄(전체 경로)과 같은 자리다. 정보 절에서 한 번 더 말하지 않는다. */
        identity={(
          <Typography component="p" sx={{ m: 0, fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>
            식별자{" "}
            <Box component="span" sx={{ color: "text.primary" }}>{org.slug}</Box>
          </Typography>
        )}
        actionsLabel={org.name + " 작업"}
        /* 동작 순서는 제품의 머리 규칙과 같다 — 보조(수정) → 더 보기 → 채움(부서 추가)이 오른쪽 끝이다(D-501). */
        actions={(
          <>
            {canEdit ? <Button size="sm" onClick={() => setEditing(true)}>수정</Button> : null}
            <OverflowMenu size="sm" ariaLabel={org.name + " 작업 더 보기"} items={menu} />
            <Button size="sm" variant="primary" onClick={() => setAdding(true)}>부서 추가</Button>
          </>
        )}
      />

      {unassigned > 0 ? (
        <OrgPeopleSection
          label="부서 미지정"
          count={unassigned}
          query={singleOrg ? people : null}
          recorded={unassigned}
          /* `department_id=none` 은 서버 센티널이다(P-61) — 사용자 화면이 그 사람들만 거른 목록을 연다. */
          listHref="#/users?department_id=none"
          emptyText="지금 쓰는 계정 중에는 부서가 없는 사람이 없습니다."
          note={(
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              사용자 화면은 다른 조직에서 부서가 없는 사람도 함께 보여 줍니다.
            </Typography>
          )}
        />
      ) : null}

      <Section title="정보" sx={{ mb: 0 }}>
        <DetailGrid sx={INFO_GRID_SX}>
          <DetailRow label="부서">{departmentCount ? departmentCount + "개" : "없음"}</DetailRow>
          <DetailRow label="조직 ID">
            <TechDetail label="식별자 보기">{org.id}</TechDetail>
          </DetailRow>
          <DetailRow label="삭제" sx={INFO_WIDE_ROW}>
            조직은 지울 수 없습니다. 사용자와 부서가 이 조직을 가리키고 있어 지우면 그 연결이
            끊깁니다. 대신 비활성화로 새 사용을 막으세요.
          </DetailRow>
          {/* 메뉴에서 사라진 항목 대신 이 줄들이 이유를 말한다 — 부서 판이 삭제에 대해 쓰는 규칙과 같다. */}
          {canEdit && active && !canSuspend ? (
            <DetailRow label="비활성화" sx={INFO_WIDE_ROW}>
              자기 조직 비활성화는 시스템 관리자만 할 수 있습니다. 비활성화하면 소속 사용자가
              모두 즉시 로그아웃되어, 되돌릴 사람이 이 조직 안에 남지 않기 때문입니다.
            </DetailRow>
          ) : null}
          {!canEdit ? (
            <DetailRow label="변경 권한" sx={INFO_WIDE_ROW}>
              조직 이름과 상태는 전체 관리자만 바꿀 수 있습니다.
            </DetailRow>
          ) : null}
        </DetailGrid>
      </Section>

      <OrgEditModal open={editing} org={org} onClose={() => setEditing(false)} />
      <DeptCreateModal
        open={adding}
        onClose={() => setAdding(false)}
        fixedOrgId={org.id}
        title={org.name + "에 부서 추가"}
        onCreated={onCreated}
      />
    </Card>
  );
}
