import React from "react";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Button, Modal, ModalFooter } from "../../ui/kit.jsx";
import { KO_WORD_BREAK } from "../../ui/theme.js";

/* 분류 관리 — 분류와 태그, 두 어휘를 한 창에서 고친다.
 *
 * ## 왜 한 창인가
 *
 * 두 어휘의 관리 규칙이 같다(추가는 누구나, 이름 고치기와 삭제는 운영자군, 사용 건수를
 * 먼저 보여 준다). 창을 둘로 나누면 같은 규칙이 두 벌의 화면을 갖고, 한쪽만 고치는 날이
 * 온다. 다른 것은 뜻 하나다 — 분류는 문서 하나에 하나(큰 갈래), 태그는 여럿(자유
 * 분류). 그 차이는 각 탭의 안내 문장이 말한다.
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

export function TaxonomyManager({
  open, onClose, canManage, busy,
  categories, tags,
  onAddCategory, onRenameCategory, onRemoveCategory,
  onAddTag, onRenameTag, onRemoveTag,
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
      <Tabs
        value={tab}
        onChange={(e, next) => setTab(next)}
        aria-label="분류 관리 탭"
        sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}
      >
        <Tab label="분류" />
        <Tab label="태그" />
      </Tabs>
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
      ) : (
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
      )}
    </Modal>
  );
}
