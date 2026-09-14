import React from "react";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Button, Modal, ModalFooter, Segmented } from "../../ui/kit.jsx";
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
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          label={addLabel}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          InputLabelProps={{ shrink: true }}
          inputProps={{ maxLength: 80 }}
          size="small"
          fullWidth
        />
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
                  <Button size="small" variant="ghost" onClick={() => setEditing(null)}>취소</Button>
                </>
              ) : (
                <>
                  <Typography sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}>{row.name}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                    문서 {row.document_count ?? 0}건
                  </Typography>
                  {canManage ? (
                    <>
                      <Button
                        size="small"
                        variant="ghost"
                        onClick={() => { setEditing(row.id); setDraft(row.name); }}
                      >
                        수정
                      </Button>
                      <Button size="small" variant="ghost" onClick={() => onRemove(row)}>
                        삭제
                      </Button>
                    </>
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
  rows, canManage, busy, editing, onOpen, onCancel, onCreate, onSave, onRemove,
}) {
  const [name, setName] = React.useState("");
  const [help, setHelp] = React.useState("");
  const [text, setText] = React.useState("");

  /* 서버가 본문을 실어 주면 그때 판을 채운다 — 목록 응답에는 본문이 없다. */
  React.useEffect(() => {
    if (!editing) { setName(""); setHelp(""); setText(""); return; }
    setName(editing.name || "");
    setHelp(editing.help || "");
    setText(editing.body ? bodyToText(editing.body) : "");
  }, [editing]);

  const isNew = Boolean(editing) && editing.id === "new";
  const clean = name.trim();

  if (editing) {
    return (
      <Stack spacing={2}>
        <TextField
          label="틀 이름"
          value={name}
          onChange={(e) => setName(e.target.value)}
          InputLabelProps={{ shrink: true }}
          inputProps={{ maxLength: 80 }}
          size="small"
          fullWidth
          required
        />
        <TextField
          label="설명"
          value={help}
          onChange={(e) => setHelp(e.target.value)}
          InputLabelProps={{ shrink: true }}
          inputProps={{ maxLength: 500 }}
          size="small"
          fullWidth
          helperText="새 문서 대화상자에서 이 틀 아래에 보이는 한 줄입니다."
        />
        <TextField
          label="본문"
          value={text}
          onChange={(e) => setText(e.target.value)}
          multiline
          minRows={8}
          maxRows={16}
          InputLabelProps={{ shrink: true }}
          size="small"
          fullWidth
          helperText="## 은 제목, - 는 글머리, 1. 은 번호입니다. 나머지 줄은 문단이 됩니다."
        />
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button variant="ghost" onClick={onCancel}>취소</Button>
          <Button
            variant="primary"
            disabled={!clean || busy}
            onClick={() => {
              const payload = { name: clean, help: help.trim(), body: textToBody(text) };
              if (isNew) onCreate(payload); else onSave(editing.id, payload);
            }}
          >
            {/* 표준 동사표(PA-RC-0002 §3)가 「새로 만든다」를 「추가」로 정했다. 옆의
                분류·태그 탭 단추와도 같은 낱말이다 — 한 창 안에서 같은 일을 두 이름으로
                부르지 않는다. */}
            {isNew ? "추가" : "저장"}
          </Button>
        </Stack>
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
              <>
                <Button size="small" variant="ghost" onClick={() => onOpen(row)}>수정</Button>
                <Button size="small" variant="ghost" onClick={() => onRemove(row)}>삭제</Button>
              </>
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
}) {
  const [tab, setTab] = React.useState(0);
  React.useEffect(() => { if (!open) setTab(0); }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="분류 관리"
      size="lg"
      footer={<ModalFooter onCancel={onClose} cancelLabel="닫기" />}
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
          busy={busy}
          editing={editingTemplate}
          onOpen={onOpenTemplate}
          onCancel={onCancelTemplate}
          onCreate={onCreateTemplate}
          onSave={onSaveTemplate}
          onRemove={onRemoveTemplate}
        />
      )}
    </Modal>
  );
}
