import React from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Modal, ModalFooter } from "../../ui/kit.jsx";
import { ProjectPicker } from "../../ui/ProjectPicker.jsx";
import { TagPicker } from "../../ui/TagPicker.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { useTree } from "./queries.js";
import { flatten } from "./KnowledgeNav.jsx";
import { PROJECT_NONE, spaceForAxis } from "./constants.js";

/* 새 문서 — 제목과 프로젝트가 필수이고 나머지는 선택이다 (지시 22.5).
 *
 * ## 「공개 범위」를 안 묻는다
 *
 * 이 제품에서 문서의 가시성은 **공간이 정한다**(§5.3) — 문서마다 범위를 따로 고르게
 * 하면 없는 권한 모델을 새로 만드는 것이다. 대신 프로젝트를 고르는 자리에서 그 뜻을
 * 한 문장으로 말한다.
 *
 * ## 폴더 후보는 이 모달이 직접 묻는다
 *
 * 옛 모달은 목록 화면이 보던 공간의 폴더를 그대로 받았다 — 모달 안에서 **다른** 프로젝트를
 * 고르면 남의 공간 폴더 목록이 그대로 남아 있었다(잠복 결함). 지금은 고른 공간의 트리를
 * 여기서 묻는다.
 *
 * ## `lockedProject`
 *
 * 프로젝트 상세의 「문서」 탭이 이 모달을 재사용한다 — 그 자리에서는 프로젝트가 이미
 * 정해져 있으므로 고르는 칸 대신 고정 표기가 선다. 전송은 `project_id` 로 나가고 서버가
 * 그 프로젝트의 공간을 찾거나 만든다(`resolve_or_create_project_space`). */
export function NewDocumentModal({
  open, onClose, onSubmit, busy, spaces, templates, categories, initial,
  lockedProject = null, lockedProjectName = "",
}) {
  const [values, setValues] = React.useState(initial);
  React.useEffect(() => { if (open) setValues(initial); }, [open, initial]);

  const set = (patch) => setValues((prev) => ({ ...prev, ...patch }));
  const chosen = templates.find((t) => t.id === values.template) || templates[0];
  /* 🔴 후보는 **프로젝트 전체**다. 예전에는 라벨만 「프로젝트」고 옵션이 「이미 공간이
     있는 프로젝트」뿐이라, 22개 중 11개 프로젝트는 이 화면에서 아예 고를 수가 없었다 —
     「공간을 먼저 추가해야 문서를 만들 수 있는」 구조의 물리적 원인이 이 셀렉트였다.
     이제 값은 프로젝트 id(또는 공통)이고, 공간은 서버가 찾거나 만든다(§14.2). */
  const commonSpace = spaceForAxis(spaces, PROJECT_NONE);
  /* 고른 프로젝트에 이미 공간이 있으면 그 폴더 트리를 보여 준다. 아직 공간이 없는
     프로젝트(첫 문서)는 폴더도 없다 — 칸 자체가 서지 않고, 만들고 나서 옮길 수 있다
     (프로젝트 고정 모드와 같은 근거). */
  const targetSpace = lockedProject ? null : spaceForAxis(spaces, values.project_id);
  const tree = useTree(open && targetSpace ? targetSpace.id : "");
  const folders = flatten(tree.data?.folders || []);
  const canSubmit = Boolean((values.title || "").trim() && (values.project_id || lockedProject));
  /* 화살표 함수를 JSX 안에 안 둔다. `=>` 의 `>` 가 뒤따르는 라벨과 짝지어져 UX 동사표
     검사(`ux-writing-verb-table.test.js`)의 JSX 텍스트 추출을 오탐시킨다. */
  const submit = () => onSubmit(values);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="새 문서 만들기"
      size="lg"
      dirty={Boolean((values.title || "").trim())}
      /* 「만들기」를 **감추지 않고 비활성으로** 둔다. 조건을 못 채운 사람에게 필요한 것은
         버튼이 사라지는 것이 아니라 「무엇이 모자란가」이고, 그 답은 필수 표시가 붙은
         칸에 있다. */
      footer={(
        <ModalFooter
          onCancel={onClose}
          onSubmit={submit}
          disabled={!canSubmit}
          submitLabel="만들기"
          busy={busy}
        />
      )}
    >
      {/* 두 칸이 서로의 높이를 끌어올리지 않는다 — `alignItems: start` 가 없으면 템플릿
          칸이 길 때 왼쪽 폼이 함께 늘어나 칸 사이에 빈 띠가 생긴다. */}
      <Box sx={{
        display: "grid", gap: 3, alignItems: "start",
        gridTemplateColumns: { xs: "1fr", md: "1fr 16rem" },
      }}>
        <Stack spacing={2}>
          <TextField
            label="문서 제목"
            required
            autoFocus
            value={values.title}
            onChange={(e) => set({ title: e.target.value })}
            inputProps={{ maxLength: 500 }}
            InputLabelProps={{ shrink: true }}
            fullWidth
          />
          {/* 라벨은 좌측 내비·필터 줄과 **같은 낱말**이다 — 같은 축을 세 자리가 세
              이름으로 부르면 사용자는 그것을 세 가지 설정으로 읽는다. */}
          {lockedProject ? (
            <TextField
              label="문서 범위"
              value={lockedProjectName || "이 프로젝트"}
              disabled
              InputLabelProps={{ shrink: true }}
              helperText="이 프로젝트를 볼 수 있는 사람이 이 문서를 볼 수 있습니다."
              fullWidth
            />
          ) : (
            <ProjectPicker
              label="문서 범위"
              required
              noAllOption
              layout="form"
              value={values.project_id}
              onChange={(next) => set({ project_id: next || "", folder_id: "" })}
              placeholder="문서가 속할 범위를 고릅니다"
              extraOptions={commonSpace ? [{ value: PROJECT_NONE, label: "공통 문서" }] : []}
              helperText={
                values.project_id === PROJECT_NONE
                  ? "조직의 모든 사람이 이 문서를 볼 수 있습니다."
                  : values.project_id
                    ? "이 프로젝트를 볼 수 있는 사람이 이 문서를 볼 수 있습니다."
                    : "공통 문서로 두거나 프로젝트 하나를 고릅니다."
              }
              sx={{ width: "100%", maxWidth: "none" }}
            />
          )}
          {!lockedProject && targetSpace ? (
            <TextField
              select
              label="폴더"
              value={values.folder_id}
              onChange={(e) => set({ folder_id: e.target.value })}
              InputLabelProps={{ shrink: true }}
              helperText="폴더는 정리 자리입니다. 문서를 볼 수 있는 사람은 바뀌지 않습니다."
              fullWidth
            >
              <MenuItem value="">폴더 없음</MenuItem>
              {folders.map((f) => (
                <MenuItem key={f.id} value={f.id}>{"　".repeat(f.depth) + f.name}</MenuItem>
              ))}
            </TextField>
          ) : null}
          <TextField
            select
            label="카테고리"
            value={values.category_id || ""}
            onChange={(e) => set({ category_id: e.target.value })}
            InputLabelProps={{ shrink: true }}
            helperText="문서의 큰 갈래입니다. 분류 관리에서 갈래를 만들 수 있습니다."
            fullWidth
          >
            <MenuItem value="">분류 없음</MenuItem>
            {categories.map((c) => (
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
            ))}
          </TextField>
          <TagPicker
            layout="form"
            value={values.tags}
            onChange={(next) => set({ tags: next })}
            helperText="검색하거나 없는 이름을 적어 새로 만듭니다."
          />
        </Stack>

        <Stack spacing={1.5}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold }}>템플릿</Typography>
          <Stack spacing={0.75}>
            {templates.map((t) => (
              <Box
                key={t.id}
                component="button"
                type="button"
                onClick={() => set({ template: t.id })}
                aria-pressed={values.template === t.id}
                sx={(theme) => ({
                  ...KO_WORD_BREAK,
                  textAlign: "left",
                  cursor: "pointer",
                  font: "inherit",
                  color: "inherit",
                  p: 1.25,
                  borderRadius: 1,
                  border: `1px solid ${values.template === t.id
                    ? theme.palette.primary.main : theme.palette.divider}`,
                  background: values.template === t.id ? theme.palette.action.selected : "none",
                })}
              >
                <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
                  {t.name}
                </Typography>
              </Box>
            ))}
          </Stack>
          {chosen ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              {chosen.help}
            </Typography>
          ) : null}
        </Stack>
      </Box>
    </Modal>
  );
}
