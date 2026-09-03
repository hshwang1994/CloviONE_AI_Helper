import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { api } from "../lib/api.js";
import { Badge, Button, FormModal, Modal, ModalFooter, OverflowMenu, useConfirm, useToast } from "../ui/kit.jsx";
import { FilterSelect } from "../ui/filters.jsx";
import { MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { celebrate } from "../ui/celebrate.js";

/* 회차의 한 바퀴 — **열고 닫는 자리**.
 *
 * ## 왜 이 파일이 생겼나
 *
 * 서버에는 `POST /api/work/sprints/{id}/state` 와 `/close` 가 처음부터 있었는데
 * **부르는 화면이 한 곳도 없었다.** 그래서 이 제품에는 스프린트의 한 바퀴가 없었다:
 *
 *   * 회차를 만들면 영원히 `planned` 이라 `active` 가 언제나 거짓이고,
 *   * 그래서 「진행 중」 배지가 절대 안 붙고 자동 선택은 사실상 「가장 최근 회차」였고,
 *   * 닫는 행동이 없으니 **미완료 이월**(`close_sprint_and_carry_over`)이 도달 불가였다.
 *
 * 사용자가 「티켓을 어떻게 뭘 바꿔서 스프린트 회의를 해야 하는지 모르겠다, 작업 보드에서
 * 빠지지도 않는다」고 한 것이 이 빈 자리다. 흐름은 이렇다:
 *
 *   백로그에 쌓는다 → 회차를 만든다 → 담는다 → **연다** → 칸반에서 진행한다
 *      → 회의에서 본다 → **닫는다** + 미완료를 이월한다
 *
 * ## 두 화면이 같은 부품을 쓴다
 *
 * 작업 보드와 스프린트 회의 둘 다 회차를 앞에 두고 일한다. 각자 단추를 만들면 한쪽만
 * 이월 대화상자를 갖는 날이 오고, 그러면 어느 화면에서 닫았는지에 따라 결과가 달라진다.
 */

export const SPRINT_STATE_LABEL = {
  planned: "예정",
  active: "진행 중",
  closed: "종료",
};

const SPRINT_STATE_KIND = { planned: "neutral", active: "info", closed: "ok" };

/** 회차 상태 배지 한 장. 상태를 **항상** 보여 준다 — 안 보이면 왜 못 여는지도 안 보인다. */
export function sprintStateLabel(sprint) {
  if (!sprint) return "";
  return SPRINT_STATE_LABEL[sprint.state] || sprint.state || "";
}

export function SprintStateBadge({ sprint }) {
  if (!sprint || !sprint.state) return null;
  return (
    <Badge
      value={sprintStateLabel(sprint)}
      kind={SPRINT_STATE_KIND[sprint.state] || "neutral"}
    />
  );
}

/** 회차 조작 권한 — 서버 게이트(`PROJECT_WRITE`)의 화면 쪽 그림자.
 * 보드·회의가 각자 같은 판정을 손으로 적던 것을 한 곳으로 모은다. */
export function useCanPlanSprint() {
  const auth = useAuth();
  return hasRole(MODERATOR_ROLES, auth.data && auth.data.role);
}

/** 회차 머리의 안내문 — state(사람이 누른 것) × phase(날짜) × 역할을 **함께** 본다.
 *
 * 🔴 예전 문구는 phase 만 봤다. 그래서 기간이 시작된 planned 회차가 「예정」 배지 옆에
 * 「진행 중인 회차입니다」를 달았고, 기간이 지난 planned 회차는 존재하지 않는 단추를
 * 가리켰다(「회차 닫기」는 active 에만 있다). 일반 참여자에게는 단추 자체가 없으므로
 * (canPlan 게이트) 문구도 단추를 시키는 대신 누가 할 수 있는지를 말한다.
 */
export function sprintPhaseNote({ state, phase, canPlan }) {
  if (state === "closed") {
    return "이미 닫은 회차입니다. 안 끝났던 티켓은 닫을 때 옮긴 곳에 있고, 여기 기록은 그대로 남습니다.";
  }
  if (state === "planned") {
    if (phase === "after") {
      return canPlan
        ? "기간이 지나도록 열지 않은 회차입니다. 기간을 고쳐서 열거나, 잘못 만든 회차라면 삭제할 수 있습니다."
        : "기간이 지나도록 열지 않은 회차입니다. 회차 정리는 운영자가 할 수 있습니다.";
    }
    if (phase === "during") {
      return canPlan
        ? "기간이 시작됐지만 아직 열지 않은 회차입니다. 「회차 열기」를 누르면 지금부터 진행을 셉니다."
        : "기간이 시작됐지만 아직 열지 않은 회차입니다. 회차 열기는 운영자가 할 수 있습니다.";
    }
    return canPlan
      ? "아직 열지 않은 회차입니다. 「회차 열기」를 누르면 진행을 세기 시작합니다."
      : "아직 열지 않은 회차입니다. 회차 열기는 운영자가 할 수 있습니다.";
  }
  if (state === "active") {
    if (phase === "before") {
      return "시작일보다 먼저 연 회차입니다. 진행은 오늘부터 셉니다.";
    }
    if (phase === "after") {
      return canPlan
        ? "기간이 지난 회차입니다. 「회차 닫기」를 누르면 안 끝난 일을 다음 회차로 넘길 수 있습니다."
        : "기간이 지난 회차입니다. 안 끝난 일은 운영자가 회차를 닫을 때 다음 회차로 넘어갑니다.";
    }
    return "진행 중인 회차입니다. 남은 일과 막힌 일을 먼저 봅니다.";
  }
  return "";
}

/** 미완료를 어디로 보낼지 고르는 대화상자.
 *
 * 기본은 **다음 회차로 이월**이다. 안 옮기면 그 티켓들은 어느 회차에도 없는 상태가 되고,
 * 다음 계획 회의에서 목록을 손으로 다시 만들게 된다 — 그러면 몇 건은 반드시 빠진다.
 * 그래도 고를 수는 있어야 한다: 회차를 접고 다시 계획하겠다는 결정도 정상이다.
 */
function CloseDialog({ open, onClose, sprint, sprints, busy, onSubmit }) {
  const CARRY_BACKLOG = "__backlog__";
  const later = (sprints || []).filter(
    (s) =>
      s.id !== (sprint && sprint.id)
      && s.state !== "closed"
      // 서버의 이월 규칙과 같은 축 — 팀 전체 회차(project_id 없음)는 언제나 받고,
      // 프로젝트 회차는 같은 프로젝트만 받는다. 여기서 안 거르면 「전체」 필터로 연
      // 화면에서 다른 프로젝트 회차가 후보로 떠서, 고르면 서버 거절만 본다.
      && (s.project_id == null || s.project_id === ((sprint && sprint.project_id) ?? null))
  );
  const [target, setTarget] = React.useState("");

  // 🔴 열리는 **순간에만** 기본값을 세운다. 예전에는 sprints 배열이 의존성이라, 대화상자가
  // 열려 있는 동안 회차 목록이 재조회돼 배열 신원만 바뀌어도 사용자가 고른 이월 대상이
  // 첫 항목으로 조용히 리셋됐다 — 닫기는 되돌릴 수 없는 동작이라 그 리셋의 값이 크다.
  React.useEffect(() => {
    if (!open) return;
    setTarget(later.length ? later[0].id : CARRY_BACKLOG);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="회차 닫기"
      size="sm"
      footer={
        <ModalFooter
          onCancel={onClose}
          onSubmit={() => onSubmit(target === CARRY_BACKLOG ? null : target)}
          submitLabel="닫기"
          busy={busy}
        />
      }
    >
      <Stack spacing={1.5}>
        <Typography variant="body2">
          {`«${(sprint && sprint.name) || ""}» 를 닫습니다. 아직 안 끝난 티켓을 어디로 보낼지 고르세요.`}
        </Typography>
        <FilterSelect
          label="안 끝난 티켓"
          value={target}
          onChange={setTarget}
          options={[
            ...later.map((s) => ({ value: s.id, label: `${s.name} 로 이월` })),
            { value: CARRY_BACKLOG, label: "백로그로 되돌림" },
          ]}
        />
        <Typography variant="caption" color="text.secondary">
          끝난 티켓은 그대로 이 회차에 남습니다. 회차를 닫아도 기록은 사라지지 않습니다.
        </Typography>
      </Stack>
    </Modal>
  );
}

/** 회차를 열고 닫는 단추 묶음. 회차를 안 골랐으면 아무것도 안 그린다. */
/** 수정 폼의 칸. 닫은 회차의 기간은 서버가 거절한다 — 못 고치는 칸은 보여 주지 않는다. */
function sprintEditFields(sprint) {
  const base = [
    { name: "name", label: "이름", required: true, maxLength: 120 },
    { name: "starts_on", label: "시작일", type: "date", required: true },
    { name: "ends_on", label: "종료일", type: "date", required: true },
    { name: "goal", label: "목표", type: "textarea", maxLength: 2000 },
  ];
  return sprint && sprint.state === "closed" ? base.filter((f) => f.type !== "date") : base;
}

export function SprintLifecycle({ sprint, sprints, size = "sm", onDeleted }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [closing, setClosing] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const canPlan = useCanPlanSprint();

  function refresh() {
    // 나머지 판(work-board·work-backlog·sprint-meeting·티켓 목록·홈)은 전부
    // `ticket-views.js` 접두사 표가 안다 — 개별 나열은 그 표의 존재 이유와 어긋난다.
    // `refetchType:"all"` 은 삭제·복원급 전용 규약이라 쓰지 않는다: 활성 화면만 즉시
    // 다시 읽고, 비활성 목록은 stale 로 남아 다음 마운트에서 새로 읽는다.
    qc.invalidateQueries({ queryKey: ["work-sprints"] });
    invalidateTicketViews(qc);
  }

  const update = useMutation({
    mutationFn: (body) =>
      api(`/api/work/sprints/${encodeURIComponent(sprint.id)}`, { method: "PATCH", body }),
    onSuccess: () => {
      refresh();
      setEditing(false);
      toast("회차를 고쳤습니다.", "success");
    },
    onError: (e) => toast((e && e.message) || "회차를 고치지 못했습니다.", "error"),
  });

  const remove = useMutation({
    mutationFn: () =>
      api(`/api/work/sprints/${encodeURIComponent(sprint.id)}`, { method: "DELETE" }),
    onSuccess: (res) => {
      refresh();
      const detached = (res && res.detached) || 0;
      toast(
        detached
          ? `회차를 삭제하고 담겨 있던 ${detached}건을 백로그로 돌렸습니다.`
          : "회차를 삭제했습니다.",
        "success",
      );
      if (onDeleted) onDeleted();
    },
    onError: (e) => toast((e && e.message) || "회차를 삭제하지 못했습니다.", "error"),
  });

  const open = useMutation({
    mutationFn: (id) =>
      api(`/api/work/sprints/${encodeURIComponent(id)}/state`, {
        method: "POST",
        body: { state: "active" },
      }),
    onSuccess: () => {
      refresh();
      toast("회차를 열었습니다. 오늘부터 진행을 셉니다.", "success");
    },
    // 같은 프로젝트에 이미 열린 회차가 있으면 서버가 그 이름을 담아 409 로 거절한다.
    onError: (e) => toast((e && e.message) || "회차를 열지 못했습니다.", "error"),
  });

  const close = useMutation({
    mutationFn: ({ id, target }) =>
      api(`/api/work/sprints/${encodeURIComponent(id)}/close`, {
        method: "POST",
        body: { target_sprint_id: target },
      }),
    onSuccess: (res) => {
      refresh();
      setClosing(false);
      /* 한 회차를 끝낸 순간이다 — 팀이 함께 보는 화면에서 가장 분명한 완료 지점이라
         여기서 축하한다(동작 최소화면 `celebrate` 가 스스로 안 터진다). */
      celebrate();
      const carried = (res && res.carried_over) || 0;
      toast(
        carried
          ? `회차를 닫고 안 끝난 ${carried}건을 옮겼습니다.`
          : "회차를 닫았습니다. 안 끝난 티켓은 없었습니다.",
        "success",
      );
    },
    onError: (e) => toast((e && e.message) || "회차를 닫지 못했습니다.", "error"),
  });

  if (!sprint || !sprint.id) return null;
  // 서버가 `PROJECT_WRITE` 로 막는다. 여기서 감추는 것은 권한 보장이 아니라 **누를 수 없는
  // 단추를 안 보여 주는 것**이다 — 눌러서 403 을 보는 것은 안내가 아니다.
  if (!canPlan) return null;

  return (
    <>
      {sprint.state === "planned" ? (
        <Button
          variant="primary"
          size={size}
          loading={open.isPending}
          onClick={() => open.mutate(sprint.id)}
        >
          회차 열기
        </Button>
      ) : null}
      {sprint.state === "active" ? (
        <Button variant="secondary" size={size} onClick={() => setClosing(true)}>
          회차 닫기
        </Button>
      ) : null}
      {/* 이름 오타·기간 실수·잘못 만든 회차를 고치는 자리 — 없어서 전부 영구였다.
          삭제는 planned 만 준다(서버 규칙과 같다): active 는 닫기로 정리하고 closed 는
          기록으로 남는다. */}
      <OverflowMenu
        size={size}
        ariaLabel="회차 관리"
        items={[
          { label: "회차 수정", onClick: () => setEditing(true) },
          sprint.state === "planned"
            ? {
                label: "회차 삭제",
                onClick: async () => {
                  const ok = await confirm(
                    "삭제한 회차는 되살릴 수 없습니다. 담겨 있던 티켓은 백로그로 돌아갑니다. 이 회차를 삭제할까요?",
                    { danger: true, confirmLabel: "삭제" },
                  );
                  if (ok) remove.mutate();
                },
              }
            : null,
        ]}
      />
      <FormModal
        open={editing}
        title="회차 수정"
        submitLabel="저장"
        fields={sprintEditFields(sprint)}
        initial={{
          name: sprint.name || "",
          starts_on: sprint.starts_on || "",
          ends_on: sprint.ends_on || "",
          goal: sprint.goal || "",
        }}
        onSubmit={(values) =>
          update.mutateAsync(
            sprint.state === "closed"
              ? { name: values.name, goal: values.goal || null }
              : {
                  name: values.name,
                  starts_on: values.starts_on,
                  ends_on: values.ends_on,
                  goal: values.goal || null,
                },
          )
        }
        onClose={() => setEditing(false)}
      />
      <CloseDialog
        open={closing}
        onClose={() => setClosing(false)}
        sprint={sprint}
        sprints={sprints}
        busy={close.isPending}
        onSubmit={(target) => close.mutate({ id: sprint.id, target })}
      />
    </>
  );
}
