import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { ActionFooter, Button, Callout, Modal, ModalFooter, RowActions, Segmented, FieldLabel } from "../../ui/kit.jsx";
import { KO_WORD_BREAK } from "../../ui/theme.js";
import { bodyToText, textToBody } from "./templateText.js";

/* 분류 관리 — 분류와 태그, 두 어휘를 한 창에서 고친다.
 *
 * ## 왜 한 창인가
 *
 * 두 어휘의 관리 규칙이 같다(추가는 누구나, 이름 고치기와 삭제는 운영자군, 사용 건수를
 * 먼저 보여 준다). 창을 둘로 나누면 같은 규칙이 두 벌의 화면을 갖고, 한쪽만 고치는 날이
 * 온다. 다른 것은 뜻 하나다 — 분류는 문서 하나에 하나(큰 갈래), 태그는 여럿(자유
 * 분류). 그 차이는 각 탭의 안내 문장이 말한다.
 *
 * ## 틀도 여기다
 *
 * 세 번째 탭이 문서 틀이다. 새 화면을 만들지 않는 이유는 위와 같다 — 셋 다 「문서가 쓰는
 * 어휘를 조직이 스스로 정한다」는 한 가지 일이고, 입구가 셋이면 사람은 그중 둘을 못 찾는다.
 *
 * 🔴 **틀을 고치거나 지워도 그 틀로 이미 만든 문서는 안 바뀐다.** 그것이 규칙이라서가
 * 아니라 구조라서다 — `documents` 는 틀을 참조하지 않고, 본문은 문서를 만드는 순간
 * 복사된다(0027). 그 사실을 탭의 안내 문장이 사람에게 먼저 말한다.
 *
 * ## 「몇 건에 붙어 있는가」를 먼저 보여 준다
 *
 * 지우려는 사람에게 필요한 것은 그 수다. 0건인 어휘를 지우는 것과 서른 건에서 떼는 것은
 * 다른 일이고, 화면이 그 차이를 말하지 않으면 사람은 같은 마음으로 누른다. */

function VocabularyPanel({
  rows, canManage, busy, addLabel, emptyText, helpText, onAdd, onRename, onRemove,
}) {
  const [name, setName] = React.useState("");
  const [editing, setEditing] = React.useState(null);
  const [draft, setDraft] = React.useState("");
  const addId = React.useId();

  const add = () => {
    const clean = name.trim();
    if (!clean) return;
    onAdd(clean, () => setName(""));
  };

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
        {helpText}
      </Typography>
      <Stack direction="row" spacing={1} alignItems="flex-end">
        {/* 라벨은 칸 위에 선다(`FieldLabel`, 핸드오프 RULES §7). 옆 「추가」 단추는 칸 바닥에 맞춘다. */}
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <FieldLabel htmlFor={addId}>{addLabel}</FieldLabel>
          <TextField
            id={addId}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
            inputProps={{ maxLength: 80 }}
            size="small"
            fullWidth
          />
        </Box>
        <Button variant="primary" disabled={!name.trim() || busy} onClick={add}>추가</Button>
      </Stack>

      {rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          {emptyText}
        </Typography>
      ) : (
        <Stack spacing={0.5} sx={{ maxHeight: "20rem", overflowY: "auto" }}>
          {rows.map((row) => (
            <Stack
              key={row.id}
              direction="row"
              spacing={1}
              alignItems="center"
              sx={(theme) => ({
                py: 0.75, borderBottom: `1px solid ${theme.palette.divider}`,
              })}
            >
              {editing === row.id ? (
                <>
                  <TextField
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    size="small"
                    autoFocus
                    inputProps={{ maxLength: 80 }}
                    sx={{ flex: 1, minWidth: 0 }}
                  />
                  <Button
                    size="small"
                    variant="primary"
                    disabled={!draft.trim() || busy}
                    onClick={() => onRename(row, draft.trim(), () => setEditing(null))}
                  >
                    저장
                  </Button>
                  {/* 취소는 보조(흰 면)다 — 글자만 있는 단추는 목록 안 부수 동작의 어휘다(핸드오프 RULES §3). */}
                  <Button size="small" onClick={() => setEditing(null)}>취소</Button>
                </>
              ) : (
                <>
                  <Typography sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}>{row.name}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                    문서 {row.document_count ?? 0}건
                  </Typography>
                  {/* 줄 동작은 `RowActions` 다(30 보조 · 파괴, 조합 계약 C-4) — 표 행과 같은 어휘다. */}
                  {canManage ? (
                    <RowActions
                      ariaLabel={`${row.name} 작업`}
                      actions={[
                        { key: "rename", label: "수정", onClick: () => { setEditing(row.id); setDraft(row.name); } },
                        { key: "remove", label: "삭제", variant: "danger", onClick: () => onRemove(row) },
                      ]}
                    />
                  ) : null}
                </>
              )}
            </Stack>
          ))}
        </Stack>
      )}

      {canManage ? null : (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          이름을 고치거나 지우는 것은 운영자만 할 수 있습니다. 새로 추가하는 것은 누구나 할 수 있습니다.
        </Typography>
      )}
    </Stack>
  );
}

/* 틀 탭 — 목록과, 하나를 여는 편집 판.
 *
 * 「빈 문서」는 표의 행이 아니라 화면의 바탕이다(`templates.BLANK`). 목록에는 서지만
 * 고치기·지우기 단추를 안 준다 — 지워지면 새 문서 대화상자의 기본값이 없는 틀을 가리킨다. */
function TemplatePanel({
  rows, canManage, editing, draft, onDraft, onOpen, onRemove,
}) {
  const fieldId = React.useId();
  const { name, help, text } = draft;
  const setName = (v) => onDraft({ ...draft, name: v });
  const setHelp = (v) => onDraft({ ...draft, help: v });
  const setText = (v) => onDraft({ ...draft, text: v });

  if (editing) {
    return (
      <Stack spacing={2}>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={`${fieldId}-name`} required>틀 이름</FieldLabel>
          <TextField
            id={`${fieldId}-name`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            inputProps={{ maxLength: 80 }}
            size="small"
            fullWidth
            required
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={`${fieldId}-help`}>설명</FieldLabel>
          <TextField
            id={`${fieldId}-help`}
            value={help}
            onChange={(e) => setHelp(e.target.value)}
            inputProps={{ maxLength: 500 }}
            size="small"
            fullWidth
            helperText="새 문서 대화상자에서 이 틀 아래에 보이는 한 줄입니다."
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <FieldLabel htmlFor={`${fieldId}-body`}>본문</FieldLabel>
          <TextField
            id={`${fieldId}-body`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            multiline
            minRows={8}
            maxRows={16}
            size="small"
            fullWidth
            helperText="## 은 제목, - 는 글머리, 1. 은 번호입니다. 나머지 줄은 문단이 됩니다."
          />
        </Box>
        {/* 취소 · 저장은 이 창의 발이다(`TaxonomyManager` 가 틀을 고치는 동안 발을 바꾼다) — 예전에는 몸 안에 둘째 단추 줄(ghost 취소 +
            채움)이 서고 창 발의 「닫기」가 따로 있어 발이 둘이었다(핸드오프 RULES §8 모달 3단). */}
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
        틀은 새 문서가 시작할 뼈대입니다. 틀을 고치거나 지워도 그 틀로 이미 만든 문서는
        그대로 남습니다.
      </Typography>
      {/* 🔴 만들기는 **누구나**다. 서버가 그렇게 정해 뒀다 — 만들기는 `DOCUMENT_UPDATE`,
          고치기·지우기는 `DOCUMENT_DELETE`. 옆의 분류·태그 탭도 같은 사다리다(어휘를
          늘리는 일은 같은 무게라는 결정). 화면만 더 좁히면 서버가 허락한 일을 사람이
          못 하게 되고, 그 차이는 아무 데도 안 적혀 있다. */}
      <Stack direction="row" justifyContent="flex-end">
        <Button variant="primary" onClick={() => onOpen({ id: "new" })}>새 틀</Button>
      </Stack>

      <Stack spacing={0.5} sx={{ maxHeight: "20rem", overflowY: "auto" }}>
        {rows.map((row) => (
          <Stack
            key={row.id}
            direction="row"
            spacing={1}
            alignItems="center"
            sx={(theme) => ({ py: 0.75, borderBottom: `1px solid ${theme.palette.divider}` })}
          >
            <Stack sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={KO_WORD_BREAK}>{row.name}</Typography>
              {row.help ? (
                <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
                  {row.help}
                </Typography>
              ) : null}
            </Stack>
            {row.builtin ? (
              <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                기본 제공
              </Typography>
            ) : null}
            {canManage && !row.builtin ? (
              <RowActions
                ariaLabel={`${row.name} 작업`}
                actions={[
                  { key: "edit", label: "수정", onClick: () => onOpen(row) },
                  { key: "remove", label: "삭제", variant: "danger", onClick: () => onRemove(row) },
                ]}
              />
            ) : null}
          </Stack>
        ))}
      </Stack>

      {canManage ? null : (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          틀을 고치거나 지우는 것은 운영자만 할 수 있습니다. 새로 만드는 것은 누구나 할 수 있습니다.
        </Typography>
      )}
    </Stack>
  );
}

export function TaxonomyManager({
  open, onClose, canManage, busy,
  categories, tags, templates,
  onAddCategory, onRenameCategory, onRemoveCategory,
  onAddTag, onRenameTag, onRemoveTag,
  editingTemplate, onOpenTemplate, onCancelTemplate,
  onCreateTemplate, onSaveTemplate, onRemoveTemplate,
  error = null,
}) {
  const [tab, setTab] = React.useState(0);
  React.useEffect(() => { if (!open) setTab(0); }, [open]);

  /* 틀 고치기 판의 값 — 발(취소 · 저장)이 이 창의 발이라 값을 창이 든다. 서버가 본문을 실어 주면 그때 판을 채운다(목록 응답에는 본문이 없다). */
  const [templateDraft, setTemplateDraft] = React.useState({ name: "", help: "", text: "" });
  React.useEffect(() => {
    if (!editingTemplate) { setTemplateDraft({ name: "", help: "", text: "" }); return; }
    setTemplateDraft({
      name: editingTemplate.name || "",
      help: editingTemplate.help || "",
      text: editingTemplate.body ? bodyToText(editingTemplate.body) : "",
    });
  }, [editingTemplate]);
  const templateOpen = tab === 2 && Boolean(editingTemplate);
  const templateIsNew = Boolean(editingTemplate) && editingTemplate.id === "new";
  const templateName = templateDraft.name.trim();
  const submitTemplate = () => {
    const payload = { name: templateName, help: templateDraft.help.trim(), body: textToBody(templateDraft.text) };
    if (templateIsNew) onCreateTemplate(payload); else onSaveTemplate(editingTemplate.id, payload);
  };

  /* 발은 하나다(핸드오프 RULES §8). 틀을 고치는 동안은 그 판의 취소 → 확정이고, 아닐 때는 「닫기」다. */
  const footer = templateOpen ? (
    <ActionFooter placement="modal">
      <Button onClick={onCancelTemplate}>취소</Button>
      <Button variant="primary" disabled={!templateName || busy} onClick={submitTemplate}>
        {/* 표준 동사표(PA-RC-0002 §3)가 「새로 만든다」를 「추가」로 정했다. 옆의 분류 · 태그 탭 단추와도 같은 낱말이다 — 한 창 안에서
            같은 일을 두 이름으로 부르지 않는다. */}
        {templateIsNew ? "추가" : "저장"}
      </Button>
    </ActionFooter>
  ) : <ModalFooter onCancel={onClose} cancelLabel="닫기" />;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="분류 관리"
      size="lg"
      footer={footer}
    >
      {/* 보기 전환은 세그먼티드(34)다 — 밑줄 탭(48)은 페이지 탭(`TabShell`)의 어휘다(핸드오프 RULES §3 · 계획 B-7). */}
      <Segmented
        ariaLabel="분류 관리 탭" value={tab} onChange={setTab}
        options={[{ value: 0, label: "분류" }, { value: 1, label: "태그" }, { value: 2, label: "틀" }]}
        sx={{ mb: 2 }}
      />
      {tab === 0 ? (
        <VocabularyPanel
          rows={categories}
          canManage={canManage}
          busy={busy}
          addLabel="새 분류"
          helpText="분류는 문서의 큰 갈래입니다. 문서 하나가 분류 하나에 속합니다."
          emptyText="아직 분류가 없습니다. 회사에 맞는 갈래를 여기서 만듭니다."
          onAdd={onAddCategory}
          onRename={onRenameCategory}
          onRemove={onRemoveCategory}
        />
      ) : tab === 1 ? (
        <VocabularyPanel
          rows={tags}
          canManage={canManage}
          busy={busy}
          addLabel="새 태그"
          helpText="태그는 자유 분류입니다. 문서 하나에 여러 태그를 붙일 수 있습니다."
          emptyText="아직 태그가 없습니다. 문서를 쓰면서 적은 태그도 여기에 모입니다."
          onAdd={onAddTag}
          onRename={onRenameTag}
          onRemove={onRemoveTag}
        />
      ) : (
        <TemplatePanel
          rows={templates || []}
          canManage={canManage}
          editing={editingTemplate}
          draft={templateDraft}
          onDraft={setTemplateDraft}
          onOpen={onOpenTemplate}
          onRemove={onRemoveTemplate}
        />
      )}
      {/* 추가 · 이름 고치기 · 지우기 · 틀 저장의 실패는 이 창 발 바로 위다 — 쓰던 값이 그대로 있고, 다시 시도하면
          걷힌다(부르는 쪽이 `error` 를 준다, 핸드오프 계획 표 6). */}
      {error ? <Callout tone="danger" compact sx={{ mt: 2.5 }}>{error}</Callout> : null}
    </Modal>
  );
}
