# 메일 틀 렌더 실측 (M1 · D-571) — 2026-10-15

> 대상은 다시 쓴 메일 틀(`app/mail/templates/layout.{html,txt}.j2`)과 로고 그림(`app/mail/assets/mark-72.png`)이다. 기준 커밋 `2b16a7ca` 위의
> 미커밋 작업 트리에서 쟀다. 원본 지문(sha256 앞 16자): `layout.html.j2` b03709a598b562c7 · `layout.txt.j2` ba80ab334e0b1f13 ·
> `content.py` 8c5d42e01f854fe2 · `mark-72.png` e2aa3f66a08a6d3d. 이 지문이 바뀌면 아래 결과는 다시 재야 한다.
> 실제 수신(랩 발송 → 회사 주소 · Gmail)은 이 문서의 범위가 아니다. 그 결과는 랩 배포 뒤 따로 적는다.

## 클래식 Outlook (Windows, Word 엔진) — COM 렌더

방법은 `scripts/ui_qa/outlook_render.ps1` 이다. 이 PC 에서 이미 떠 있던 클래식 Outlook 에 COM 으로 붙어 새 메일 작성 창을 열고, 로고를 CID
첨부(`PR_ATTACH_CONTENT_ID` = `clovi-mark@clovirassist`, 숨김)로 붙인 뒤 `HTMLBody` 를 넣고, 창을 맨 앞에 세워 화면을 찍었다. 찍은 창은 저장하지
않고 버렸다(`Close(1)`). 임시 보관함 수는 모든 실행에서 앞뒤가 같았다(12 → 12).

- Outlook 16.0.0.20326(Microsoft 365 클릭 투 런 16.0.20326.20142), 화면 2560x1440 · 배율 100%(96 DPI).
- Office 테마 값은 6(Windows 설정을 따름)이고 Windows 앱 테마가 밝음이라 **밝은 테마로만** 그렸다. 사용자가 쓰는 Outlook 이라 테마를 바꾸지
  않았다. 검정 테마는 아래 표에서 미검증이다.
- 작성 창이라 줄 끝 표시(↵)와 표 손잡이(⊕, □)가 보인다. 사용자의 편집기 표시 설정이고 받은 메일 읽기 창에는 없다. 설정은 건드리지 않았다.

최종 실행 `dist/ui-qa/mail-outlook/2026-10-15-final/`(그림 있음 다섯 종류 + 그림 없음 두 종류, 맨 앞 창 제목 일치 7/7)에서 잰 값:

| 종류 | 주 단추 | 단추 글자 가운데(세로 · 가로) | 로고 · 워드마크 | 사실 상자 행 |
|---|---|---|---|---|
| test | 155x44, 둥근 모서리 | +0.5 · -0.5px | 표식 30px 전부 보임, 세로 가운데 차이 +0.5px | 40 · 41 · 41px |
| ticket_assigned(알림) | 224x44, 둥근 모서리 | +0.5 · -1.0px | 같음 | 40px |
| password_reset | 200x44, 둥근 모서리 | +0.5 · -0.5px | 같음 | 사실 상자 없음 |
| account_locked | 170x44, 둥근 모서리 | +0.5 · -0.5px | 같음, 표지 「계정 보안」 하나 | 40 · 41px(셋째 행은 두 줄) |
| notify_email_verification | 단추 없음(코드 상자) | - | 같음 | 코드 상자 가운데 정렬 |
| test · ticket_assigned(그림 없음) | 위와 같음 | 위와 같음 | 깨진 그림 자리 36px, 워드마크는 한 줄 | 위와 같음 |

눈으로 확인한 것(`crop/*.png`): 대체 주소가 `?` 앞에서 두 줄로 나뉜다(재설정 메일). 날짜와 「ClovirAssist에서」가 한 덩어리로 붙는다. 바닥글은 세
줄이고 알림 메일은 「알림 메일 설정 바꾸기 | 문의: …」가 한 줄이다. 600px 판 밖으로 넘치는 칸이 없다.

### 반복에서 고친 것(같은 COM 렌더로 잼)

1. **단추 칸의 네모.** 계획대로 단추 칸에 `bgcolor` · `mso-padding-alt:0 24px` 를 두고 그 안에 VML `v:roundrect` 를 넣으니 Word 가 칸 바탕을
   VML 뒤에 48px 더 넓은 네모로 깔아 둥근 모서리가 덮였다(205x45, 네모 모서리). Outlook 전용 `<style>` 에서 그 칸의 바탕과 여백을 걷자
   VML 둥근 단추만 남았다(155x44). 칸을 갈래마다 따로 둔 변형도 같은 결과였고, 칸 마크업을 계획대로 두는 쪽을 골랐다.
2. **로고 잘림과 워드마크 처짐.** 로고 칸에 `line-height:36px` 와 `mso-line-height-rule:exactly` 를 함께 주니 Word 가 그림 위쪽을 잘라 표식이
   26px 만 보였고, 워드마크는 표식 가운데보다 8.5px 아래였다. 로고 칸에서 exactly 를 빼자 표식 30px 이 다 보였다. 워드마크를 36px exactly
   줄로 두면 3.5px 처졌고, 28px exactly 줄 + `valign=middle` 로 두자 차이가 +0.5px 이 됐다.
3. **한글과 영문 사이 간격.** Word 가 「ClovirAssist 에서」, 「2026 년 10 월」처럼 간격을 더 넣었다. Outlook 전용 `<style>` 의
   `text-autospace:none` 이 막았다.

## Chromium — 매트릭스와 로컬 E2E

- `scripts/ui_qa/mail_render_matrix.py`(Chromium 151): 표본 26종 × 보기 셋(밝음 · `prefers-color-scheme` 다크 · `data-ogsc` 강제 다크) × 폭
  600 · 375 = 156장, 판정 실패 0(`MAIL_MATRIX_OK (156/156)`). 판정은 가로 넘침 ≤ 1px · 단추 높이 44±1 · 단추 글자 흰색 · 단추 바탕
  보라 · 머리 띠 흰색 · 로고 36x36 · 로고와 워드마크 세로 가운데 차이 ≤ 1px 이다. 사실 행은 600px 에서 40 · 41px, 375px 에서 이름 위 · 값
  아래로 쌓여 62 · 63px 이다. 눈으로 본 장: test · approval_requested 밝음 600, ticket_assigned · backup_failed 다크 600,
  account_locked 밝음 375, invite 강제 다크 375.
- `scripts/ui_qa/mail_e2e.py`(실제 전송기 → 127.0.0.1 받는 쪽): 받은 메일 다섯 통 × 네 모양(밝음 · 밝음 그림 막힘 · 어둠 · 어둠 그림 막힘) ×
  600 · 375 의 가로 넘침 · 단추 높이 · 단추 글자색을 포함해 `MAIL_E2E_OK (162/162)`. M2 변경 뒤 다시 돌려 같은 결과다. 받은 알림 메일에는
  `List-Unsubscribe: <…/#/profile>` 이 있고 다른 종류에는 없다.

## 클라이언트 × 테마 × 그림 → 검증 수단

「Chromium(대리)」는 그 앱이 쓰는 규칙(`prefers-color-scheme` 또는 `data-ogsc`)을 Chromium 에 세워 본 것이다. 그 앱 자체의 렌더가 아니므로
실제 앱의 판정은 미검증으로 남긴다.

| 클라이언트 | 테마 | 그림 | 검증 수단 | 결과 |
|---|---|---|---|---|
| 클래식 Outlook(Windows, Word 엔진) | 밝음(Office 테마 「시스템 · 밝음」) | CID 로고 보임 | COM 렌더 | 통과(위 표) |
| 클래식 Outlook | 밝음 | 로고 없음(CID 를 못 찾음) | COM 렌더 | 통과 - 깨진 그림 자리 36px, 배치 그대로 |
| 클래식 Outlook | 검정 · 진한 회색 테마(본문 다크) | 보임 · 막힘 | 미검증 | 사용자가 쓰는 Outlook 의 테마를 바꾸지 않았다 |
| 새 Outlook · Outlook.com · OWA | 밝음 | 보임 · 막힘 | Chromium(대리, 밝음) | 대리 통과, 실제 앱 미검증 |
| 새 Outlook · Outlook.com · Outlook 앱 | 다크 | 보임 · 막힘 | Chromium(대리, `data-ogsc` 강제 다크) | 대리 통과(머리 띠 흰색 고정, 단추 보라 · 흰 글자), 실제 앱 미검증 |
| Apple 메일 · iOS 메일 | 밝음 · 다크 | 보임 · 막힘 | Chromium(대리, `prefers-color-scheme`) | 대리 통과, 실제 앱 미검증 |
| Gmail 웹 · Gmail Android · Outlook iOS | 밝음 · 다크 | 보임 · 막힘 | 미검증 | 실수신 캡처가 필요하다(사람이 할 일) |
| 평문 부분(모든 앱의 텍스트 보기) | - | - | 황금 파일 26종 | 머리 위 이름 → 제목 → 본문 → 사실 → 단추 주소 → 메모 → 바닥글 세 줄 |

## 남은 것

- 클래식 Outlook 검정 테마의 본문 다크 렌더: 테마를 바꿀 수 있는 PC(또는 사용자의 허락)에서 같은 스크립트로 잰다. 스크립트는 테마를 읽기만 한다.
- 실제 수신 화면(새 Outlook · OWA · Gmail 웹 · Gmail Android · Outlook iOS, 밝음 · 다크): 랩 배포 뒤 `lab_mail_e2e` 로 보내고 캡처한다.
- 작성 창이 아니라 받은 메일 읽기 창의 렌더: 같은 Word 엔진이라 같다고 보지만 받은 메일로는 아직 재지 않았다.

## 다시 재는 명령

```
.venv/Scripts/python.exe scripts/mail/export_mark.py                                  # 로고 PNG(BrandLogo.jsx 표식 → 72x72)
.venv/Scripts/python.exe -m scripts.ui_qa.mail_render_matrix --out dist/ui-qa/mail-templates/<ts>
pwsh -File scripts/ui_qa/outlook_render.ps1 -Source dist/ui-qa/mail-templates/<ts>/src -Kinds test,ticket_assigned,password_reset,notify_email_verification,account_locked
pwsh -File scripts/ui_qa/outlook_render.ps1 -Source dist/ui-qa/mail-templates/<ts>/src -Kinds test,ticket_assigned -NoImage -Out <같은 폴더>
.venv/Scripts/python.exe -m scripts.ui_qa.mail_e2e
```
