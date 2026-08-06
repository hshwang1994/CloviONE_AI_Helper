# scripts/ui_qa — 시각·기하 QA 하네스

React SPA(HashRouter)의 **모든 화면 × 라이트/다크 × 뷰포트 행렬**을 실제 서버에 로그인한
상태로 돌아다니며 스크린샷을 찍고, 레이아웃·콘솔·접근성 관련 검사를 수행한 뒤
오프라인에서 열리는 HTML 리포트를 만든다.

MUI 재설계 **전(PRE) 기준선**을 `--label pre` 로 찍어 두고, 재설계 **후(POST)** 를
`--label post` 로 찍어 같은 자리에서 비교하는 것이 기본 사용법이다.

모든 산출물은 `dist/` 아래에 쓴다(`dist/` 는 이미 gitignore 대상).

---

## 0. 준비 (한 번만)

```bash
# 의존성 (requirements-dev.txt 에 playwright / Pillow 가 들어 있다)
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m playwright install chromium

# 프런트엔드 번들이 최신인지 확인 (app/static/react/ 로 빌드된다)
cd frontend && npm run build && cd ..
```

## 1. 서버 띄우기

하네스는 **서버를 직접 띄우지 않는다.** 반드시 먼저 실행해 둔다.

```bash
.venv/Scripts/python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080
```

`--base-url` 의 `/readyz` 가 200이 아니면 하네스는 즉시 **종료 코드 2** 로 멈춘다.
(서버에 못 닿을 때 `page.set_content()` 같은 가짜 렌더로 조용히 우회하지 않는다 —
그런 하네스는 아무것도 검증하지 못한다.)

## 2. 실행

```bash
# 전체 화면 × 두 테마 × 전체 뷰포트 (오래 걸린다)
.venv/Scripts/python.exe -m scripts.ui_qa.run --label pre

# 빠른 확인: 대표 3화면 × 두 테마 × 대표 3뷰포트
.venv/Scripts/python.exe -m scripts.ui_qa.run --label pre \
    --routes smoke --viewports 1366x768 1920x1080 3840x2160

# 재설계 후 비교본
.venv/Scripts/python.exe -m scripts.ui_qa.run --label post

# CI 게이트: 가로 스크롤·콘솔 오류가 나면 종료 코드 1
.venv/Scripts/python.exe -m scripts.ui_qa.run --label ci \
    --fail-on horizontal_overflow,console_errors,page_errors
```

리포트를 다시 만들기만 할 때:

```bash
.venv/Scripts/python.exe -m scripts.ui_qa.report --label pre
```

## 3. 산출물

```
dist/ui-qa/
├── storage_state.json          로그인 세션(라벨 간 공유, 만료되면 자동 재로그인)
├── session.json                계정 id/role (테마 localStorage 키에 필요)
├── credentials.json            자동 생성된 QA 계정 비밀번호
└── <label>/
    ├── results.json            전체 결과(기계 판독용) — 항상 쓴다
    ├── report.html             오프라인 리포트(더블클릭으로 열림)
    ├── light/<viewport>/<route>.png
    └── dark/<viewport>/<route>.png
```

---

## 옵션

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--base-url` | `http://127.0.0.1:8080` | 검사 대상 서버 |
| `--label` | `baseline` | `dist/ui-qa/<label>/` 에 저장 (`pre` / `post`) |
| `--routes` | 전체 | 라우트 id, 해시 경로, 또는 `all` / `smoke` / `user` / `admin` / `detail` |
| `--viewports` | 전체 8종 | 아래 표의 이름 |
| `--themes` | `light dark` | |
| `--fail-on` | 없음 | 치명 처리할 검사 항목(또는 `all`). 걸리면 종료 코드 1 |
| `--rebuild-auth` | off | 세션 캐시를 버리고 다시 로그인 |
| `--ignore-console` | 없음 | 콘솔 오류에서 제외할 정규식 |
| `--no-full-page` | off | 접힌 화면(뷰포트)만 캡처 |
| `--settle-ms` | 300 | 대기 후 추가 안정화 시간 |
| `--headed` | off | 브라우저를 눈으로 보며 실행 |
| `--list` | | 라우트 목록만 출력 |

라우트 목록: `.venv/Scripts/python.exe -m scripts.ui_qa.run --list`

### 뷰포트 행렬

`390x844`, `768x1024`, `1366x768`, `1920x1080`, `2560x1440`, `3072x1728`, `3840x2160`,
그리고 `1920x1080@2x` (deviceScaleFactor 2 — **4K 패널 + OS 200% 배율** 환경 재현,
실제 PNG 는 3840×2160 픽셀로 나온다).

---

## 검사 항목 (`--fail-on` 에 쓰는 이름)

| 이름 | 내용 |
|---|---|
| `auth_ok` | 화면이 실제로 그려졌는가(`/login` 으로 튕기지 않았는가) |
| `theme_applied` | `<html data-theme>` 가 강제한 테마와 일치하는가 |
| `horizontal_overflow` | `documentElement.scrollWidth <= clientWidth + 1` |
| `console_errors` | `console.error` / 리소스 로드 실패 |
| `page_errors` | 잡히지 않은 예외(`pageerror`) |
| `broken_images` | 로드 후 `naturalWidth === 0` 인 `<img>` |
| `duplicate_ids` | 같은 `id` 를 쓰는 요소가 둘 이상 |
| `tiny_text` | **폭 ≥ 2200 에서만** 12 CSS px 미만으로 그려진 텍스트 |
| `narrow_main` | **폭 ≥ 3840 에서만** 본문 열이 뷰포트의 60% 미만 |
| `vertical_text_collapse` | 여러 글자 텍스트가 약 2ch 미만 폭에 갇혀 세로로 무너진 경우 |

`tiny_text` / `narrow_main` 은 대상 폭이 아니면 `skip` 으로 집계된다(실패가 아니다).

`narrow_main` 은 클래스 이름에 의존하지 않는다. `#main-content` 안의 **보이는 모든
비-fixed 요소 박스를 합집합**한 폭(`usedWidth`)이 실제로 레이아웃이 차지한 가로 범위이며,
이 값으로 판정한다. `#main-content` 자체는 사이드바 옆을 꽉 채우므로 그것만 재면
"4K에서 양옆이 텅 빈다" 를 절대 잡지 못한다 — 폭을 좁히는 것은 그 **안쪽** 열의
`max-width` 이기 때문이다(구 셸은 `.c-content`, MUI 셸은 클래스 없는 `<Box>`).
`results.json` 에는 `usedWidth` / `contentWidth` / `mainWidth` 세 값이 모두 남는다.

---

## 동작 방식 (수정할 때 알아야 할 것)

### 라우트 목록 (`routes.py`)
`frontend/src/app/App.jsx` 의 `UserBody` / `AdminBody` `<Route>` 와
`frontend/src/screens/registry.js` 의 `REGISTRY` 키(16개, `"/" + key`)에서 **유도**했다.
추측한 목록이 아니며, 출처 파일과 심볼이 `routes.py` 상단 주석에 적혀 있다.
라우팅이 바뀌면 그 주석을 따라 다시 유도할 것.

사용자 콘솔은 `/`, 관리자 콘솔은 `/admin` 셸에서 열린다
(`http://127.0.0.1:8080/#/my-tickets`, `http://127.0.0.1:8080/admin#/dashboard`).

### 세션 (`auth.py`)
1. `dist/ui-qa/storage_state.json` 이 아직 `/api/me` 200 이면 그대로 재사용한다.
2. 아니면 **실제 `/login` 폼**을 채워 로그인한다.
3. 계정이 없으면 프로젝트 CLI(`python -m app.cli.user_cli add`)로 만든다 — DB 를 직접
   건드리지 않는다. 이 CLI 는 항상 `must_change_password=True` 로 만들기 때문에,
   하네스가 이어서 **실제 `/change-password` 화면**을 통과해 고정 비밀번호를 만든다.

기본 계정은 `ui-qa@goodmit.co.kr` / role `system_admin`
(모든 `RequireRole` 게이트를 통과하고 `/admin` 셸에서 튕기지 않기 위함).
`UI_QA_EMAIL` / `UI_QA_PASSWORD` / `UI_QA_ROLE` 환경변수로 덮어쓸 수 있다.

### 테마 강제 (`capture.py`)
`App.jsx` 는 모듈 로드 시점에 `localStorage["clovirone_theme"]` 로 테마를 적용하고,
로그인 이후 `UserMenu` 가 **계정별 키** `clovirone_theme:<userId>` 가 있으면 그것으로
덮어쓴다. 그래서 두 키를 **모두** `context.add_init_script` 로 심는다(번들 첫 줄보다 먼저).
심어 놓고 믿는 게 아니라, 로드 후 `<html data-theme>` 를 실제로 읽어
`theme_applied` 로 확인한다.

### 전체 화면 캡처
`.c-app` 은 뷰포트에 고정되고 `#main-content` 가 내부 스크롤을 갖는 앱 셸 레이아웃이라,
`full_page=True` 만으로는 **첫 화면(접힌 부분)** 밖에 안 찍힌다. 그래서 검사(assertion)를
**정규 뷰포트에서 먼저 측정한 뒤**, 내부 스크롤 양만큼 **뷰포트 높이를 키워** 다시 찍는다
(CSS 를 조작하지 않는다 — 반응형 레이아웃이 스스로 늘어나게 둔다). 최대 8000px 에서 멈춘다.

### 번들 지문 (PRE/POST 비교의 전제)
`npm run build` 는 `app/static/react/` 를 **덮어쓴다**. 실행 도중 누가 다시 빌드하면
결과물이 두 빌드의 뒤섞임이 되어 기준선으로 쓸 수 없다. 그래서 매 실행이 시작·종료 시점에
`app/static/react/index.html` 의 해시와 자산 이름을 기록하고(`results.json` 의
`run.build_before` / `run.build_after`, 리포트 헤더에도 표시), 둘이 다르면 경고를
`notes` 맨 앞에 넣는다. **리포트에 이 경고가 보이면 그 결과는 버리고 다시 돌려야 한다.**

### 상세 화면
- 사용자 콘솔 상세(`/tickets/:id`, `/board/:id`, `/team-docs/:id`, `/games/:id`,
  `/chat-rooms/:id`)는 목록 API 의 첫 항목 id 로 해석한다.
- 관리자 콘솔 상세는 `registry.js` 의 `onQuery` / `OBJ_ID_PARAM` 계약대로
  `#/integrations?id=…`, `#/runners?id=…`, `#/jobs?job_id=…` 쿼리 딥링크로 드로어를 연다.

데이터가 없거나 API 가 실패하면 그 라우트는 **건너뛰고**, 이유를 `results.json` 의
`notes` 와 리포트 하단 "실행 메모" 에 남긴다. 커버리지를 지어내지 않는다.

---

## 알려진 제약

- **Notion 미구성**: 티켓 화면(`/my-tickets`, `/unassigned`, `/team-tickets`,
  `/tickets/:id`)과 개발자 월간 리포트는 Notion 토큰(`var/secrets/notion_report_token`)이
  있어야 실제 데이터가 나온다. 없으면 화면은 "연동 필요" 안내를 그리고,
  `/tickets/:id` 상세는 id 를 못 찾아 건너뛴다.
- **DB 마이그레이션**: `var/web.sqlite3` 가 `alembic head` 보다 뒤처져 있으면
  자유게시판·문서·놀이·채팅방 API 가 500 을 내고 해당 화면이 오류 상태로 찍힌다.
  `.venv/Scripts/python.exe -m alembic upgrade head` 로 맞춘 뒤 다시 돌릴 것.
- 스크린샷 용량이 크다(4K 전체 화면 캡처 기준 장당 수 MB). 전체 행렬을 한 번에 돌리면
  수 GB 가 된다 — 필요한 뷰포트만 골라 쓰는 편이 낫다.

---

## 기준 대조 (`baseline.py`)

### 왜 있나

디자인 기준(`design/baseline/preview-standalone.html`)이 있는데 CSS 토큰만 값으로 대조하고
"이미 일치한다"고 결론 내린 적이 있다. **토큰이 같은 것과 화면이 같은 것은 다른 얘기였다.**
그래서 규칙을 도구로 만들었다 — **화면 작업의 완료 판정은 이 시트로 한다.**

```bash
.venv/Scripts/python.exe -m scripts.ui_qa.baseline --out dist/baseline --shots
.venv/Scripts/python.exe -m scripts.ui_qa.baseline --routes home,my-tickets --out dist/baseline
```

앱이 `http://127.0.0.1:8080` 에 떠 있어야 한다(`--base-url` 로 바꿀 수 있다).

### 기준 목업 들여오기

원본은 `.bak` 폴더의 **16.3MB 단일 HTML** 이었다 — 저장소 밖이라 CI 가 못 읽고, 크기 때문에
열어 볼 수도 없었다. 그런데 **99%가 임베드 이미지 19개**이고 실제 마크업+CSS+JS 는 150KB 다.
data URI 를 `design/baseline/assets/` 로 뽑아내 HTML 을 150KB 로 줄여 저장소에 넣었다.
목업은 `#/<route>` 해시로 구동된다(`initialRoute = window.__QA_ROUTE || location.hash …`).

### 무엇을 재고, 무엇을 안 재는가

**픽셀 diff 는 쓰지 않는다.** 기준은 목업이고 우리는 실제 데이터가 든 앱이라, 글자 수도 행 수도
다르다. 픽셀 비교는 100% 실패하거나 임계값을 아무렇게나 잡게 된다. 대신 사람이 "다르다"고
말할 때 실제로 가리키는 것을 잰다: 뼈대(상단바/사이드바/본문 폭·격자 열 수) · 카드(개수·반지름
종류 수·그림자 비율·높이 편차) · 색(배경/글자/강조) · 타이포(제목·본문 크기, 글꼴) ·
컨트롤(버튼 높이·반지름, 입력 높이) · 밀도(카드 간격, 본문 여백).

**합격 기준 = 허용 오차 안**: 반지름 2px · 색 채널 12/255 · 폭 비율 5% · 글자 1.5px ·
간격 6px · 높이 4px. 이 값은 `baseline.py` 의 `TOLERANCE` 한 곳에만 있다.

예외 두 가지:
- **카드 반지름 종류 수**는 "우리가 기준보다 많으면 실패" 다. 한 화면에 반지름이 여러 종류
  섞여 있다는 뜻이라 오차로 볼 수 없다.
- **카드 높이 편차**는 기준의 1.5배 또는 120px 중 큰 값까지 허용한다. 실제 데이터가 들어가면
  카드가 조금씩 길어지는 것은 정상이다.

### 기준과 일부러 다르게 한 것

`INTENTIONAL` 딕셔너리에 **이유와 함께** 적는다. 기준은 하한선이지 상한선이 아니다.
이유를 한 줄로 못 쓰면 의도가 아니라 결함이니 여기 넣지 말고 고쳐야 한다.
시트는 이것들을 별도 절로 분리해 보여 준다 — 안 그러면 시트가 영원히 빨갛고 아무도 안 본다.

### 프로브를 고칠 때 주의

기준과 우리 앱에 **같은 스크립트**를 돌린다. 서로 다른 프로브를 쓰면 비교가 아니라 두 개의
측정이 된다. 그리고 측정값이 화면마다 똑같이 나오면 **프로브를 의심해야 한다** — 실제로
`.MuiPaper-root` 를 그냥 세다가 상단바·서랍까지 잡아 네 화면 전부 "높이 편차 1031" 이
나온 적이 있다. 강조색을 CSS 변수에서 읽다가 `#536CD6` 을 `[536, 6]` 으로 파싱한 적도 있다.
