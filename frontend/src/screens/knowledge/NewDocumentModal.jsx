import React from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Callout, Modal, ModalFooter } from "../../ui/kit.jsx";
import { ProjectPicker } from "../../ui/ProjectPicker.jsx";
import { TagPicker } from "../../ui/TagPicker.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { PROJECT_NONE, PROJECT_UNASSIGNED_LABEL } from "./constants.js";

/* 새 문서 — **제목·분류·태그가 필수**이고 프로젝트와 템플릿은 선택이다 (문서 개편 3번).
 *
 * ## 왜 분류와 태그가 필수인가
 *
 * 둘 다 나중에 찾는 길이다. 비워 두고 만든 문서는 목록의 어느 조건에도 안 걸려서, 제목을
 * 정확히 기억하는 사람 말고는 다시 못 찾는다. 만드는 순간이 그 둘을 아는 유일한 순간이다.
 *
 * 막는 자리는 **이 대화상자뿐**이다. 서버에서 강제하면 AI 초안·문서 복원·이관·Import 가
 * 전부 422 로 죽는다 — 그 경로들은 분류를 나중에(내용을 보고) 붙이는 것이 옳다.
 *
 * ## 프로젝트는 선택이다
 *
 * 안 고르면 조직 공통 문서가 된다 — 서버가 공간을 찾거나 만든다. 화면은 「공간」이라는
 * 낱말을 몰라도 되고, 만들지 못하는 상태 자체가 없다.
 *
 * ## 폴더를 안 묻는다
 *
 * 폴더 축은 화면에서 걷혔다(문서 개편 1·5번). 표와 API 는 그대로 있지만 만들거나 고를
 * 자리가 없으므로, 여기서 고르게 두면 값을 넣을 수만 있고 뺄 수는 없는 칸이 된다.
 *
 * ## `lockedProject`
 *
 * 프로젝트 상세의 「문서」 탭이 이 모달을 재사용한다 — 그 자리에서는 프로젝트가 이미
 * 정해져 있으므로 고르는 칸 대신 고정 표기가 선다. */
export function NewDocumentModal({
  open, onClose, onSubmit, busy, templates, categories, initial,
  lockedProject = null, lockedProjectName = "", error = null,
}) {
  const [values, setValues] = React.useState(initial);
  React.useEffect(() => { if (open) setValues(initial); }, [open, initial]);

  const set = (patch) => setValues((prev) => ({ ...prev, ...patch }));
  const chosen = templates.find((t) => t.id === values.template) || templates[0];
  /* 필수 셋 — 제목·분류·태그. 프로젝트는 **없어도 된다**(안 고르면 공통 문서다).
     태그는 「최소 하나」다: 배열이 비어 있으면 못 만든다. */
  const canSubmit = Boolean(
    (values.title || "").trim()
    && values.category_id
    && (values.tags || []).length > 0,
  );
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
          <TextField
            select
            label="분류"
            required
            value={values.category_id || ""}
            onChange={(e) => set({ category_id: e.target.value })}
            InputLabelProps={{ shrink: true }}
            helperText="문서의 큰 갈래입니다. 분류 관리에서 갈래를 만들 수 있습니다."
            fullWidth
          >
            {categories.map((c) => (
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
            ))}
          </TextField>
          <TagPicker
            layout="form"
            required
            value={values.tags}
            onChange={(next) => set({ tags: next })}
            helperText="하나 이상 고릅니다. 없는 이름을 적으면 새로 만듭니다."
          />
          {/* 라벨은 필터 줄과 **같은 낱말**이다 — 같은 축을 두 자리가 두 이름으로 부르면
              사용자는 그것을 두 가지 설정으로 읽는다. */}
          {lockedProject ? (
            <TextField
              label="프로젝트"
              value={lockedProjectName || "이 프로젝트"}
              disabled
              InputLabelProps={{ shrink: true }}
              helperText="이 프로젝트를 볼 수 있는 사람이 이 문서를 볼 수 있습니다."
              fullWidth
            />
          ) : (
            <ProjectPicker
              label="프로젝트"
              noAllOption
              layout="form"
              value={values.project_id}
              onChange={(next) => set({ project_id: next || "" })}
              placeholder="고르지 않으면 프로젝트 미지정입니다"
              extraOptions={[{ value: PROJECT_NONE, label: PROJECT_UNASSIGNED_LABEL }]}
              helperText={
                values.project_id && values.project_id !== PROJECT_NONE
                  ? "이 프로젝트를 볼 수 있는 사람이 이 문서를 볼 수 있습니다."
                  : "조직의 모든 사람이 이 문서를 볼 수 있습니다."
              }
              sx={{ width: "100%", maxWidth: "none" }}
            />
          )}
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
      {/* 만들기 실패는 발 바로 위 — 쓰던 값이 그대로 있고, 다시 누르면 걷힌다(부르는 쪽이 `error` 를 준다). */}
      {error ? <Callout tone="danger" compact sx={{ mt: 2.5 }}>{error}</Callout> : null}
    </Modal>
  );
}
