import React from "react";
import { api } from "../../lib/api.js";
import { FormModal, useToast } from "../../ui/kit.jsx";
import { diffFields } from "../../lib/diffFields.js";
import { useDepartmentOptions, useInvalidateOrgCaches, useOrganizations } from "./orgQueries.js";

/* 조직 콘솔의 폼 모달 네 벌 — 문구와 규칙은 옛 registry/org.js 의 것을 그대로 잇는다.
 *
 * 오류는 FormModal 이 폼 안에 그린다(`onSubmit` 이 던지면 그 문장이 칸 위에 선다) —
 * 409 의 「무엇이 몇 건」 같은 서버 문장이 토스트로 스쳐 지나가지 않고 폼에 남는다.
 * 성공은 부르는 쪽이 닫고 토스트를 낸다. 수정은 `diffFields` 로 **바뀐 것만** PATCH 한다
 * (CONC-01) — 그 사이 다른 관리자가 바꾼 필드를 조용히 덮지 않는다. */

export function OrgCreateModal({ open, onClose, onCreated }) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  return (
    <FormModal
      open={open}
      title="조직 추가"
      fields={[
        { name: "name", label: "조직 이름", type: "text", required: true,
          help: "화면에 보이는 이름입니다." },
        { name: "slug", label: "식별자", type: "text", required: true,
          help: "영문 소문자, 숫자, 붙임표만 씁니다. 추가한 뒤에는 바꿀 수 없습니다." },
      ]}
      initial={{ name: "", slug: "" }}
      submitLabel="추가"
      onClose={onClose}
      onSubmit={async (body) => {
        const made = await api("/api/admin/organizations", { method: "POST", body });
        invalidate();
        toast("추가했습니다.");
        onClose();
        if (onCreated) onCreated(made);
      }}
    />
  );
}

export function OrgEditModal({ open, org, onClose }) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  return (
    <FormModal
      open={open}
      title="조직 수정"
      fields={[
        { name: "name", label: "조직 이름", type: "text", required: true,
          help: "이 조직 이름이 보이는 모든 화면에 바로 반영됩니다." },
      ]}
      initial={{ name: org?.name || "" }}
      submitLabel="저장"
      onClose={onClose}
      onSubmit={async (body) => {
        const changed = diffFields(body, { name: org?.name || "" });
        if (!Object.keys(changed).length) {
          toast("변경된 내용이 없습니다.");
          onClose();
          return;
        }
        await api("/api/admin/organizations/" + org.id, { method: "PATCH", body: changed });
        invalidate();
        toast("저장했습니다.");
        onClose();
      }}
    />
  );
}

/* 상위 부서 후보 — 자기 자신은 뺀다(자기 부모가 될 수 없다). 하위 부서를 부모로 고르는
 * 순환은 백엔드(app/org/tree.py::validate_parent)가 거절하므로 여기서 다시 계산하지
 * 않는다 — 같은 규칙을 두 곳에 두면 반드시 어긋난다.
 *
 * 🔴 다만 **조직이 다른 부서는 애초에 후보가 아니다**(org-03). 서버는 상위 부서가 이 행과
 * 같은 조직일 것을 요구하는데(`validate_parent`·`create_item` 둘 다), 후보를 전량으로 두면
 * 조직이 둘 이상인 설치에서 폼이 «고르면 반드시 422 로 실패하는» 선택지를 권한다. 그때
 * 서버 문구는 「알 수 없는 상위 부서입니다」라 원인(조직이 다르다)도 말해 주지 않는다.
 * 순환과 달리 이 조건은 화면이 이미 아는 사실이라 여기서 거른다 — 후보를 만드는 규칙이지
 * 판정을 두 벌로 두는 것이 아니다.
 *
 * **미사용 부서도 새 상위 부서가 될 수 없다**(xb-08, `app/org/service.py::ensure_parent_is_active`).
 * 조직과 같은 이유로 후보에서 뺀다. 수정 폼의 **지금 상위 부서**(`keepId`)만은 미사용이어도 남긴다 —
 * 서버도 부모가 실제로 바뀔 때만 그 규칙을 보고, 빼 버리면 이름만 고치는 폼이 지금 값을 잃는다. */
function parentOptions(rows, { selfId = null, orgId = null, keepId = null } = {}) {
  return [{ value: "", label: "(최상위)" }].concat(
    (rows || [])
      .filter((d) => d.id !== selfId)
      .filter((d) => !orgId || !d.org_id || d.org_id === orgId)
      .filter((d) => d.active !== false || (keepId && d.id === keepId))
      .map((d) => ({ value: d.id, label: d.name })),
  );
}

/* 부서 추가 — **어느 조직에, 어느 부서 밑에 만드는지는 누른 자리가 이미 말한다.**
 *
 * 옛 입구는 선택과 무관한 페이지 머리였다. 그래서 창이 조직을 **다시** 물었고(조직 칸),
 * 방금 트리에서 고른 부서 밑에 만들려 해도 상위 부서를 처음부터 찾아야 했다. 지금 입구는
 * 조직 판의 「부서 추가」와 부서 판의 「하위 부서 추가」 둘이고, 부르는 쪽이 조직을 고정하고
 * (`fixedOrgId` — 요청에 그대로 실린다) 상위 부서를 미리 채운다(`defaultParentId`). 조직 칸은
 * 없다 — 고정된 값을 고를 수 있는 것처럼 세우면 그 칸은 거짓말이다.
 *
 * 상위 부서 목록이 아직 안 왔을 때 미리 채운 값은 `defaultParentLabel` 로 이름을 갖는다.
 * 없으면 선택기가 「선택 안 함」을 보이면서 요청에는 그 부서가 실리는 순간이 생긴다.
 *
 * 정지된 조직에도 부서를 만들 수 있다 — 되살리기 전에 조직도를 미리 손보는 것은 정상 업무라
 * 서버가 막지 않는다(app/org/service.py::create_item). 다만 **그 상태를 말한다**: 정지된 조직에
 * 만든 부서는 그 조직 사람이 아무도 못 쓴다(전원 로그아웃 상태다, org-17). 낱말은 같은 콘솔의
 * 조직 배지와 맞춘다(「미사용」). */
export function DeptCreateModal({
  open, onClose, fixedOrgId = "", defaultParentId = "", defaultParentLabel = "",
  title = "부서 추가", onCreated,
}) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  const departments = useDepartmentOptions();
  const orgs = useOrganizations();
  const orgRows = (orgs.data && orgs.data.items) || [];
  const deptRows = (departments.data && departments.data.items) || [];
  const fixedOrg = fixedOrgId ? orgRows.find((o) => o.id === fixedOrgId) : null;
  const suspended = Boolean(fixedOrg && fixedOrg.status !== "active");

  const options = parentOptions(deptRows, { orgId: fixedOrgId || null });
  if (defaultParentId && !options.some((o) => o.value === defaultParentId)) {
    options.push({ value: defaultParentId, label: defaultParentLabel || "고른 부서" });
  }

  const fields = [
    { name: "name", label: "부서 이름", type: "text", required: true,
      help: suspended
        ? "이 조직은 미사용 상태라 여기에 추가한 부서는 조직을 다시 활성화할 때까지 아무도 쓸 수 없습니다."
        : "사용자 폼의 '부서' 목록에 바로 나타납니다." },
    { name: "parent_id", label: "상위 부서", type: "select", options,
      help: "비우면 최상위 부서가 됩니다. 이 조직에서 사용 중인 부서만 상위로 고를 수 있습니다." },
  ];

  return (
    <FormModal
      open={open}
      title={title}
      fields={fields}
      initial={{ name: "", parent_id: defaultParentId || "" }}
      submitLabel="추가"
      onClose={onClose}
      onSubmit={async (body) => {
        const payload = fixedOrgId ? { ...body, org_id: fixedOrgId } : body;
        const made = await api("/api/admin/departments", { method: "POST", body: payload });
        invalidate();
        toast("추가했습니다.");
        onClose();
        if (onCreated) onCreated(made);
      }}
    />
  );
}

export function DeptEditModal({ open, dept, onClose }) {
  const toast = useToast();
  const invalidate = useInvalidateOrgCaches();
  const departments = useDepartmentOptions();
  const initial = { name: dept?.name || "", parent_id: dept?.parent_id || "" };
  return (
    <FormModal
      open={open}
      title="부서 수정"
      fields={[
        { name: "name", label: "부서 이름", type: "text", required: true,
          help: "이름을 바꾸면 이 부서를 쓰는 모든 사용자(소속 인원)에게 즉시 반영됩니다." },
        /* 수정에서는 조직이 이미 정해져 있다 — 그 조직의 부서만 후보다(org-03). 지금 상위 부서는
           미사용이어도 후보에 남는다(`parentOptions` 의 `keepId`). */
        { name: "parent_id", label: "상위 부서", type: "select",
          options: parentOptions((departments.data && departments.data.items) || [],
                                 { selfId: dept?.id, orgId: dept?.org_id, keepId: dept?.parent_id }),
          help: "비우면 최상위 부서가 됩니다. 같은 조직의 부서만 상위로 지정할 수 있고,"
            + " 하위 부서를 상위로 고르면 순환이 되어 저장되지 않습니다." },
      ]}
      initial={initial}
      submitLabel="저장"
      onClose={onClose}
      onSubmit={async (body) => {
        const changed = diffFields(body, initial);
        if (!Object.keys(changed).length) {
          toast("변경된 내용이 없습니다.");
          onClose();
          return;
        }
        await api("/api/admin/departments/" + dept.id, { method: "PATCH", body: changed });
        invalidate();
        toast("저장했습니다.");
        onClose();
      }}
    />
  );
}
