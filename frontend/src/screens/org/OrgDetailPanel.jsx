import React from "react";
import { useMutation } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import {
  Badge, Button, Callout, Card, DetailGrid, DetailRow, OverflowMenu, Section, TechDetail, useConfirm, useToast,
} from "../../ui/kit.jsx";
import { HeaderActions } from "../../ui/HeaderSlot.jsx";
import { handleApiError } from "../data-screen/apiError.js";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { useInvalidateOrgCaches } from "./orgQueries.js";
import { DeptCreateModal, OrgEditModal } from "./orgModals.jsx";
import { OrgMembersList } from "./OrgMembersList.jsx";
import { INFO_GRID_SX, INFO_WIDE_ROW, OrgPanelHead } from "./OrgPanelHead.jsx";

/* 조직 상세 판 — 트리에서 조직을 고르면 오른쪽이 이것으로 반응한다. **고른 조직 하나를 관리하는 자리**다.
 *
 * ## 무엇을 걷었나
 *
 * 옛 판은 요약 타일 셋(부서 · 사용자 · 부서 미지정), 같은 수를 문장으로 되풀이한 「포함 관계」 줄, 그리고
 * 트리를 한 번 더 그린 「부서 N개」 두 줄기 목록을 들었다. 페이지 머리의 요약 타일 넷까지 더하면 한 화면이
 * 부서 수를 다섯 번, 구성원 수를 네 번 말했다. 지금은:
 *
 *   머리        이름 · 조직 · 상태 + 둘째 줄의 식별자 + 「수정」
 *   예외        부서도 조직 직속도 아닌 사람이 있을 때만 한 줄 - 「목록 보기」가 구성원 목록을 그 사람들로 바꾼다
 *   구성원      이 조직의 사람 전부(검색 · 상태 · 소속 종류, 페이지로 받는다 - `OrgMembersList`)
 *   정보        부서 수 · 조직 ID · 삭제 안내 · 비활성화 안내 · 변경 권한 안내
 *
 * 부서 목록은 트리가 그 목록이다.
 *
 * ## 동작은 페이지 머리에 (계획 3.6, D-510)
 *
 * 「더 보기」와 주 동작 「부서 추가」는 페이지 머리의 오른쪽에 선다(`HeaderActions` - 콘솔이 자리를 낸다).
 * 판 안에서는 30px 이던 주 동작이 머리의 34px 보조 단추(「조직 추가」)보다 작아 위계가 거꾸로 읽혔다.
 * 판 머리에는 「수정」 하나만 남는다.
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
export function OrgDetailPanel({ org, treeRow, headingRef, onCreated }) {
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
  /* 부서도 조직 직속도 아닌 사람(정합성 화면의 「소속이 지정되지 않은 사용자」와 같은 정의, 지금 일하는 사람만). */
  const unassigned = treeRow ? treeRow.unassigned_count || 0 : 0;
  const [membership, setMembership] = React.useState("");

  const actor = auth.data || {};
  const mgmt = actor.management || {};
  /* 부서 범위 관리자는 미지정 사람을 볼 수 없다(`apply_user_scope`) - 그 수는 언제나 0 이라 0 이 사실인지 말할 수 없다. */
  const seesUnassigned = !mgmt.kind || mgmt.kind === "global" || mgmt.kind === "org";
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
        actions={canEdit ? <Button size="sm" onClick={() => setEditing(true)}>수정</Button> : null}
      />
      {/* 동작 순서는 제품의 머리 규칙과 같다 — 더 보기 → 채움(부서 추가)이 오른쪽 끝이다(D-501). 콘솔 밖에서 이 판만
          그리면(시험) 판 안에 그대로 선다. */}
      <HeaderActions
        fallback={(
          <>
            <OverflowMenu ariaLabel={org.name + " 작업 더 보기"} items={menu} />
            <Button variant="primary" onClick={() => setAdding(true)}>부서 추가</Button>
          </>
        )}
      >
        <OverflowMenu ariaLabel={org.name + " 작업 더 보기"} items={menu} />
        <Button variant="primary" onClick={() => setAdding(true)}>부서 추가</Button>
      </HeaderActions>

      {unassigned > 0 && membership !== "unassigned" ? (
        <Callout
          tone="warn" compact
          action={<Button size="sm" onClick={() => setMembership("unassigned")}>목록 보기</Button>}
        >
          부서가 지정되지 않은 사람이 {unassigned}명 있습니다.
        </Callout>
      ) : null}

      <OrgMembersList
        key={org.id}
        scope={{ kind: "org", orgId: org.id }}
        membership={membership}
        onMembership={setMembership}
        emptyText="이 조직에 속한 사람이 없습니다."
      />

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
          {!seesUnassigned ? (
            <DetailRow label="부서 미지정" sx={INFO_WIDE_ROW}>
              부서가 지정되지 않은 사람은 전체 또는 조직 관리자만 볼 수 있습니다.
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
