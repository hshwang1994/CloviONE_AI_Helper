import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { api } from "../lib/api.js";
import { Badge, Button, Modal, ModalFooter, useToast } from "../ui/kit.jsx";
import { FilterSelect } from "../ui/filters.jsx";
import { MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import { invalidateTicketViews } from "./ticket-views.js";

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

/** 미완료를 어디로 보낼지 고르는 대화상자.
 *
 * 기본은 **다음 회차로 이월**이다. 안 옮기면 그 티켓들은 어느 회차에도 없는 상태가 되고,
 * 다음 계획 회의에서 목록을 손으로 다시 만들게 된다 — 그러면 몇 건은 반드시 빠진다.
 * 그래도 고를 수는 있어야 한다: 회차를 접고 다시 계획하겠다는 결정도 정상이다.
 */
function CloseDialog({ open, onClose, sprint, sprints, busy, onSubmit }) {
  const CARRY_BACKLOG = "__backlog__";
  const later = (sprints || []).filter(
    (s) => s.id !== (sprint && sprint.id) && s.state !== "closed"
  );
  const [target, setTarget] = React.useState("");

  React.useEffect(() => {
    if (!open) return;
    setTarget(later.length ? later[0].id : CARRY_BACKLOG);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sprints]);

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
export function SprintLifecycle({ sprint, sprints, size = "sm" }) {
  const qc = useQueryClient();
  const toast = useToast();
  const auth = useAuth();
  const [closing, setClosing] = React.useState(false);
  const canPlan = hasRole(MODERATOR_ROLES, auth.data && auth.data.role);

  function refresh() {
    qc.invalidateQueries({ queryKey: ["work-sprints"] });
    qc.invalidateQueries({ queryKey: ["work-board"] });
    qc.invalidateQueries({ queryKey: ["work-backlog"] });
    qc.invalidateQueries({ queryKey: ["sprint-meeting"] });
    invalidateTicketViews(qc, { refetchType: "all" });
  }

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
