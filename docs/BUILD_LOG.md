# Build Log

세션 간 인수인계 기록(HISTORY). 최신 항목이 위.

> **현재 상태는 여기서 찾지 마라.** 지금 어디까지 왔는지는 [WORK_STATE.md](WORK_STATE.md),
> 남은 문제는 [BACKLOG.md](BACKLOG.md), 검증 공백은 [QA_COVERAGE.md](QA_COVERAGE.md).
> 이 문서는 "무엇을 했는가"의 누적 이력이다. Raw log를 복사해 비대하게 만들지 않는다.

## 2026-08-09 (Sonnet 구현 사이클 1) — 배포 경로 복구 (`SONNET_HANDOFF.md §3` 1단계)

**무엇을 했나**: Opus 인계 문서의 1단계(배포 경로 복구)부터 착수. 그 이후 모든 사이클의
"배포 후 재검증"이 여기 의존하므로 먼저 끝내지 않으면 아무것도 실환경 검증할 수 없었다.

**고친 것**: `DEPLOY-01`/`DEPLOY-02`(`upgrade-clovirone-web-assistant.sh` 번들 경로가
`DNS_NAME`/`BIND_IP` 를 안 넘겨 installer 가 즉시 죽는데 서비스는 이미 정지된 채 복구
코드가 없었다 — `update-from-git.sh` 의 backup→install→verify→`rollback_now()` 골격을
이식) · `UX-50`/H-2(`StructuredObjectFields.jsx` 의 `fmtDuration` import 누락으로
`/settings` 세션 정책 편집기가 크래시) — 무료 동승으로 같이 배포.

**배포 절차를 실제로 따라가다가 문서·스크립트 버그를 2개 더 찾았다(둘 다 새 발견)**:
`DEPLOY-03`(installer 주석이 "여기서 멈추면 아무것도 안 바꿨다"고 하는데 이미 rsync·venv가
끝난 뒤였다 — 주석 정정) · `DEPLOY-04`(롤백이 특권 헬퍼(privhelper) 유닛을 안 되살려
`ROLLBACK_OK` 가 찍혀도 시스템 설정 화면이 죽어 있었다 — 백업·롤백에 추가). 그리고
`MAINTENANCE_PLAYBOOK.md §2-3` 의 스테이징 명령 자체가 (a) 체크섬 파일을 압축 풀기 전에
없는 경로에서 확인하려 했고 (b) `-C stage` 로 풀어 tar 내부의 `stage/` 접두사와 겹쳐
`~/deploy/stage/stage/app-src` 로 이중 중첩됐다 — 둘 다 실제로 그 명령을 그대로 실행해서
발견했고 고쳤다.

**실서버 검증**: 정상 배포 1회(`UPGRADE_OK`) + 스테이징 사본을 고의로 깨서(`requirements.txt`
제거) 재배포해 install 실패 유도 → `rollback_now` 가 백업을 복원 → `UPGRADE_ROLLED_BACK` →
`systemctl is-active clovirone-web-assistant clovirone-web-worker clovirone-privhelper` 3종
전부 active + `healthz`/`readyz` 200. **두 번** 재현해 DEPLOY-04 수정 전/후를 비교했다(백업
스크립트 자체가 새 코드에서만 privhelper 를 담으므로 최초 1회는 담기지 않는 것까지 확인).
Chrome 으로 `/settings` → 「세션 정책」 상세를 직접 열어 크래시 없이 `= 680분`/`= 8시간`
렌더 확인(콘솔 오류 0).

**게이트**: pytest 루트 전체 green · 러너 263개 green · vitest 173파일/1213개 green(신규
회귀 테스트 3개 추가) · `STATIC_CHECKS_OK`.

**다음**: `SONNET_HANDOFF.md §3` 2~4단계 — `SYS-01`(TLS 무동작) · `SEC-30`(CSV 권한 상승
우회) · `FN-40`(공지 PATCH 500) · `OPS-10`/`OPS-11`(워커 내구성).

## 2026-08-08 (사이클 0) — 지속 작업 기억 구축 + Opus 전수조사

**무엇을 했나**: 작업 상태를 대화에서 프로젝트 파일로 옮기고, 서버를 HEAD로 올린 뒤,
아무도 본 적 없던 영역을 전수조사하고, 배포된 실물을 열어 눈으로 판독했다.

**문서 재편** — `docs/`에 이미 34개가 있어 역할이 겹치는 것을 새로 만들지 않고 배정했다.
`WORK_PLAN_INDEX.md`(MASTER PLAN, 전면 개정)와 이 파일(HISTORY)은 재사용, `WORK_STATE.md`·
`BACKLOG.md`·`QA_COVERAGE.md`·`DECISIONS.md`는 신규. `CLAUDE.md`는 덮어쓰지 않고 §0(진입점)과
§9 색인만 추가. `NEXT_SESSION_PLAN.md`는 포인터로 축소.

**게이트를 전부 통과시키고 배포했다** — `STATIC_CHECKS_OK` · `REHEARSAL_OK` ·
**pytest exit 0(HEAD에서 완주한 것이 이번이 처음이다 — 라운드 14가 두 번 중단됐다)** ·
vitest 172파일/1212테스트 · `UPGRADE_OK` → `DEPLOY_VERIFY_OK`. 서버가 라운드 9~14만큼
뒤처져 있었으므로, 그 상태로 조사하면 이미 고쳐진 버그를 다시 발견해 BACKLOG가 오염된다.

**막고 있던 것 2건을 고쳤다**
- `QA-07` 시간이 지나 **스스로 깨진** 프런트 테스트. 절대 날짜 픽스처 vs 상대 기준(`>7일`).
  작성 다음 날 깨져 `final_verify`를 막고 있었다. 픽스처를 상대값으로.
- `QA-09` **번들 무결성 검사가 모든 번들에서 항상 1건 실패**. `find`가 리다이렉트로 먼저 생긴
  빈 매니페스트를 자기 목록에 넣어 영원히 자기 자신과 불일치. 절차서가 이걸 배포 전 확인
  단계로 적어 뒀으니, 늘 실패하는 검사는 없는 검사보다 나쁘다. 회귀 테스트 3건으로 못박음.

**QA 하네스를 실제 서버에 겨눌 수 있게 했다** — `--insecure` 추가(SSH 터널은 안 된다:
`COOKIE_SECURE=true`라 Playwright API 클라이언트가 http로 세션 쿠키를 안 싣는다) ·
원격 강제 비밀번호 변경 처리 · 라우트 62→70(화면 약 2,600줄이 검사 밖에 있었다) ·
역할 계정 4개 생성(서버 실계정 14개 중 12개가 admin, **operator·auditor는 0명**이었다).

**조사 결과 — BACKLOG 292건**(대부분 신규):
- **러너 20건, 라우터를 실제 실행해 재현**: `"그거 완료했어?"`라는 **질문이** 티켓을 완료로
  바꾸고, `"완료로 바꾸지 마"`라는 **거절이** 완료로 바꾸고, 선택 대기 중 `"그만할래"`가 쓰기를
  수행한다. 셋 다 가드는 있는데 **가드가 도달하지 않는 자리에** 있다.
- **`app/core/` 12건**(사상 최초 감사): 워커 리스를 두 프로세스가 동시에 잡을 수 있다 ·
  만료 세션의 `revoked_at`이 롤백돼 **절대 저장되지 않는다** · 500 응답이 보안 헤더와 접근
  로그를 통째로 건너뛴다.
- **미감사 19모듈 59건**: 전사 생산성 노출 · org 스코프 우회 · 백업이 도는 동안 전체 쓰기 잠김 ·
  부서 admin이 전사 배너 · 전역 AI 상한이 강제와 표시가 서로 다른 것을 셈 · 로그아웃이
  임퍼소네이션 기록을 영원히 "진행 중"으로 남김.
- **registry 28화면↔API 8건**: **구조적으로 절대 작동할 수 없는 버튼**(GET에 body를 실어
  `fetch`가 던진다) · 서버는 고쳤는데 화면이 안 받은 링크·필터.
- **실화면 판독 66건(11화면)**: 판독한 화면들은 **기계 검사 21종을 전부 통과했다.**
  대시보드 타일 21개가 전부 같은 카드라 "지금 조치할 일"과 "단순 재고"가 같은 무게 ·
  같은 숫자가 한 화면에 세 번 · 역할 배지에서 최고 권한이 **빨강(=위험)** · 온보딩 모달이
  홈을 덮은 채 캡처돼 **자동 QA가 홈을 한 번도 검사한 적이 없다** · `/sprint` 한 페이지가
  **11,558px**(페이지네이션 없음) · 4K에서 글자만 커지고 레이아웃 구성은 그대로.
- **4K 회귀 원인 확정**: `tiny_text` 134 fail의 범인이 정확히 두 줄 —
  `TopSearch.jsx:68`(11px «Ctrl K»)와 `Mascot.jsx:364`(10px «현재 화면을 기준으로 도와드려요»).
  둘 다 상단바·사이드바라 모든 SPA 화면에 있다.

**배포 서버에서 직접 재현한 것** — `qa-user`(role=user)로 로그인해:
`/api/assistant/weekly-digest` → 200, 전사 합계 + **이름 붙은 상위 기여자 5명**.
`/api/sprint/summary` → 200, **17명 전원의 완료율·지연·배정**. 같은 세션에서 관리자
엔드포인트는 전부 403이므로 **RBAC 뼈대는 건강하고 이 두 개에만 게이트가 없다.**
특히 `dev-monthly`는 같은 집계를 `SENSITIVE_READ`로 막는데 `weekly-digest`가 그 정책을 무효화한다.

**남은 것**: 판독 11/70 · `F`~`L` 축 대부분 미착수 · 역할별 캡처 미실행 ·
**조사는 수렴하지 않았다**(화면당 6건 속도 유지). 다음 작업은 `WORK_STATE.md` §3.

---

## 2026-08-08 — 코드레벨 감사 8~14라운드 (로컬 커밋 7개, **배포 전**)

`834cb51`~`7f2b1be` + `2ac14f5`. **198파일 / +7,878 / −465.** 이 이력이 오랫동안 이 문서에 없었고
커밋 본문에만 있었다 — 가장 최근이자 가장 침습적인 작업이었는데도 그랬다.

| 라운드 | 범위 | 실버그 |
|---|---|---|
| 8 `834cb51` | 전 페이지 코드레벨 감사(5클러스터 × 7라운드) | **35건(크래시 6건 포함)** |
| 9 `dc63246` | 댓글 작성자 신원표시 기능 + 기능 간 연결 | 7건 |
| 10 `266fe9a` | 댓글 초안 오염, 사다리 크래시, 티켓 카운트 은폐 | 4건 |
| 11 `b966468` | 백엔드 자동화 정책 위반 + 프런트 | 2 + 3건 |
| 12 `0a345e7` | 게임 동시성/유령우승, 백업 보존정책, 알림 누락 | 3 + 1 + 2건 |
| 13 `e13d366` | **미감사 모듈** auth/profiles/notion/mail/llm/setup 전수조사 | 16건 |
| 14 `7f2b1be` | **미감사 모듈** approvals/jobs/workflows/integrations/health/settings/sysops/search | 23건 |
| — `2ac14f5` | Notion 매핑 재동기화가 완료된 잡의 초 단위 멱등키와 충돌 | 1건 |

**이 라운드들이 스스로 남긴 미처리 항목**(전부 `BACKLOG.md`에 이관):
- 라운드 9: 승인 위임받은 운영자에게 버튼 없음 · "승인 대기" 배지가 개인 안읽음 수 ·
  워크플로 실행 이력을 `/jobs`에서 역추적 불가 · `Trash` 복구가 문서 캐시를 못 씻음
- 라운드 12: 토너먼트 개별전 제출 경합 잔존
- 라운드 13·14: 인증/세션/RBAC/scope 경계 항목은 **"원칙대로 수정하지 않고 리포트만"** —
  세션 만료 미필터링 · 아바타 조회 시 `active` 미확인 · 위임 취소 시 만료일 표시 오류 ·
  allowlist 캐시 staleness
- 라운드 8: `lib/people.js`·`lib/format.js` 중복 모듈 정리 미완

**⚠️ 라운드 14가 남긴 경고**: "전체 스위트 1회 실행은 환경 이벤트로 두 차례 중단되어 완주하지
못했다." → **전체 백엔드 스위트가 HEAD에서 완주된 적이 없다.** 사이클 0에서 처음 완주시킨다.

**❌ 배포 안 됨**: 이 7개 커밋 전부 로컬 기준. 서버는 여전히 그 이전 상태다(해시 비교로 확인).

---

## 2026-08-07 — 클로비 브랜드 이미지 63장 재생성본 교체 (로컬 커밋, 배포 전)

- 사용자가 GPT로 재생성한 클로비 마스코트/일러스트 세트를 `app/static/brand/`의 68개 슬롯(마스코트
  포즈 8+미사용정의 4, 원본 프레임 20/21·레이어 7, 빈상태·에러 일러스트 13, 온보딩 spot 8, 기타 3)에
  매핑해 교체. 원래 위치·파일명 그대로 덮어써 코드 변경 없음. `manifest.json` sha256·크기·해상도,
  `mascot-lock.json` 해시 4개를 실제 파일과 동기화.
- **로그인 히어로 4장(hero/eye-base/eyes-layer/avatar)은 변경 없음** — 새로 받은 파일이 기존과
  SHA-256까지 완전히 동일(재생성이 로그인 폴더까지는 반영 안 된 것으로 보임). 다시 받으면 같은
  절차로 교체 가능.
- `mascot/frames/wave-05.png`만 짝이 없어 원본 유지(67/68 매칭 성공). 매칭 시 사용자가 넘겨준
  `빈상태_에러화면` 폴더 전체에 윈도우 중복저장 흔적("(2)" 접미사)이 붙어있던 걸 정규식으로 자동 보정.
- **스타일 변화 확인**: 원본은 배경 없는 플랫 컷아웃인데 신규 마스코트 포즈·spot 일러스트 다수는
  은은한 비네트(광원) 배경 + 더 디테일한 장면 구성으로 바뀜. 알파 채널을 직접 그리드 샘플링해
  가장자리가 실제로 투명 처리된 것 확인(고정 회색 박스로 깨지는 건 아님) — 브랜드 톤 전환이 의도된
  것인지 사용자 확인 필요. `빈상태_에러화면` 11장은 원본과 동일한 플랫 스타일로 옴.
- **검증(✅)**: 프로덕션 경로에서 직접 재열람해 clovi-idle/state-404 신규 반영, wave-05.png 원본
  보존 확인. 이 경로를 참조하는 테스트 전부(`test_login_visual_contract.py`+`test_favicon_wiring.py`
  30개) 통과, `pytest -m regression` 전체도 green(exit 0) — 단 이 테스트들은 HTML 배선·해시 필드만
  보고 마스코트 그림 내용 자체(픽셀)는 검증하지 않음.
- **⚠️ 미확인**: 실제 브라우저 렌더(로그인 이후 화면에서 마스코트/빈상태 카드가 실제로 어떻게
  보이는지)는 로그인 필요로 육안 미확인.
- **❌ 배포 안 됨**: 이 커밋은 로컬 워킹 트리 기준. 프로덕션(`clovirone-ai.gooddi.lab`, `10.100.64.71`)엔
  아직 안 올라감 — `MAINTENANCE_PLAYBOOK.md §1`(정적 파일 핫 업데이트: 재시작 불필요,
  `stage-static-update.sh` → scp → 서버에서 sudo는 사용자 직접 → 해시 대조 검증) 그대로 적용하면 됨.
- 백업 없이 직접 덮어씀(사용자 명시 지시) — 전부 git 추적 대상이라 되돌리려면 이 커밋 이전으로 revert.

## 2026-07-29 — 새 티켓 설명 = 문서 본문식 리치 에디터 (배포 완료)

- 새 티켓(내 업무 > 새 티켓)의 '설명'을 문서 본문과 똑같은 편집 경험으로. 서식 도구(제목/글머리/
  번호/구분선/이모지) + 라이브 미리보기 + 넓은 입력칸(rows 4 → 12).
- 공용화: 프런트 `ui/BodyEditor.jsx`(툴바+textarea+미리보기)를 TeamDocs 새 문서와 NewTicket이 공유.
  백엔드 `app/core/notion_blocks.py:markdown_to_blocks`를 team_docs `body_children`와 tickets 설명이 공유 —
  전엔 티켓 설명이 통짜 문단 1개였는데 이제 제목/목록/구분선이 실제 Notion 블록으로 저장된다(설명 4000자 한도).
- 검증(✅): 백엔드 pytest 752 passed(티켓 마크다운→블록 테스트 추가), vitest 90/90, STATIC_CHECKS_OK, build.
  라이브: healthz 200, tickets 무손상, 새 번들 index.S1zNSbuu.js 서빙.
- 부가: 사용자 피드백대로 UI/내 답변에서 가운뎃점 기호 제거, 페이지 도움말 한 줄로 단축(별도 정적 배포).
  참고: 부서/직책/Notion 연결은 이미 구현돼 있음(관리자 콘솔 '사용자' 그룹). 실제로 12/15명 부서 연결됨,
  직책은 등록 5개인데 배정 0명이라 미구현처럼 보였을 뿐.

## 2026-07-29 — UX 배치: 배지색·문서서식·게임 애니메이션·홈 대시보드 (배포 완료)

- **카테고리/문서종류 배지 색**: 값별로 다른 색. tokens.css에 장식용 4색(purple/teal/pink/indigo,
  라이트/다크 대비 확보) + kit.css .k-badge--*. lib/badges.js가 게시판 5카테고리(공지=danger 등)·
  문서 8종류를 각각 다른 kind로 매핑(미정의=neutral). 목록·상세 양쪽 적용.
- **새 문서 본문 서식 UX**: 도구가 이제 '줄 맨 앞'에 표식(##/-/1.)을 붙이고(단어 중간 X), 구분선은
  자기 줄에. **라이브 미리보기(DocBodyPreview)** 추가 — body_children와 같게 렌더(빈 줄=간격,
  100줄 상한·초과 경고). caret 0 엣지 가드.
- **게임 애니메이션**: 가위바위보 손 이모지(✌️✊✋) 흔들기→공개, 승자 pop/glow, 숫자 카드 플립,
  팀/사다리/점수 순차 등장. **기본 ON**(동작 최소화를 직접 켠 사용자만 OFF — 이전엔 no-preference로
  감싸 오해 소지, 반전 수정). 승자 공개 시 **canvas-confetti 축포**(npm 빌드타임 의존, 캔버스 CSSOM·
  워커 미사용이라 CSP 안전; 무승부·팀/사다리 등 '승자 없음'은 제외). 인라인 스타일 없이 nth-child 지연.
- **내 업무 홈 대시보드**: `GET /api/board/mine`(list_by_author/author_stats — 내 글·받은 댓글[남이 단 것]·
  조회 집계, 삭제 제외) + MyTickets.jsx BoardActivity 위젯(게시판 꺼지면 조용히 숨김).
- **적대적 검수(3관점→검증)**: 확정 4건 모두 반영 — 미리보기 100줄 상한·빈줄 간격 일치, prefixLine
  caret0 가드, comment_count_received에서 본인 댓글 제외.
- **검증(✅)**: 백엔드 pytest exit 0, board 16, vitest 90/90, STATIC_CHECKS_OK, build(confetti 번들).
  라이브: healthz 200, `/api/board/mine` 401, 새 번들 index.CLfiyPk4.js 서빙·참조, chat 401·worker 무손상.
- **⚠️ 미확인**: 브라우저 시각(배지색·미리보기·애니메이션·축포·홈 위젯)은 로그인 필요로 눈 확인 못 함.

## 2026-07-29 — Phase 6: 게임 AI 퀴즈 생성 (다크런치 배포 완료)

- **아키텍처(안전 우선)**: 앱 `POST /api/games/quiz/generate` → `app/games/ai.py`(games의 유일한
  외부 호출, service.py는 외부 호출 없음) → **OutboundClient(allowlist=runners, bearer secret_ref)**로
  러너의 **전용 신규 엔드포인트 `POST /v1/assistant/quiz`** 직접 호출(로컬 127.0.0.1:8789). n8n은
  전혀 안 거친다(프로덕션 n8n 무접촉). 러너는 `route_request`(티켓/채팅 라우팅)를 **건드리지 않는**
  분리된 엔드포인트라 기존 동작 무영향. 러너가 Claude CLI로 생성 → `_sanitize_quiz`(정답 텍스트→
  인덱스, 정답이 보기에 없으면 드롭) → 앱이 다시 `_clean_questions`로 검증(§11 이중 검증).
- **다크런치**: `game_ai_enabled` 플래그 **fail-closed 기본 OFF**(_DEFAULTS+config json). 런타임
  `/etc/.../feature-flags.json`엔 키가 없어 코드 기본값 False로 실효. 러너 토큰 secret도 켤 때까지 부재.
- **안전장치**: CSRF + 로그인 + per-user rate limit(game_ai_ratelimiter, 5버스트/~5분). 러너 토큰은
  secret_ref로만(로그·응답·DB 미노출). QuizGenerateError는 민감정보 없이 '다시 시도/직접 입력' 안내.
- **검수(적대적 워크플로 4관점→검증)**: 확정 결함 1건 — 퀴즈가 티켓/채팅의 180s deadline을 써서
  앱이 50s에 포기해도 러너가 공용 세마포어 permit(2개, 티켓 자동화와 공유)을 ~130s 더 쥐어
  프로덕션 429 유발 가능. **수정**: `QUIZ_TIMEOUT_SECONDS=45`(앱 50s·nginx 60s보다 짧게) 전용 예산.
- **검증(✅)**: 앱 pytest **750 passed**(+AI 3), 러너 **263 passed**(+quiz 4, 수정 후 재확인), vitest 90/90,
  STATIC_CHECKS_OK(OutboundClient 경유 확인), build. 라이브: 앱 healthz 200·`/quiz/generate` 라우트
  존재(401)·flag 실효 False·회귀 무손상; 러너 v3.57.0 health gate 통과·`/v1/assistant/quiz` 라우트 존재
  (401, unknown은 404)·`/message` 무손상·8787/8788/8789 전부 active·backup+auto-rollback.
- **⚠️ 켜기 전 사용자 조치(라이브 LLM 경로는 미검증 — 비용·프로덕션이라 다크로 둠)**:
  ① `/etc/clovirone-web-assistant/feature-flags.json`에 `"game_ai_enabled": true` 추가(root).
  ② 러너의 `RUNNER_TOKEN` 값을 `/etc/clovirone-web-assistant/secrets/game_runner_token` 파일로 저장
  (0640 root:clovirone-web). 두 조치 후 놀이>실시간 퀴즈 생성 모달에 'AI로 문제 생성'이 뜬다.
- 롤백: 러너 `assistant.py.bak-20260729_004813`, 앱은 표준 rollback 스크립트. 끄기=플래그 false.

## 2026-07-28 — 놀이 게임 확장: 실시간 퀴즈 (배포 완료)

- **실시간 퀴즈(quiz)**: 방장이 문제(지문+보기 2~6+정답)를 미리 넣고, 다라운드 상태기계로 진행.
  phase=answering(참여자 몰래 응답, 남의 답·정답 비공개) → revealed(방장이 정답 공개, 서버가 채점·
  누적) → next(다음 라운드 or 종료 시 누적 점수판 확정). 정답/채점은 서버만(§13.1). config.questions는
  RoomCreate `_clean_questions`로 구조·범위 강제(최대 20문항). 신규 엔드포인트 `POST .../quiz-answer`·
  `/reveal`·`/next`. `public_state`가 phase별로 노출 범위를 조절(answering엔 정답 숨김).
- 프런트: 생성 모달에 `QuizEditor`(문제/보기/정답 라디오 추가·삭제), GameRoom에 라운드 표시·응답
  버튼·정답 하이라이트·실시간 점수판·최종 순위 무대 + 방장 '정답 공개'/'다음 문제' 컨트롤.
- 검증(✅): 백엔드 **747 passed**, 게임 19 tests(라운드 채점·답 은닉·phase 가드 포함), vitest 90/90,
  STATIC_CHECKS_OK, build. 라이브: `/quiz-answer`·`/reveal` 401, 새 번들 서빙, chat 401·worker·n8n 무손상.
- **게임 7종 라이브**: 랜덤 추첨 · 빠른 투표 · 랜덤 팀 나누기 · 숫자 눈치 · 사다리타기 · 가위바위보 ·
  실시간 퀴즈. 스펙 8종 카테고리를 사실상 커버(월드컵 토너먼트 브래킷·Notion 기반 퀴즈만 미구현).
  **남음**: Phase 6 게임 AI 생성(n8n 워크플로 + 러너 액션 + 검토 UI) — 다중 시스템 통합이라 규모 큼.

## 2026-07-28 — 놀이 게임 확장: 가위바위보 (배포 완료)

- **가위바위보(rps)**: 참여자가 몰래 가위(0)/바위(1)/보(2)를 내고(진행 중 `public_state`가 은닉),
  방장이 공개하면 서버 판정 — 정확히 두 종류만 나오면 이기는 쪽 승리, 아니면 무승부. 신규
  `POST /rooms/{id}/rps`(VoteInput 재사용). `finish_game`/`public_state`에 rps 분기 추가.
- 검증(✅): 백엔드 **745 passed**, 게임 17 tests(2종류판정·전원동일 무승부 포함), vitest 90/90,
  STATIC_CHECKS_OK, build. 라이브: healthz 200, `/rps` 401, 새 번들 서빙, chat 401·worker·n8n 무손상.
- **게임 6종 라이브**: 랜덤 추첨 · 빠른 투표 · 랜덤 팀 나누기 · 숫자 눈치 · 사다리타기 · 가위바위보.
  남은 스펙 게임(실시간 퀴즈·밸런스·가위바위보 토너먼트 등)과 Phase 6(게임 AI 생성)은 미착수.

## 2026-07-28 — 놀이 게임 확장: 숫자 눈치 + 사다리타기 (배포 완료)

- **숫자 눈치(number)**: 참여자가 몰래 숫자를 내고(진행 중엔 `service.public_state`가 남의 선택을
  감춰 제출수/내 선택만 노출) 방장이 종료하면 서버가 공개해 '가장 낮은 유일 숫자'를 확정. 신규
  `POST /rooms/{id}/pick`(NumberInput). `finish_game`을 게임별 디스패처로 리팩터(`_finish_vote`/`_finish_number`).
- **사다리타기(ladder)**: team_split처럼 방장 시작 즉시 확정. config.options(결과 목록)를 셔플해
  참여자에 1:1 배정(부족하면 '꽝' 채움). 새 엔드포인트·마이그레이션 없음.
- 프런트: 생성 모달에 두 게임 추가(숫자 범위 / 결과 목록=vote 선택지 UI 재사용), GameRoom에 숫자
  입력·제출·집계 공개 무대와 사다리 배정 목록 무대. 게임 5종 라이브.
- **검증(✅)**: 전체 백엔드 pytest **743 passed**, 게임 15 tests, vitest 90/90, STATIC_CHECKS_OK, build.
  라이브: healthz 200, `/pick` 401(라우트 활성), 새 번들 서빙·참조, worker·n8n active.
- **⚠️ 미확인**: 브라우저 시각(숫자 은닉→공개, 사다리 배정 렌더)은 로그인 필요로 미확인.

## 2026-07-28 — 놀이 team_split + 사용자 피드백 배치 (배포 완료)

- **랜덤 팀 나누기(team_split)**: 세 번째 게임. random_draw처럼 방장 시작 즉시 서버가
  `secrets.SystemRandom().shuffle` + 라운드로빈으로 N개 팀 균등 분배·확정. 새 엔드포인트·마이그레이션
  없음(config.teams). 테스트 `test_team_split_server_partitions_evenly`. 게임 총 12 tests.
- **사용자 피드백 배치**(한 번에 배포):
  - **문서 탭 분리**: USER_NAV에서 문서를 팀 공간 밖 독립 그룹 '문서'로. 팀 공간=놀이+자유게시판.
    NAV_ICONS['문서'] 추가. 문서 화면 crumbRoot 정리.
  - **문서 필터 상태 유지**(TeamDocs): 필터/검색/정렬/페이지를 URL 쿼리에 저장(useSearchParams,
    replace). 상세 보고 뒤로 오면 복원. 첫 렌더 page-reset 스킵(useRef 가드) + useDebounced 초기값=URL.
  - **놀이 2버튼 버그**: 빈 목록에서 헤더+EmptyState 중복 '게임방 만들기' → EmptyState 액션 제거.
    게시판도 동일 정리. 두 페이지에 k-page-help 설명 추가(비어보임 완화).
  - **새 문서 모달**: 본문 textarea 확대(rows14, min-height 260, resize) + 서식 도구(제목/글머리/번호/
    구분선/이모지 커서 삽입). 백엔드 `body_children`가 가벼운 마크다운(`##`/`-`/`1.`/`---`)을 Notion
    블록으로 변환. 모달 자체 스크롤은 kit `.k-modal-body`(overflow-y auto, max-height 88vh)가 이미 담당.
  - **AI 도우미 채팅 너비**: `--chat-content-max` 1000→1200px.
  - **문서 프로젝트/필수/작성자**: 새 문서 프로젝트 선택지=Notion 전체 프로젝트(신규
    `GET /api/team-docs/projects` + `notion_docs.list_all_project_names`, 실패 시 캐시 폴백). 제목·문서
    종류·업무 분야 **필수**(schemas `validate_default=True` + 검증기). 수동 '소유자' 입력 제거 → 작성자
    자동(로그인 사용자, 기존 배관). 검색 플레이스홀더 '소유자'→'작성자'(search는 owner+author 둘 다).
- **검증(✅)**: 전체 백엔드 pytest **740 passed**(동시 빌드 레이스로 index.html 순간 부재 1건은
  단독 재실행에서 소멸), 문서 28 tests, vitest 90/90, STATIC_CHECKS_OK, vite build. 라이브: healthz 200,
  `/api/team-docs/projects` 404→401(라우트 활성), 새 번들 index.beKelqS9.js 200·index.html 참조,
  /api/conversations 401(무손상), worker active.
- **⚠️ 미확인**: 브라우저 시각/상호작용(탭 분리 표시·필터 복원·모달 서식 삽입·채팅 폭·team_split 팀
  렌더)은 로그인 필요로 미확인(비번 직접 입력 불가). API/빌드/테스트 레벨만 확인.

## 2026-07-28 — 팀 공간 > 놀이(게임) Phase 4·5 (배포 완료)

- **신규 모듈 `app/games/`** (router/service/repository/schemas/models) — 폴링 기반 **서버 확정·
  이벤트 시퀀스** 게임방 인프라. 불변 §1(sync) 유지: WebSocket 없이 `GET /api/games/rooms/{id}/state?since=<seq>`
  폴링. 방/멤버/이벤트 3테이블(마이그레이션 **0019**). 이벤트는 방별 순번(event_seq)으로 append-only,
  유니크(room_id,seq) 위반은 SAVEPOINT로 흡수·재시도.
- **게임 종류는 config/state_json + service 분기로 확장**(테이블 추가 없음):
  - **random_draw**(Phase 4): 방장 시작 → `secrets.SystemRandom().sample`로 당첨자 서버 확정.
  - **quick_vote**(Phase 5): 방장이 선택지 열기(start→playing) → 참여자 투표(`/vote`, 재투표=덮어쓰기,
    관전자 불가) → 방장 종료(`/finish`) → 서버가 집계·당첨 선택지 확정(동점=공동). 마이그레이션 불필요.
- **프런트**: `screens/Games.jsx`(방 목록 3초 폴링 + 게임 종류별 생성 모달) · `screens/GameRoom.jsx`
  (1.2초 폴링, 자동 입장, 참여자·채팅·추첨/투표 UI). `App.jsx` 팀 공간 그룹에 **놀이** 추가
  (`/games`, `/games/:id`, USER_SEG_PATHS). CSP 준수(textContent). 게임방 채팅은 **순수 내부 DB**
  (n8n/Notion/Claude 안 거침, §13.2).
- **기능 플래그** `games_enabled`(config/feature-flags.json + feature_flags.py `_DEFAULTS`, 기본 true).
  서버 feature-flags.json은 installer가 보존하므로 값은 코드 기본값 True로 실효.
- **테스트**: `tests/integration/test_games_api.py` 11개(생성/목록/입장/준비/폴링/랜덤추첨 서버확정/
  방장전용시작/채팅·리셋/관전/방장위임/기능플래그OFF + quick_vote 집계·재투표·관전자차단).
- **검증(✅ 확인함)**: 배포 전 전체 백엔드 pytest `exit 0`, vitest `90/90`, `STATIC_CHECKS_OK`, vite build.
  라이브(10.100.64.71): 배포 후 `alembic head=0019`, game_* 테이블 3종 생성 확인, `/api/games/rooms`
  404→401(플래그 실효 True), `/vote`·`/finish` 401(라우트 존재), 새 번들 200, index.html이 새 번들 참조.
  기존 무손상: healthz 200 · /api/me 401 · worker active · n8n active · 배포 전 백업 생성.
- **⚠️ 미확인**: 실제 로그인 브라우저 end-to-end(방 생성→추첨/투표→결과 렌더→폴링→채팅)는 눈으로
  확인 못 함(로그인 필드 비번 직접 입력 불가 — 안전 규칙). 사용자 30초 확인: 팀 공간>놀이.
- **다음**: Phase 5 나머지 게임(점심정하기·팀나누기·실시간퀴즈·밸런스·가위바위보·숫자눈치·사다리),
  Phase 6 게임 AI 생성(n8n+러너). 엔진(제출→서버집계→확정)은 quick_vote로 검증됨.

## 2026-07-14 — 세션 1

- 계획 승인: `~/.claude/plans/c-users-hshwa-downloads-clovirone-web-as-indexed-quokka.md`
- 스펙: `~/Downloads/ClovirONE_Web_Assistant_Final_Claude_Instructions.md` (v2.0)
- 사용자 결정: ① SSH 키+임시 NOPASSWD ② 서버 인터넷 됨(wheelhouse는 항상 번들)
  ③ ClovirONE 로고 사용
- 사전 실측: 서버 22 포트 도달 OK, 키 인증 미등록(D0 대기), DNS 정상, 로컬 py3.11.9
- M0 진행: 저장소 스켈레톤, core(config/db/models_base/clock/errors/middleware/pagination),
  app factory, health 라우터, alembic 베이스라인, config allowlist JSON 4종,
  tokens.css(§24.1 팔레트+다크), 로고 3종 static/img, pytest 하니스+테스트 5파일
- M0 완료(커밋 573201d, 18 tests) → M1 완료(1b98739, 67 tests): Argon2id 로그인/로그아웃/
  비밀번호변경, opaque 세션(idle/절대 타임아웃·회전·fixation 방지), CSRF(X-CSRF-Token 헤더),
  RBAC deps(auditor=명시 목록), rate limit, 잠금, 로그인/비밀번호변경 페이지+JS
- M2 완료(108 tests): audit_logs+마스킹(record_audit), 관리자 사용자 API 10종
  (/api/admin/users — 생성 시 임시비번 1회 표시, disable=세션 폐기, 마지막 system_admin 가드),
  audit 조회 API(auditor 접근 가능), clovirone-user CLI 11종(동일 service layer, 비번 stdin만)
- M3 완료(06468a3, 143 tests): AllowlistRegistry(mtime 캐시·미존재=전면거부), SecretValue(repr=***)
  +FileSecretReferenceProvider(경로순회 차단), OutboundClient(유일 httpx 관문·redirect 금지·
  call-time SSRF·bearer/api_key 주입), config_versions(스냅샷 append-only), Integration Registry
  (CRUD·health·enable/disable·rollback=신규버전·discovery 4종 시드), httpx import 정적 가드 테스트
- M4 완료(ae47005, 168 tests): jobs 테이블+원자 claim(단일 UPDATE RETURNING, 스레드 경합 테스트
  증명), backoff 5·10·20s, stuck 복구(sweep), graceful shutdown, idempotency dedup(begin_nested),
  worker_main(시그널 처리·tick_callbacks=M8 scheduler 연결점), admin jobs API(operator retry/cancel)
  ⚠️ 교훈: SQLite DateTime 문자열 비교는 strftime("%Y-%m-%d %H:%M:%S.%f")로 마이크로초 6자리
  필수(SQLAlchemy 저장 형식과 일치). 원시 UPDATE 후 ORM 객체는 db.refresh 필요.
- M5 완료(e9c467e, 190 tests): conversations/messages(0006), §23.2 API(202+polling, client_message_id
  멱등, 자동 제목), chat_message 핸들러(n8n via OutboundClient, timeout/5xx=재시도·4xx=영구,
  on_failure 훅→message failed 마킹, backend_conversation_id 컨텍스트 유지), worker에 최종실패
  훅 호출 추가(sweep 경로 포함), 채팅 UI 전체(chat.html/css/js — textContent 렌더, ticket/project
  카드, notion.so 링크 검증, Enter 전송, 5000자, 폴링 backoff, 입력 복원, sessionStorage 복원,
  모바일 drawer), requester 위조 차단·IDOR·XSS 테스트. node --check JS 구문 확인.
  ⚠️ 미검증: 실브라우저 렌더(로컬 uvicorn+Chrome 검증은 검수 루프 전 수행 예정)
- M6 완료(ddf6ddc, 213): Runner Registry(§15 — 생성=강제 disabled, clone, circuit breaker
  5실패→degraded+300s cooldown+half-open, health/test, rollback), Workflow Registry(§16 —
  test=GET 도달성만·write 실행 금지, seed 'ClovirONE AI 업무 도우미'), provider_http/provider_n8n
- M7 완료(43c1f8f, 229): prompt/policy 버전 수명주기(행=버전, draft→test→review→published→
  archived, publish 시 기존 published 자동 archived, unified diff, rollback=구버전 재발행),
  automation_templates(대상 존재 검증, disabled 기본). ⚠️ 교훈: 라우터 팩토리에서 closure 변수
  annotation 쓰려면 `from __future__ import annotations` 금지(문자열화→FastAPI가 query로 오인).
  🔧 flake 수정: Windows 시계 tick(15.6ms)으로 메시지 created_at 동률 빈발 → 메시지 정렬을
  SQLite rowid(삽입 순서)로 변경.
- M8 완료(0f25df3, 256): schedules/schedule_runs(0009), cron.py(cronsim+ZoneInfo, naive-UTC 경계,
  preset daily/weekly/monthly, DST 테스트), SchedulerService.tick(미스파이어 skip=skipped 기록/
  run_once=1회 캐치업, UNIQUE 멱등키 insert-first(begin_nested), 동시실행 skip, once 자기비활성,
  end_at 초과 시 비활성), schedule_run 핸들러(workflow invoke, approval_required write는 자동
  실행 거부, on_failure→run failed), run-now/dry-run(§18.6), run retry(operator), worker_main에
  scheduler tick_callbacks 등록(1초 간격). ⚠️ 교훈: FakeClock을 30분 이상 advance하면 테스트
  세션이 idle 만료 → 재로그인 필요.
- M9 완료(1a387c2, 268): approvals(0010, §20/§21.15 — 게이트 규칙: system_admin=즉시 적용,
  그 외=202 approval_pending; 대상: schedule.enable / runner base_url·secret_ref 변경 /
  role→admin+ 변경. 자기승인 금지(feature-flags.json self_approval_allowed), 72h 만료 스윕
  (worker tick), approve 시 APPROVAL_EXECUTORS로 저장 payload 정확히 1회 재적용, 이중 승인 409),
  notifications(§21.16 in-app — fan-out: worker 최종 실패→job 소유자, schedule 실패→소유자,
  승인 요청→관리자들, 승인 결정·만료→요청자, 계정 잠금→본인+관리자; /api/notifications
  목록/읽음(소유권 검사)/unread-count), core/feature_flags.py.
  ⚠️ M8 테스트 2건이 admin으로 enable하던 것을 system_admin으로 변경(게이트 도입 여파).
- M10 완료(a215cee, 292): settings registry(0011 app_settings, §14.4 허용목록 14키+검증자,
  dry-run→apply→before-snapshot(config_versions)→rollback, SettingsCache in-process), maintenance
  gate(block_if_maintenance dep, user만 503·operator+ 통과), 문서자동화(§19 — quality.py 게이트
  6종, document_generations(0011) preview_only/preview_then_approve/auto_publish, dedup 멱등키,
  read-back, disabled 예제 템플릿, approval executor document.publish 추가)
- M11 완료(50bca11, 304): user_notion_mappings(0012), verify_mapping(예약 워크플로 'notion-user-
  mapping' 조회 → verified(1)/unmapped(0)/conflict(2+), 캐시·last_verified), manual map/unmap/
  resolve-conflict, notion_user_id 마스킹(abcd…efgh)·브라우저 입력 금지, admin API + users의 501
  verify를 실제 구현으로 교체, profile/user-row에 실제 status. **chat 핸들러 안전 차단**: 미매핑
  사용자의 '내 티켓/내 프로젝트' 1인칭 요청은 n8n 호출 없이 안내 메시지로 응답(§12.3).
  🔧 login_as 픽스처가 make_user 선생성 사용자와 중복 생성하던 것 수정(기존 사용자 허용).
- **남은 구현**: M12(dashboard 집계·backups 테이블+sqlite backup API+temp restore·진단 번들),
  M13(관리자 UI 16화면), M14(§30 스크립트 5종+systemd+nginx vhost+docs 17종+deploy 05~99),
  M15(보안 스윕), 검수루프 3회, 로컬 브라우저 실화면 검증, D2~D5 배포.
- M12 완료(db48686, 319): dashboard 집계(§14.1 — 컴포넌트 heartbeat·카운트·24h job 통계·disk/mem/
  cert D-day·last backup), backups(0013 sqlite backup API online backup+checksum+integrity verify+
  temp restore+retention), worker heartbeat(15s), 진단 번들(마스킹). ⚠️ verify_backup는 malformed
  image의 DatabaseError를 not-ok로 처리(예외 전파 금지).
- M13 완료(3900f65, 326): 관리자 콘솔 16화면 데이터 주도 SPA — base_admin.html 셸 + common.js
  (el/api/badge/formModal/confirmModal/diffModal, CSRF 자동) + sections.js(16섹션 선언형 config)
  + app.js(라우터·제네릭 테이블/필터/정렬/행액션 엔진·dashboard/settings/maintenance 커스텀 뷰·
  다크테마·모바일 drawer). CSP 준수(inline JS 0). /admin은 operator+ 요구(user는 / 리다이렉트).
- **✅ M13 실서버 검증(2026-07-14, 로컬 uvicorn :8099)**: 실행 중인 실제 서버 대상 15개 체크
  전부 통과 — 로그인→세션→/api/me(system_admin)·채팅 페이지·admin HTML(inline JS 0)·정적 자산
  7종 200·dashboard API(discovery 4 integration 집계)·CSP script-src 'self'.
  ⚠️ **브라우저 실제 페인트는 미검증**: Claude-in-Chrome 확장 미연결로 JS 실행 후 렌더 확인 불가.
  자산·API·라우팅·CSP는 실서버로 확인됨(테스트 326 + HTTP e2e). 브라우저 렌더는 검수 루프나
  확장 연결 후 확인 필요. 로컬 서버 실행 중: http://127.0.0.1:8099 (verify-admin@goodmit.co.kr /
  Verify-Admin-1!). 종료: uvicorn 프로세스 kill.
  [히스토리] 이전 남은 구현 메모(M10부터):
  게이트·§19 문서자동화 preview→승인→publish+품질게이트+disabled 예제), M11(notion_mapping —
  §21.2 테이블은 신규 마이그레이션 필요(0002에 placeholder 없음), verified/unmapped/conflict,
  '내 티켓' 차단은 chat_message 핸들러에 훅), M12(dashboard 집계·backups 테이블+sqlite backup
  API+temp restore·진단 번들), M13(관리자 UI 16화면 — admin/base_admin.html+공통 테이블 렌더러
  JS, CSP inline 금지 유지), M14(§30 스크립트 5종+systemd 유닛+nginx vhost+docs 17종+
  deploy/00~99), M15(보안 스윕: IDOR 전 객체, secret 노출 전 GET, §32.8 항목별), 검수루프 3회,
  로컬 uvicorn+Chrome 실화면 검증(로그인→채팅→관리자), D0~D5 배포(계획 파일 참조).

## 2026-07-14 — 세션 1 (검수 루프)

- **iteration 1** (wf, 7관점 21에이전트, 76 findings): Critical 0, High 7 확정 + Medium 다수.
  전부 수정(commit 6787df9, 373 tests). 핵심: 설정 12/14 먹통→실배선+6키 제거, XFF IP 위조,
  DB restore WAL 사이드카, schedule_run 취소 고착, admin의 system_admin 생성, 관리자 표
  페이지네이션, 모바일 드로어. Medium 잔여는 KNOWN_LIMITATIONS 문서화(5d7c5ba).
- **iteration 2** (8에이전트, 22 findings): **High 1** (내가 iter1에서 넣은 회귀 —
  create-user 임시비번 secretModal이 formModal auto-close에 지워짐) + 보안/데이터 Medium.
  전부 수정(commit ccbb5dd, 381 tests). secretModal keepModalOpen, integration rollback 게이트,
  system_admin 권한 경계(부여/회수 모두 sysadmin), password min_classes bound, 백업 보존
  마지막 성공본 보존, 문서 발행 멱등키, effective settings 배선 완결.
- **iteration 3**: 최종 확인 진행 중 (High=0 확인 목표).
- **iteration 4** (6에이전트, 9 findings): **High 1** — admin이 reset-password 등
  lifecycle 엔드포인트로 system_admin 계정 탈취(권한 상승) 확정. ensure_can_manage_target
  서비스 계층 가드로 전 경로(HTTP·CLI·승인) 차단(4d17879, 389 tests, 보안 회귀 7).
- **iteration 5** (3에이전트): raw 1건 → 적대 검증에서 **Critical 0 / High 0** (clean).
  단일 medium(승인 executor stale TOCTOU)은 verifier가 not-real 판정했으나 방어적으로
  hardening(stale 승인 거부). **검수 루프 종료: §32.9 완료조건 충족(Critical 0·High 0·5회
  반복·389 테스트 통과·static clean·Medium 문서화).**

## 2026-07-14 — 세션 1 (배포 D2~D5)

- **D2 번들 재빌드**(리뷰 수정 반영): dist/…bundle.tar.gz 11MB, wheelhouse 34 manylinux cp312.
- **D3 설치**: bundle scp→sha256 검증→unpack→install-...sh 실행. ⚠️ 2건 수정:
  (1) alembic/discovery가 relative script_location/`python -m app`을 못 찾음 → install에 `cd $APP_DIR`
  추가(runuser는 -l 없으면 CWD 보존). (2) seed_admin의 `$(grep web.env)`가 cloviradmin(권한없음)에서
  전개됨 → `sudo bash -c`로 root가 grep. INSTALL_OK: 3서비스 active·WAL·기존 서비스 무접촉.
- **최초 계정**: hshwang@goodmit.co.kr system_admin, 임시비번 콘솔 1회 표시(로그 미기록).
- **D4 검증**: validate-...sh VALIDATE_OK(§35 전항목), 스모크 로그인 흐름(login 200→/api/me 세션
  identity 확인), 백업+integrity ok+체크섬 OK. ⚠️ 브라우저 렌더는 Chrome 확장 미연결로 미검증.
- **D5 마무리**: 최종 ZIP(/home/cloviradmin/ClovirONE_Web_Assistant_Final.zip, secret 미포함),
  workflow 시드('ClovirONE AI 업무 도우미'), **NOPASSWD 제거 확인**(sudo -n now fails), 키인증 유지.
  INSTALLATION_REPORT.md 작성. 🔧 discovery.py에 workflow 시드 배선(재설치 대비).

## 2026-07-14 — 세션 1 (배포 후 검수·UX 폴리시)

- **브라우저 실화면 검증**(Chrome 확장 연결): 로그인→비번변경→채팅→관리자 콘솔(대시보드·사용자
  ·Integrations·Runners 등) 전부 정상 페인트, 콘솔 JS 에러 0.
- **검수 루프 iteration 6**(7관점 적대검증, 배포단계 코드 변경 대상 최종 확인): raw 2건 →
  적대 검증에서 **Critical 0 / High 0 / Medium·Low 0**. 5→6회 수렴, 확정 결함 없음.
- **UX 개선(사용자 피드백: "이게 무슨 페이지인지·각 설정이 뭘 의미하는지 모르겠음")**:
  관리자 콘솔 16개 섹션에 페이지 설명 콜아웃(ⓘ) 추가. `sections.js`에 `desc` 필드,
  `app.js`에 `sectionHelpNode()`/`prependHelp()`(모든 렌더러 분기: dashboard·table empty/non-empty
  ·settings·maintenance), `admin.css`에 `.section-help` 스타일. **XSS 안전**: desc는 개발자
  정적 리터럴이나 innerHTML 미사용—태그 제거 후 textContent로 렌더(코드베이스 일관성). Settings는
  기존 per-setting `설명`/`적용` 컬럼과 결합. node --check OK, 관리자 콘솔 테스트 7 pass.
  로컬 서버(:8099) 브라우저 검증 완료(dashboard·settings·integrations·maintenance·schedules
  ·notion-mapping 콜아웃 렌더 확인). 커밋 완료.
- **✅ 프로덕션 반영 확인**: 정적 3파일 배포됨. 디스크 sha256 = 기대값 일치, **nginx 서빙 파일
  sha256도 바이트 단위 일치**(`curl .../static/... | sha256sum`). 사용자가 파워쉘로 tar 직접 추출
  (apply 래퍼 백업폴더 흔적 없음 — 결과 파일은 정확, 이전본은 git 히스토리). Ctrl+Shift+R 안내.

## 2026-07-14 — 세션 1 (유지보수 하네스 구성)

- **하네스 목적**: 향후 세션이 제품을 이어받아 유지보수·수정 가능하도록 프로젝트 컨텍스트를 고정.
- **`CLAUDE.md` 신규**(저장소 루트, Claude Code 자동 로드): ①프로젝트 개요 ②불변 규칙 10종(sync·
  OutboundClient 단일관문·secret 파일참조·opaque 세션·textContent 렌더·불변성 등) ③저장소 지도
  ④로컬 개발/테스트 ⑤변경 워크플로 ⑥배포/롤백 ⑦커밋 전 보안 체크리스트 ⑧함정(BUILD_LOG 교훈)
  ⑨문서 색인 ⑩운영 전 조치.
- **`docs/MAINTENANCE_PLAYBOOK.md` 신규**: 12개 레시피(프런트 핫배포·전체 업그레이드·admin 섹션·
  설정·마이그레이션·API·secret·allowlist·검수 루프·롤백·백업·운영 명령), 각 exact 명령.
- **`scripts/stage-static-update.sh` 신규**: 프런트 핫배포 스테이징 자동화(LF 정규화+체크섬 tar+
  scp/sudo/verify 명령 출력). app/static/* 만 허용(안전 가드). bash -n·dry-run OK.
- README에 CLAUDE.md·PLAYBOOK 포인터 추가. 전역 메모리에도 하네스 진입점 기록.

## 2026-07-14 — 세션 1 (전수 기능 감사 + P0 수정)

- **전수 감사**(사용자 지적 "페이지마다 안 되는 게 많다"): 21개 도메인 × 42 에이전트(감사+적대검증).
  결과 `docs/FEATURE_AUDIT_2026-07-14.md`. 핵심: **백엔드 완성+검수됐으나 관리자 콘솔 UI가 대부분
  읽기 전용**(20/21 도메인 frontend_all_actions_wired=no). 확정 106건(High 19·Med 24·Low 62),
  ui-gap 56·spec-deviation 21·bug 11. 내 이전 검수의 빈틈=UI 완성도 미감사.
- **P0 버그 11건 수정 + 회귀 테스트**(394 green, static OK): chat 안전차단 정규식 '할당' 누락(HIGH,
  #1 퀵프롬프트 우회) → 수정; prompts/policies 중복이름 500→409(limit(1)); notion verify stale 정리;
  jobs retry/cancel started_at; templates policy_id 검증; backups 파일명 μs 유일화; chat 미지 커서→[];
  settings effective_settings N+1; 권한 버튼 게이팅(app.js roles 필터 + sections.js roles 태깅 —
  operator/read-role에게 enable/disable/backup 버튼 숨김). 커밋 8d98647·a688c32·060e73a 등.
- **러너 헬스 오탐 근본원인**: discovery 시드가 러너 health_url=None → base_url '/'(404)=down. 러너는
  살아있음(/healthz=200). 시드 수정(3ae07fc) + **프로덕션 3개 통합 health_url PATCH·검증(all up)**.
- **정적 배포**: 브랜드 디자인(좌상단 '관리자 콘솔' 과대 → muted 서브타이틀) + 콜아웃 + 권한게이팅
  프로덕션 반영, **서빙 해시 로컬 일치 검증 완료**. 채팅 정렬 정상 확인(처리중 멈춤은 로컬 worker 부재).
- **다음: P1** — 관리자 콘솔 쓰기 UI 구축(Runners·Integrations 생성/수정 → 수명주기 → Jobs 섹션 등).

## 2026-07-15 — 세션 1 (P1 관리자 콘솔 쓰기 UI 완성)

- **데이터주도 폼 프레임워크**(app.js): `openEditForm`(PATCH/PUT·row prefill·approval_pending 인지),
  `openActionForm`(clone/rollback/manual-map 파라미터 폼·body(row) 병합), `openSubList`(실행이력·세션
  테이블 모달), form 기반 customActions, action kind `edit`/`form`/`sublist`, roles 게이팅.
- **전 섹션 배선**(sections.js): Runners·Integrations·Workflows 생성/수정/상세(+러너 복제);
  Prompt/Policy `LIFECYCLE_ACTIONS`(상세·수정[draft]·상태변경[draft→test→review→published 셀렉트·
  백엔드 검증]·새버전·롤백[name+version]); Templates 생성/수정[PUT]/활성; Schedules 생성/수정[PUT]/
  실행이력[sublist]; **Jobs 섹션 신설**(status/type 필터·재시도[failed]/취소[queued]/상세);
  Documents 생성 폼; Notion 수동매핑·충돌해결; Approvals 상세·취소; Users 수정[역할]·세션; Notifications 읽음.
- **교훈**: prompt 수명주기는 draft→test→review→published(직접 발행 불가) → 단일 발행 버튼 대신 상태
  셀렉트로 백엔드 검증에 위임. GET은 require_csrf가 SAFE_METHODS로 스킵(jobs GET 목록 CSRF 불필요).
  브라우저 ref는 reload 후 stale 가능(재-find 필요).
- **로컬 실검증**: 러너 생성(비활성 기본)+수정 prefill, 프롬프트 생성+draft→test 전이, Jobs 네비 표시.
  394 green·static OK·node --check OK. 커밋 bce5789·9230b4c. **프로덕션 배포 대기(정적 3파일 sudo)**.
- **잔여 P2**: diff 뷰어, settings 버전/롤백 UI, schedule run 재시도, approvals 만료표시.

## 2026-07-15 — 세션 1 (P2 마무리)

- **P2 UI**(정적, 현재 백엔드와 호환): prompt/policy **버전 비교(diff)**(kind:"diff"→GET diff/view→
  A.diffModal); **Settings 이력/롤백**(settingHistory: 버전목록+원클릭 롤백) + **수정 시 dry-run 검증**;
  **schedule 실행이력 재시도**(openSubList rowAction 확장). 로컬 실검증: 설정 365→400 수정(dry-run+PUT)
  +이력 모달 v1=365+롤백 버튼 확인.
- **P2 백엔드**(spec 편차, 사용자 비가시): health stale→**down**(§14.1); approvals pending-past-expiry
  목록에서 **expired 표시**; integrations/runners/workflows/settings rollback **async→sync**(불변식,
  body는 Pydantic 모델); **ui_branding.product_name → 채팅 페이지 제목**(로그인만이었음). 회귀 테스트 2.
- 커밋 ec159b8(백엔드)·d870a4d(UI). 394+ green·static OK.
- **배포**: 정적 P2 UI는 핫배포(무중단, 현재 백엔드 호환). 백엔드 P2(비가시 spec 수정)는 **전체 업그레이드**
  필요(서비스 재시작) — Low 우선순위라 다음 코드 업그레이드에 배치 권장. DB 마이그레이션 없음.

## 2026-07-15 — 세션2 후반 (챗봇 조회 배포 + 운영 결정)

- **#34 Phase 1 조회 챗봇 배포·검증**: 자유 질의가 실서버에서 라이브 Notion 데이터로 동작(필터·정렬·요약·추론). 러너 `runner/claude-work-assistant/assistant.py`(버전관리) 확장 + 버그 3개 수정(CLI 2.1.x `result` 파싱=claude_draft도 복구, update-intent 오탐, `_extract_text` response_text 누락). 러너 6+플랫폼 3 테스트. 커밋 8805fed·1eae1ad·f0ac01b·e81c040.
- **질문 답변(코드확인)**: 채팅 보관=worker `run_retention` 실제 실행(기본 365→**90일로 변경**·프로덕션 값도 90 반영). Notion 매핑=계정↔Notion ID 연결로 '내 티켓' 정확도↑, **이메일/이름 fallback 있어 선택 기능**(유지+설명 개선, 배포). Claude 세션=`--no-session-persistence`라 세션 없음, 컨텍스트는 러너 sqlite+플랫폼 전체기록에 durable(예전 대화 이어감 가능), 다만 손실 시 경고 없음(개선 대상).
- **응답속도 병목**: n8n이 매 메시지 Notion 전체 조회(~60초). 결정=**A. n8n 유지+5분 캐시**. 러너 생성도 LLM 에이전트화 예정.
- **생성 흐름 발견**: claude_draft 코드수정+단위테스트 통과(복구 확신)이나 규칙기반 필드수집 brittle('난이도 보통' 파싱 실패). e2e 생성은 Notion write라 미완결(확인 미전송). → 생성 LLM 에이전트화 필요.

## 2026-07-15 — 세션2 (n8n 캐시 JSON + 생성 LLM 에이전트화)

- **n8n 5분 캐시(옵션 A) JSON 생성·구조검증**: `Downloads\ClovirONE_AI_Work_Assistant\ClovirONE_AI_Work_Assistant_CACHED.json`(+`CACHE_적용_안내.md`). 캐시=n8n 내장 `$getWorkflowStaticData('global').workDataCache`(**Redis 아님·외부 인프라 0**), 5분 TTL. 노드 2개 추가(캐시 확인 Code / 캐시 유효? IF) + `AI 요청 구성` 재작성(hit=캐시 읽기 / miss=노드 읽기+캐시 기록) + `Notion 변경 결과` 성공 시 캐시 무효화. 재배선·jsCode 참조·미스경로 실행 무결성 전부 통과. **⚠️ 라이브 웹훅 HIT/MISS는 사용자가 import 후 검증(안내서에 절차)**.
- **#34 Phase 2 생성(create) LLM 에이전트화**(러너): 규칙기반 필드게이트를 `claude_draft` **뒤로** 이동. DRAFT_SCHEMA에 `fields`(priority/difficulty/due_date/assignee_names/unassigned) 추가 + 프롬프트 지침. 코어서(`_coerce_priority/_coerce_difficulty/_coerce_iso_date`)로 정제(규칙 파싱값 절대 미덮어씀·추측 0). '난이도 보통' 등 자연어/다중턴이 LLM 추출로 채워져 CREATE_PREVIEW 도달. ready=false→자연질문, ready=true+필드누락→여전히 게이트. 병합값이 preview·pending·`build_create_body`(실제 write)까지 도달 확인. `create_missing_fields` 단일 소스. 러너 테스트 6→**10 green**.
- **미검증(정직)**: 실제 Notion 생성 e2e는 side-effect라 미실행 → 유닛+코드리뷰가 안전망. 배포 후 사용자 실검증 필요.

## 2026-07-15 — 세션2 (생성 러너 3.1.0 배포 + 코드리뷰 반영)

- **코드리뷰(적대적) 지적 전부 수정**: [HIGH] 담당자 다중턴/수정 시 유실→본인 오배정(`_restore_assignees`로 이전턴 복원 + `assignee_people`/`create_unassigned` 컨텍스트 지속 + 본인배정을 LLM 추출 뒤로 지연) · [HIGH] `_coerce_priority` 부분문자열이 없는 우선순위 발명("상관없어요"→높음)→정확매칭+DRAFT_SCHEMA priority enum · [MED] LLM `assignee_names` 미소비→`_resolve_named_assignees`(정확·비모호 매칭만) · [MED] `_DIFFICULTY_WORDS` 우선순위어휘 충돌 제거 · [LOW] draft 불변화·`_ask_missing` pending_question. 회귀 테스트 3개 추가(담당자 다중턴 지속·우선순위 무발명·LLM 이름 소비). **러너 13 green**.
- **배포 3.1.0**(claude-work-assistant, :8789, User=n8n): SHA 전송검증→서버 py_compile→백업(`assistant.py.bak-20260715-122941`)→install→restart→**헬스 200+version=3.1.0 검증**(자동롤백 미발동). 다른 러너 8787/8788 무손상 확인, active. 롤백=백업 파일 재설치.
- **⚠️ 미검증(정직)**: 실제 채팅에서 create가 CREATE_PREVIEW 도달·승인 시 Notion write는 side-effect라 미확인. 사용자 30초 검증: 채팅에서 "○○프로젝트에 △△ 티켓 만들어줘 난이도 보통…" → 프리뷰 필드(특히 난이도) 확인 → 승인 시 Notion 등록 확인.

## 2026-07-15 — 세션2 (채팅 무응답 진단 + 생각중 애니메이션)

- **"채팅 대답 없음" 진단**: DB 마지막 메시지·job이 **11:23 KST**(1.5h 전)이고 이후 전무, 웹로그상 브라우저(192.168.253.124)가 **11:44 이후 서버에 요청 0건**. → 서버가 아니라 **브라우저 세션 만료/스테일**. **서버 파이프라인은 정상 검증**: worker와 동일 payload로 n8n 웹훅 직접 프로브 → 13초에 정답(`"진행중 32건"`, 라이브 Notion). = **러너 3.1.0 배포도 라이브 정상 확인**(제 배포 무해). 사용자 조치: Ctrl+Shift+R + 재로그인.
- **생각중(typing) 애니메이션**(사용자 요청): chat.js `renderThinking()`(점 3개 순차 바운스)+`.thinking-*` CSS(`thinking-blink` 스태거 애니메이션·prefers-reduced-motion 대응). **폴링 깜빡임 제거**: `lastRenderSig` 시그니처 가드로 변경 없으면 메시지 로그 재렌더 안 함(=애니메이션 리셋/플리커 방지). 정적 핫배포(체크섬 일치+HTTP 200 서빙 검증, 재시작 불요).

## 2026-07-15 — 세션2 (수정(update) LLM 에이전트화 + 러너 3.2.0 배포)

- **#34 Phase 2 수정(update) 에이전트화**: 규칙 난이도 파서를 정성표현(보통/어려움 등, 난이도 앵커+조사 허용 gap)까지 확장 → create·update 공통 fast path. LLM 폴백(`llm_extract_update_changes`, `UPDATE_EXTRACT_SCHEMA`): 규칙이 값 못 뽑거나 필드 키워드만 언급된 복합 메시지("완료로 바꾸고 난이도도 낮춰줘")면 LLM이 gap 채움 → **직접 쓰기 대신 확인 미리보기(UPDATE_PREVIEW, needs_confirmation)**. 규칙전용 변경은 기존대로 직접 쓰기(fast). 승인 시 handle_confirmation(kind=UPDATE)로 기록.
- **적대적 코드리뷰 BLOCK → 수정**: [CRITICAL] `extract_priority` 스트립/`extract_difficulty` 앵커가 조사 화이트리스트(는/를/…)만 허용 → "난이도**도** 낮음"/"난이도**만** 보통"에서 난이도어가 우선순위로 누출 + 실제 난이도 누락 → **직접 무확인 오기록**. 공유 상수(`_DIFFICULTY_ANCHOR=난이도.{0,3}?`)로 모든 조사 허용·두 함수 단일 소스. [HIGH] 무앵커 `[1-6]단계/정도` 폴백이 무관한 "2단계" 오파싱 → 제거(앵커만). [HIGH] 복합 메시지 필드 누락 → unresolved-mention 트리거로 LLM gap-fill. 경험적 검증: 누출 0·2단계 오파싱 0·정상 우선순위 유지·규칙전용=직접/LLM=미리보기.
- 러너 테스트 **18 green**. 배포 3.2.0(백업 `assistant.py.bak-20260715-133930`→헬스 200+version 3.2.0 검증→자동롤백 내장). **라이브 검증**: 읽기전용 질의 "계획 155건" 11초 응답, 8787/8788 무손상.
- **잔여(리뷰 MEDIUM, 비안전·연기)**: ①LLM 호출이 타겟/소유권 확인 전 발생(비효율, n8n 토큰 뒤라 저위험) ②handle_confirmation이 확인 시점에 소유권 재검증 안 함(create도 동일한 기존 패턴). 향후 하드닝.

## 2026-07-15 — 세션2 (#34 Phase 2: 이미지 파이프라인 구축)

- **사용자 요구 3모드 반영**: ①정보 추출 ②이미지 보고 대화하며 추론(다중턴) ③본문에 이미지 반영.
  설계: 이미지 도착 시 러너가 **1회 정밀 비전 분석**(summary/ocr_text/notable/suggested_title) →
  결과를 **대화 컨텍스트(image_notes, 최근 5개)에 영속** → 이후 모든 턴의 자유질의(claude_query)와
  티켓 초안(claude_draft)에 주입 = ①②③(텍스트 반영) 충족. 원본 파일은 러너 저장소에 TTL 24h 보관
  → ③(바이너리 Notion 첨부)는 후속 n8n 업로드 체인(작업 #39, n8n 2.29.9 확인).
- **플랫폼**: `app/chat/attachments.py` 신규(≤3장·PNG/JPEG/WebP·3MB/장·6MB 총·base64·**매직바이트 검증**·
  파일명 새니타이즈). 메시지 POST에 attachments(라우터 Pydantic+서비스 검증), 이미지-only 메시지는
  "(이미지 첨부)" 대체. **저장 원칙(서버 미보관)**: Message에는 이름만(structured_payload), bytes는
  job payload로만 통과 → worker가 n8n 전달 성공 후 **payload에서 bytes 스트립**. 미들웨어+nginx
  해당 라우트만 8MB(나머지 256k 유지). UI: 📎 버튼+**클립보드 붙여넣기**+칩(제거 가능)+
  캔버스 다운스케일(장변 1568px JPEG q0.85)+메시지 이름칩 렌더.
- **러너 3.3.0**: `_run_claude`에 tools/cwd/max_turns 파라미터(비전=Read 도구만·이미지 디렉터리 cwd).
  `ingest_image_attachments`(재검증→생성 파일명으로 저장→분석→노트, 실패 시 우아한 성능저하).
  process_request→route_request 분리(비전 ms 합산). 이미지 오면 자유대화 라우팅·CREATE 승인 대기 중
  이미지는 초안 수정으로. claude_query에 **대화 이력 축적**(user/assistant 왕복 10개 캡). MAX_BODY 16MB.
  **하드닝(리뷰 MEDIUM 2건 해소)**: update LLM 추출을 타겟 해석·소유권 확인 **뒤**로(비용/DoS 차단),
  handle_confirmation이 **확인 시점 소유권 재검증**(재할당 시 FORBIDDEN·소실 시 재조회 안내).
- **n8n v2 JSON**: `ClovirONE_AI_Work_Assistant_v2_cache_image.json` = 캐시 + attachments 통과
  (요청 전처리·AI 요청 구성 2곳). 구조 검증 5항목 통과. 안내서 v2 갱신. **v2 하나만 import하면 됨**.
- 테스트: 플랫폼 전체 green+STATIC_CHECKS_OK(첨부 유닛 8·API 4·핸들러 1 신규), 러너 **23 green**
  (비전 인제스트·이미지 대화 라우팅·LLM 비용 가드·confirm 재검증 신규 5).

## 2026-07-15 — 세션2 (적대 리뷰 반영 + 러너 3.3.0 배포 + 번들 준비)

- **3관점 적대 리뷰(워크플로 15에이전트)**: 확정 8건(HIGH 3·MED 5)/기각 4건. 전부 수정:
  ①비전 타임아웃 미포착→메시지 전체 504·재시도가 비전 재과금 → 비전 전용 60s 타임아웃+우아한 강등+message_id 재분석 방지
  ②이미지+명시적 변경명령이 읽기전용 대화로 하이재킹 → update 의도면 쓰기 흐름 유지, 노트 미적재 시 플래그 미설정
  ③bulk 후보가 존재하지 않는 project_id 키로 필터→항상 공집합 → project_ids 리스트 포함검사
  ④~⑧ job payload 이미지 bytes 잔존(안내 조기반환·최종실패·retry 유실·정리부재) → `strip_attachment_bytes` 공통헬퍼(모든 종료경로)+retry가 도너 job에서 bytes 회수 후 도너 스트립+리텐션 스윕(24h 지난 종료 job).
- **기각건 재검증서 발굴한 잔존 이슈(중요)**: 첫 메시지 conversation_id=None→n8n이 전 대화를
  'powershell-local' 공유 버킷으로 수렴(사용자 대화 간 컨텍스트 혼입+전 사용자 이미지 동거) →
  핸들러가 플랫폼 UUID 폴백 전송으로 근본수정(신규 대화부터 격리).
- **검증·배포**: 플랫폼 전체 green+STATIC_CHECKS_OK, 러너 **27 green**. 커밋 ba113fc·28f1a87·c70e7fe·e74d9e3.
  **러너 3.3.0 배포**(백업 `assistant.py.bak-20260715-143631`→헬스 200+3.3.0, 이미지 저장소 0700 n8n 생성,
  라이브 질의 12s 정답, 8787/8788 무손상). **업그레이드 번들 서버 업로드 완료**(SHA 일치,
  `/home/cloviradmin/clovirone-web-assistant-bundle.tar.gz`) — 실행은 사용자(분류기 차단, 기존 정책).
- **사용자 액션 대기**: ①전체 업그레이드 실행 ②n8n v2 import ③브라우저 hard-refresh.

## 2026-07-15 — 세션2 (#38 로그인 페이지 ClovirONE 디자인 적용·배포)

- **디자인 시스템 이식**: `Downloads\ClovirONE Design System\clovirone\ui_kit\Login.html` → split 히어로
  (인디고 그라디언트+그리드 오버레이+세리프 모토+업무도우미 테마 데코 타일 3종) / 흰 폼 패널(리드 아이콘
  인풋·포커스 링·그라디언트 CTA). 1920×1080 고정 스테이지 → **반응형 flex**(<1024px 히어로 숨김).
- **미사용 기능 제거(사용자 결정)**: SSO/SAML·OTP 버튼, 사용자/관리자 토글, 로그인 유지. '비밀번호 찾기'
  링크 → 실제 플로우 안내("관리자에게 재발급 요청")로 대체. **다크 텍스트 워드마크 SVG 신규**
  (기존 wordmark는 흰 텍스트 — 흰 패널에서 비가시, 실화면 검증으로 발견). 크롬 autofill 배경 오버라이드.
- **불변 준수**: 외부 폰트/CDN 0, 인라인 script/style 0(CSP — 초안의 인라인 script 자가 발견·제거),
  login.js 무수정(엘리먼트 id 계약 유지).
- **실화면 검증(로컬 :8099 Chrome)**: 렌더 + 다크 워드마크 + **실제 로그인→채팅 진입** 성공, 콘솔 에러 0.
  보너스로 '생각중 ●●●' 애니메이션·📎 첨부 버튼 실화면 최초 확인.
- **프로덕션 핫배포**(무중단): login.html(템플릿 auto-reload)+login.css+wordmark-dark.svg — 체크섬 일치
  +서빙 마커 검증(LOGIN_DEPLOY_OK). 백업 *.bak-20260715-145617. **업그레이드 번들 재빌드·재업로드**
  (구 번들이 로그인을 롤백시킬 뻔한 것 자가 발견 — 새 SHA 31a18b3d…). 커밋 c86259a.
- **질문 답변 기록**: 관리자 사용자 추가 시 초기 비밀번호 입력란 없음 = 의도된 설계(서버 자동생성→
  1회 표시 모달→첫 로그인 변경 강제). 분실 시 = 사용자 행 '비번재발급' 버튼(동일 1회표시 플로우) 기존재.

## 2026-07-15 — 세션2 (업그레이드 스테이지 사고 + 부팅 자동기동 감사)

- **사고**: 사용자가 실행한 업그레이드가 UPGRADE_OK였으나 **옛 스테이지**(`/home/cloviradmin/deploy/stage`
  고정 기본값)에서 설치 → 이미지 백엔드·로그인 리디자인 미반영(login.css 404로 발견). 원인=스크립트의
  고정 STAGE 기본값 + 안내 명령에 STAGE 미지정(내 실수).
- **재발 방지 수정**: upgrade 스크립트가 **자기 번들 위치에서 STAGE 자동 인식**(BASH_SOURCE 기준
  <stage>/app-src/scripts → 상위 2단계, app-src+wheels 존재 검증, `stage:` 로그 출력, env 오버라이드 유지).
  커밋 후 번들 재빌드·재업로드(SHA 6e1520e8…).
- **부팅 자동기동 감사(사용자 요청)**: 7개 서비스 전부 이미 `enabled`+`Restart=on-failure`(3~10s) —
  web/worker/nginx/n8n/work-assistant/ticket-runner/request-interpreter. **전원 복구 시 전체 자동 기동
  확인, 변경 불필요.** 러너 상태 DB·이미지 저장소는 디스크 영속(/var/lib/n8n)이라 재부팅 무손실.
  n8n staticData 캐시도 DB 영속. 확인 방법: systemctl is-enabled/show -p Restart 전 유닛 조회.

## 2026-07-15 — 세션2 (재업그레이드 검증 완료 — #35 종결)

- **재업그레이드 라이브 검증(전부 ✅)**: https healthz/readyz 200 · **로그인 리디자인 서빙**(마커 2·login.css 200)
  · nginx 이미지 라우트 8m(root grep: 전역 256k+라우트 8m) · 서비스 5종 active · 러너 3.3.0 무손상.
  → **#35(전체 업그레이드) + 이미지 플랫폼 백엔드 배포 완료.**
- **n8n v2 import 미완 판별(이미지 프로브)**: 웹훅에 1px PNG 첨부 프로브 → 러너에 attachments 미도달
  (image_notes 0, LLM이 "이미지 정보 확인 안 됨"이라 응답 — 파이프라인 자체는 정상). **잔여 사용자 액션 =
  n8n UI에서 `ClovirONE_AI_Work_Assistant_v2_cache_image.json` import 1회**(공유 n8n 무접촉 원칙상 UI 권장).
- USER_GUIDE에 이미지 첨부 사용법 섹션 추가.

## 2026-07-15 — 세션2 (#40 전체 텍스트 검수 + 계정/n8n 이슈)

- **텍스트 검수(사용자 피드백)**: 사용자 노출 문구에서 가운뎃점(·) 나열체 전면 제거, 완전한 자연
  문장으로 재작성 — 로그인 히어로/타일, 비밀번호 변경 안내, 관리자 콘솔 desc 5곳. 프로덕션 서빙
  검증(remaining-middledot=0). 로그인 **히어로 타일 약 1.6배 확대**(clamp 반응형)+문장형 캡션.
  TEXT_DEPLOY_OK(핫배포), 번들 재동기화.
- **초기 비밀번호 UI(사용자 요청)**: 관리자 사용자 추가 폼에 '초기 비밀번호(선택)' 필드+'첫 로그인
  변경 요구' 체크박스 노출(API는 기존 지원, UI만 추가). createForm transform 훅 신설(빈 값 제거),
  백엔드도 공백→자동생성 정규화(다음 업그레이드 반영).
- **hshwang 계정 복구**: CLI passwd(비밀번호는 stdin 전용)+unlock+must_change 해제 — 사용자가 지정한
  기본 비밀번호로 즉시 로그인 가능(값은 기록하지 않음, 대화에서 전달).
- **n8n UI 접속 불가 원인**: n8n이 127.0.0.1:5678에만 바인딩(방화벽 아님, ufw inactive) — 외부
  브라우저에서 직접 접속 불가. 해결책 = SSH 로컬 포트포워딩(서버 무변경) 안내.

## 2026-07-15 — 세션2 (n8n v2 히트 크래시 → v3 긴급 수정)

- **사고(치명)**: v2 import 후 웹훅이 200+빈 본문. 로그 = `Node '프로젝트 묶기' hasn't been executed`.
  **원인 = n8n 2.x task-runner의 정적 프리페치**: Code 노드 소스에 적힌 `$('노드')` 참조를 실행 전에
  전부 로드 — 분기상 실행 안 하는 else 브랜치의 참조라도, 해당 노드가 스킵됐으면(캐시 히트) 즉시 예외.
  v2의 'AI 요청 구성'(hit=캐시/miss=노드 읽기 단일 코드)이 정확히 이 패턴 → **캐시 히트마다 채팅 사망**
  (만료 직후 1회만 성공). 사전 구조검증·설계리뷰 모두 런타임 의미론이라 미탐.
- **v3 수정**: 캐시 기록을 miss 경로 전용 'This 캐시 기록' Code 노드로 분리(참조 노드 전부 자기 경로의
  보장된 조상), 'AI 요청 구성'은 직접 입력($input)+staticData만 읽음(스킵 가능 노드 참조 0).
  재배선: 작업 DB 스키마 조회→캐시 기록→AI 요청 구성. **프리페치 안전 검증기**(전 Code 노드의 $('X')가
  보장 조상인지 그래프 검사) 작성·통과 + 병합-이후 노드 전수 참조 스윕 통과.
- **교훈(불변)**: n8n Code 노드에서는 "실행 안 될 브랜치"라도 `$('노드')`를 적으면 안 된다 —
  조건부 데이터는 staticData나 직접 입력으로만. 향후 모든 워크플로 수정에 프리페치 검증기 적용.
- 산출물: `ClovirONE_AI_Work_Assistant_v3.json`(v2 대체, v2 파일 삭제). 사용자 재import 필요.

## 2026-07-15 — 세션2 (진범 확정: IF 노드 구조 오류 → v4)

- **v3 라이브 검증에서 이상 지속**(전 질의 0건·0초, 이미지 비전은 정상 동작 21s·image_notes=1).
  n8n DB의 실행 기록 정밀 분석: 실행 82가 `cache_hit:false`인데 **TRUE 분기로 라우팅**됨을 확인.
- **근본 원인(전체 사건의 단일 진범)**: 내가 손으로 만든 '캐시 유효?' IF 노드의 parameters 구조가
  n8n IF v2.2 스키마와 다름 — 원본은 `parameters.conditions.{options,conditions,combinator}` 중첩인데
  내 것은 한 단계 평탄화. n8n이 조건을 못 읽어 **항상 TRUE(히트) 분기** → v2에선 매 요청 프리페치
  크래시(74~81 전부 error), v3에선 매 요청 빈 캐시 폴백(0건). miss가 한 번도 안 돌아 캐시도 영원히 빈 상태.
- **v4**: '캐시 유효?'를 검증된 '즉시 응답?' IF와 동일한 중첩 구조로 재생성 + 방어 2건(빈 캐시=미스 취급,
  빈 조회 결과는 캐시 기록 생략). 검증 6항목 전부 통과(IF 구조 일치·프리페치 안전 포함). v3 파일 삭제.
- **교훈**: n8n 노드를 손으로 지어내지 말 것 — 반드시 같은 워크플로의 검증된 동종 노드 parameters를
  복제해서 값만 바꾼다. 신규 노드는 실행 기록(execution_data)으로 분기 라우팅까지 확인해야 검증 완료.
- 발견: 동명 워크플로 7개 누적(반복 import) — 활성 1개 외 6개 삭제 권고(사용자).

## 2026-07-15 — 세션2 종결 (v4 라이브 검증 전부 통과 — #34/#36 완결)

- **3종 프로브 전부 성공**: ①MISS 17.9s "진행 33건"(실데이터, Notion 조회+캐시 기록)
  ②HIT 4.7s "계획 154건"(**3.8배 빠름**, Notion 조회 스킵) ③이미지 28s action=QUERY(대화형),
  1px 프로브 이미지를 "아주 작은 단색(분홍 계열)"로 정확 묘사, image_notes 컨텍스트 영속.
- **실행 기록 확정**: exec85 miss(cache_hit=false→조회→기록), exec86/87 hit(true→스킵),
  workDataCache staticData 영속(task-runner 쓰기 반영도 정상). 분기 라우팅 완전 정상.
- **#34(Notion 챗봇 재설계) + #36(이미지 파이프라인) 라이브 완결**: 조회(자유질의)+생성(LLM 초안)+
  수정(LLM 폴백+확인)+이미지(추출·대화추론·본문반영)+5분 캐시. 남은 후속 = #39 바이너리 첨부.
- 운영 참고: n8n에 동명 워크플로 7개(활성 1) — 비활성 6개 삭제 권고(사용자).

## 2026-07-15 — 세션2 (대화형 전환 + 버그사냥 13건 + 러너 3.4.0)

- **대화형 챗봇 전환(사용자 피드백 "예측 못한 답변에 에러, 잡담도 돼야")**: 규칙 미매칭 → UNSUPPORTED
  거부 대신 **대화 레이어(claude_query)로 폴백**. 잡담 하드거부 키워드(날씨·메뉴·뉴스 등) 삭제,
  실행형(메일 발송 등)만 명시 거절 유지. QUERY 프롬프트를 범용 비서 페르소나로 재작성(실시간 정보
  한계 솔직 안내, 잡담↔업무 자유 전환, 승인 대기 중 잡담 시 pending_note로 상기). 승인 대기 분기의
  막다른 안내들도 대화로 대체. CLI 일시 실패 1회 재시도+서버 stderr 로깅+자연 안내문.
- **매핑 관문 제거(사용자 보고 "나한테 할당된 티켓이 거부됨")**: 플랫폼의 미매핑 1인칭 차단 삭제 —
  러너가 이름/이메일로 해석(검증됨: 실데이터 6건 반환). 매핑은 정확도 보조로 존치. 위조 불가 불변
  유지 테스트 포함.
- **버그사냥 루프(18에이전트) 확정 13건 전부 수정**: [CRIT] 세마포어 누수→429 동결(전 구간 try/finally)
  · [HIGH] 500이 str(exc) 노출(traceback은 서버 로그로)· 취소 후 에코 컨텍스트 부활(톰스톤 rev+1)·
  승인 중복 디스패치(dispatched_at 가드+재시도 우회)· CLI 데드라인(비전+본호출 단일 창) · [MED]
  대화별 턴 직렬화 락·413 영구잠금(에코 폐기+persist 2단 강등)·ticket_selection 원문 병합·스윕 경쟁
  (신생 디렉터리 보호+저장 재시도)·시간 기반 TTL 스윕 데몬·context/sync 크기 상한. 기각 2건.
- 러너 테스트 **31 green**, 플랫폼 전체 green+STATIC_CHECKS_OK. **3.4.0 배포**(백업 bak-20260715-210119)
  + 라이브 3종 검증: 잡담(날짜 정답·한계 솔직)·내 티켓(실데이터 6건)·잡담→업무 전환. 커밋 7f6febf.
- **대기**: 플랫폼 매핑 차단 제거는 전체 업그레이드 필요(번들 재업로드됨). v5(이미지 첨부 체인)는
  import됨 — 다음 실제 티켓 생성 시 라이브 확인.

## 2026-07-15 — 세션2 (#39 완결: 이미지 원본 Notion 첨부 라이브 검증)

- **3단계 장애를 순차 해결**: ①토글 미리로드(n8n은 저장만으론 실행 버전 안 바뀜 — Active off/on 필수,
  실행 스냅샷(execution_data.workflowData)으로 판정) ②n8n 파일접근 허용목록(기본 ~/.n8n-files만) →
  러너 이미지 저장소를 `/home/n8n/.n8n-files/clovirone-work-assistant-images`로 이전(3.4.1, 기존 파일
  마이그레이션) ③러너 systemd ProtectHome=read-only가 새 경로 차단 → drop-in
  (`/etc/systemd/system/claude-work-assistant.service.d/image-store.conf`, ReadWritePaths 추가).
- **e2e 확정(flatted 완전 디코드)**: 첨부 필터→업로드 생성(file_upload id)→전송→**이미지 블록 생성**
  (parent=생성된 티켓 페이지). v6 워크플로. 테스트 티켓 3개 생성됨(사용자 삭제 예정).
- **운영 교훈**: n8n 워크플로 교체 후 반드시 Active 토글 off/on. 실행이 어떤 버전으로 돌았는지는
  execution_data의 workflowData 스냅샷으로 확인.

## 2026-07-15 — 세션2 (개선 프로그램 착수: 디스커버리 + P0 1차)

- **디스커버리(4축 감사, 16에이전트)**: 갭 32건(P0 8·P1 16·P2 8) → `docs/IMPROVEMENT_BACKLOG.md` 영속.
- **P0 1차 4건 구현·배포(러너 3.5.0 + chat.js 핫배포, 러너 35 green)**:
  ①claude_query가 참조 티켓 id를 last_results로 기록 → 대화형 답변 직후 "두 번째 티켓" 참조 정상
  ②freeform 직후 "더 보여줘" → 전체 티켓 덤프 대신 대화 이어가기
  ③2페이지에서 화면 범위 밖 맨 번호("2번") → 추측 금지·범위 안내(잘못된 티켓 직접 쓰기 차단)
  ④티켓 카드의 담당자/프로젝트가 죽은 키(assignee/project)여서 **한 번도 표시된 적 없음** →
  배열 필드(assignees/project_names) 렌더 + LLM 경로 카드에 Notion url 추가.
- **P0 잔여 4건(다음 턴 즉시)**: 시작일 변경 오기록(마감일로 기록됨), 제목 변경 미지원+상태 오발사,
  "내가 만든 티켓" 침묵 오답(created_by 수집+MY_CREATED 스코프+미지원 축 정직 안내). 이후 P1 16건.

## 2026-07-15 — 세션2 (P0 2차: 시작일/제목/생성자 축 — 러너 3.6.0)

- **P0 잔여 4건 구현·배포·라이브 검증**: ①시작일 변경 오기록(마감일→) 수정 — 날짜 채널이 사용자가
  말한 필드를 따름(write mapping에 시작일 추가) ②제목 변경 지원 + 새 제목 속 상태어("배포 완료
  안내")가 상태 변경으로 오발사되지 않게 제목 구문을 필드 추출에서 제외(write mapping에 제목 추가)
  ③"내가 만든 티켓" = created_by 필터(normalize_ticket이 page.created_by 수집, n8n 묶기 노드가
  페이지 통째 전달 확인) — **라이브 실데이터 2건 검증**. 요청자/참여자 축은 정직 안내 — 라이브 검증
  ④(부수 발견) ISO 날짜+한글 조사("2026-08-01로")를 유니코드 \b 경계 탓에 못 잡던 파서 결함 수정.
- 러너 **38 green**, 3.6.0 배포(백업 bak-20260715-222500). **백로그 P0 8/8 완료** — 다음 = P1 16건
  (시작일 조회 축·그룹화/SUMMARY·상대날짜 정책·라우팅 경계·카드 상세진입/중복렌더·quick prompts
  개편·n8n 오류 안내 등, docs/IMPROVEMENT_BACKLOG.md).

## 2026-07-15 — 세션2 (P1 웨이브 A — 러너 3.7.1)

- **P1 6건 완료·라이브 검증**: ①그룹화/현황 요약 — 상태별/프로젝트별/담당자별/우선순위별 결정론 집계
  렌더(SUMMARY 죽은 분기 해소, 라이브: "상태별로 정리" → 6건 집계+제목) + freeform 마커('정리')가
  그룹 요청을 LLM으로 뺏던 라우팅 가드(3.7.1) ②상대 날짜 — 지난주/어제/지난달/N주 뒤 인식(라이브:
  "지난주 마감 5건") ③라우팅 경계 — '알려줘/어떤' 마커 제거(정형 질의는 규칙 엔진 고정) ④삭제 정직
  안내(취소 상태 대안+Notion 안내) ⑤LLM 잘림 고지(800/300건 초과 시 수치 단정 금지 지침)
  ⑥LLM 카드 Notion 링크(3.5.0에서 선반영 확인). 러너 **43 green**.
- **P1 잔여 10건**: 시작일 조회 축(#16), LLM 경로 구조화 질의 미저장(#9), CREATE 모드 고착(#10),
  n8n 실패 안내(#12), 일괄 변경(#14), 실행 후 재조회(#15), UI 3건(#21 중복렌더·#22 상세진입·
  #23 quick prompts), 프로젝트 카드(#24). 다음 턴 = UI 3건(핫배포 가능) 우선.

## 2026-07-15 — 세션2 (P1 UI 웨이브 — 3.7.2 + UI 핫배포)

- **P1 3건**: #21 목록 텍스트/카드 이중 렌더 제거(텍스트=요약문+페이징 힌트, 카드=본체) ·
  #22 카드 번호 배지(러너 start_index와 동기 — "N번" 후속 참조와 화면 일치)+'상세' 버튼 ·
  #23 새 대화 추천 7개 개편(그룹 요약·기간 개수·생성자 축·생성 포함, 조회 편중 제거).
- 러너 43 green, 3.7.2 배포, UI 핫배포(served-markers 검증). **P1 9/16 완료.**
- **P1 잔여 7**: #16 시작일 조회축, #9 LLM 구조질의 미저장, #10 CREATE 모드 고착, #12 n8n 실패
  안내, #14 일괄 변경(L), #15 실행 후 재조회, #24 프로젝트 카드 확장.

## 2026-07-15 — 세션2 (P1 11/16 — 러너 3.7.3)

- #16 시작일 조회 축(필터가 field 보유, 라벨에 '시작일' 명시) · #12 최종 실패 시 대화 내 원인+다음
  행동 안내(시간초과/연결 구분 — 플랫폼 변경이라 **다음 업그레이드에 탑승**, 번들 동기화됨).
- 러너 44 green·플랫폼 전체 green·3.7.3 배포. **P1 잔여 5**: #9 LLM 구조질의 미저장, #10 CREATE
  모드 고착, #15 실행 후 재조회, #24 프로젝트 카드 확장, #14 일괄 변경(L).

## 2026-07-15 — 세션2 (P1 14/16 — 러너 3.8.0, P1 사실상 완료)

- #10 CREATE 고착 해소(생성 중 조회/현황이 빠져나가고 초안 유지·재개) · #9 freeform 잔재의 승계
  오염 차단(조건 수정이 전체 티켓으로 리셋되던 것) · #24 프로젝트 목록/카드에 진행 중 티켓 수와
  담당 정/부(라이브: 5건+112건 집계). 러너 **47 green**, 3.8.0 배포+chat.js 핫배포.
- **연기 2건(근거)**: #15 실행 후 재조회 — n8n 응답이 이미 실제 쓰기 응답(page 객체)에서 생성되어
  부분 충족, 전후 값 표시는 다음 n8n 개정에 배치 / #14 일괄 변경(L) — 다건 쓰기 안전 흐름
  (미리보기+대상 수 확인) 설계 포함 단독 배치 필요.
- **다음**: 지시서 15.5 검수 루프(이번 배치 변경분 적대 검증) → P2 8건 선별.

## 2026-07-15 — 세션2 (15.5 검수 루프 확정 10건 수정 — 러너 3.9.0)

- **배치 검수(14에이전트, 2렌즈+반박) 확정 10건 전부 수정**:
  [HIGH] ①실패 안내 message_id 고정 접미사 → 재시도 재실패 시 unique 충돌·트랜잭션 롤백·'처리 중'
  영구 고착 → job.id 포함 ②제목 정규식 과탐("제목은 그대로 두고 마감일을…" 전체를 제목으로 캡처,
  실제 변경 소실+무확인 직접쓰기) → 조사 필수+필드 키워드 lookahead 차단 ③삭제 안내의 '그 티켓'
  예시가 stale selected_ticket 오타겟 직접쓰기 유발 → 선택 해제+제목 기반 예시.
  [MED] CREATE 탈출 맨명사('목록/현황/조회')가 필드 답변 강탈 → 명시적 질의형만 / 시작일 채널이
  '마감' 공존 시 뒤집힘 → 마감 우선 가드 / 그룹 가드가 추론형('진행률/분석') 가둠 → 추론 마커 시
  LLM 유지 / chat.js 절단이 WORK_SUMMARY 집계 파괴 → start_index 게이트 / MY_CREATED 봇 생성 누락
  침묵 → 고지 추가. [LOW] '진행 중'→'미완료' 라벨 정직화.
- P2-#31(프로젝트 색칩+상태 배지색, 다크 대응) 동시 배포. 러너 **53 green**, 3.9.0+UI 핫배포, 번들 동기화.
- **잔여**: P2 #25/#26/#29/#30(S급 4)·#27 댓글(M)·#28 본문(L)·#32 버튼화(M), P1 연기 2(#14/#15),
  사용자 업그레이드 1회(플랫폼분: #12 실패안내+id 수정).

## 2026-07-15 — 세션2 (P2 계속 — 러너 3.9.1)

- #26 COUNT 유령 번호 제거(비가시 목록 참조 차단, last_query는 유지해 "목록으로" 후속 가능) ·
  #30 정렬 축 3종(최신순/시작일순/난이도순)+사용자 페이지 크기("N개씩", 1~50 캡). 러너 55 green.
- 잔여 P2: #25 followup 과승계(S), #29 무따옴표 검색(S — 오탐 설계 신중), #27 댓글(M, n8n comments
  필요), #28 본문 blocks(L), #32 확인/선택 버튼화(M).

## 2026-07-15 — 세션2 마감 (P2 5/8 — 러너 3.9.2, 번들 최신화)

- #25 자기 주어 질의(검색어/생성자 축)의 stale 필터 상속 차단(3.9.2). #29 무따옴표 검색은 오탐 해악
  근거로 보류(자연어 검색=LLM 경로가 커버). 러너 55 green. 번들 동기화(플랫폼분 대기: 실패안내+id
  충돌 수정 — 사용자 업그레이드 1회).
- **프로그램 누계**: P0 8/8 · P1 14/16(2 연기) · P2 5/8(1 보류, #27 댓글·#28 본문·#32 버튼화 잔여) ·
  15.5 검수 10/10. 러너 3.5.0→3.9.2(9회 배포, 매회 백업+헬스+자동롤백), 라이브 프로브 9종 통과.

## 2026-07-15 — 세션2 (P2-32 배포 + n8n v7 + 댓글 3.11.0 준비)

- **#32 원탭 버튼 배포**(3.10.0+UI): 러너 choices[{label,send}] 공통 구조 — 프로젝트/티켓 선택,
  생성/변경 미리보기에 버튼. UI는 **마지막 어시스턴트 메시지에만** 렌더(stale 승인 오발송 차단),
  send=타이핑 문장과 동일이라 라우팅·안전장치 불변.
- **n8n v7 생성·검증(11항목)**: '댓글 작성?' IF(검증 구조 복제)+'Notion 댓글 작성'(POST /v1/comments)
  +'Notion 변경 결과' COMMENT 분기+**UPDATE 적용값 표시**(실제 page 응답에서 추출, §9.3=#15).
  파일: Downloads\...\ClovirONE_AI_Work_Assistant_v7.json.
- **러너 3.11.0 커밋(배포 보류)**: 댓글 의도/추출/write_request(kind=COMMENT). 57 green.
  **순서: 사용자 v7 import+토글 off/on → 러너 3.11.0 배포**(v6에 COMMENT 보내면 400).
- 잔여: #28 본문 blocks(L, 보류 — 대량 조회 비용), #29 보류, #14 일괄(L).

## 2026-07-16 — 전면 제품 검수 (러너 3.11.0 → 3.27.0)

**이어받은 작업 완결**: n8n v7의 `Notion 변경 결과` Code 노드에 문자열 안 줄바꿈으로 인한 JS 문법
오류가 있어 **쓰기 경로(생성·변경·댓글) 전체가 죽어 있었다**(조회는 정상이라 눈에 안 띄었다).
웹훅은 응답 없이 끝났다. 고치고 티켓 생성·댓글·프로젝트 없는 티켓 생성을 라이브 확인.

**⚠️ n8n 수정 규칙(중요)**: `workflow_entity.nodes`를 raw SQL로 UPDATE하면 **n8n이 읽는 상태와
갈라진다**. python으로 다시 읽으면 수정본이 보이는데 `n8n export:workflow`는 옛 코드를 내보내고
실행 스냅샷에도 옛 코드가 찍힌다(완전 재시작해도 동일). 40분을 태웠다.
→ **CLI만 사용**: 로컬 JSON에 `"id": "<live id>"` 넣고 `n8n import:workflow` →
`n8n update:workflow --id=<id> --active=true` → `systemctl restart n8n` → **`export:workflow`로 되읽어 검증**.
Code 노드는 import 전에 `node --check`(async function으로 감싸서).

**검수 방식**: 8개 도메인 병렬 검수 → 주장마다 별도 검증자가 반증 시도 → 통과분만 수정.
1차 48건 확정(기각 6), 수정 후 2차 26건 확정(기각 6). 2차 확정의 상당수가 1차 수정이 만든 회귀였다.
기록: `docs/product-quality-audit/` 9종.

**공통 원인**: 낱말을 문장 어디서든 부분일치시켜 조건으로 삼은 것. 제목의 '완료'가 상태를 뒤집고,
이름 '남기훈'의 '남'이 완료 조회를 끄고, '중간 점검'의 '중간'이 우선순위 필터가 됐다. 결과는 0건
아니면 정반대 데이터. **0건에는 오류 표시가 없어 사용자는 데이터가 없다고 믿는다.**
→ 낱말은 '지시된 위치'에서만 조건이 된다(앵커 템플릿, 어순, 연속 일치).

**두 번째 교훈**: "이름을 못 찾으면 정직하게 말한다"는 수정이 못 알아들은 조건까지 이름으로 단정해
"내가 담당하는 티켓 보여줘"에 "찾지 못했습니다"라고 답했다(치명적 회귀). 단정은 구분 가능할 때만.

**보안**: 작업 큐가 operator에게 타인 채팅 원문·이메일·첨부 원본 노출(대화 API는 403인데 우회로),
스케줄 run-now/retry가 승인 게이트 우회, 문서 무승인 발행, 승인 TOCTOU, 댓글 소유권 미검사,
동명이인 매핑, n8n 재전송 캐시가 message_id만으로 키를 만들어 타인 응답 반환 — 전부 수정.

**n8n 숨은 결함**: '조회 및 질문 응답' 노드가 허용목록으로 응답을 재구성하며 `choices`와
`start_index`를 떨어뜨리고 있었다. **원탭 선택 버튼 기능(P2-32)이 통째로 죽어 있었다.**
러너에 응답 필드를 추가하면 이 노드도 함께 고쳐야 한다.

**검증**: 러너 109 / 플랫폼 451 / 화면 JS 32(하네스 신규) 통과, STATIC_CHECKS_OK.
라이브 12개 여정 정상(그중 9개는 수정 전 0건 또는 정반대 데이터).

**남은 것**: 브라우저 실화면 검증(#42), 이미지 첨부 라이브 검증(#43), n8n staticData 정리(#44).
**사용자 조치**: 검수 중 실제 고객 티켓에 검증용 댓글이 달렸다(Notion API로 삭제 불가) —
https://app.notion.com/p/329c5c5a568480ea88b2cef09c93090d 에서 직접 삭제 필요.

## 2026-07-16 — 로그인 전후 디자인 일관성 (브랜드 토큰 통일)

**문제**: 사용자가 "로그인 전후가 다른 제품처럼 보인다"고 지적. 원인은 팔레트가 두 벌이었던 것.
로그인만 `login.css`의 `--lg-*`(브랜드 #536CD6 계열)를 쓰고, 로그인 이후는 `tokens.css`의
`--color-primary: #4F46E5`(Tailwind indigo)를 썼다. **브랜드 로고 SVG 자신이 #536CD6/#435CBE/#758AE1로
그려져 있어, UI가 자기 로고와 다른 색을 쓰고 있었다.**

**조치**: `tokens.css`를 디자인 시스템 원본(`Downloads/ClovirONE Design System/clovirone/tokens.css`)
기준으로 다시 쓰고 모든 화면이 그 하나만 보게 했다. 로그인 CSS 복사가 아니라 값의 출처를 옮긴 것.
primary #4F46E5→#536CD6, 사이드바 #0F172A→#141B34(브랜드 잉크), 테두리 #E2E8F0→#DEE4F5(쿨),
배경 #F4F7FB→#F8FAFF, 본문 #172033→#333333, 그림자 슬레이트→푸른 캐스트, 사이드바 너비 240/260→260.
`--color-secondary`(청록)는 브랜드에 없어 삭제. 토큰 45 정의 / 45 참조(죽은 토큰 0).

**색을 손대다 드러난 접근성 결함(측정값)**: 배지 글자가 자기 틴트 위에서 AA 미달(info 3.91,
success 4.14, warning 4.15) → 글자만 짙게. 다크에서는 반대로 되돌린다(라이트용 짙은 글자를 다크에
두면 1.75). primary 위 흰 글자 다크 3.24 → `--color-on-primary`(잉크, 5.24). 토스트 다크 1.67 →
`--color-on-status`. 로그인 화면 자체도: 서버 연결 표시 **1.94**(안 보임), 푸터 2.43, 힌트 3.19,
표시 버튼 3.14, 버튼 흰 글자 4.22 → 전부 4.5 이상.

**브랜드**: 비밀번호 변경 화면이 **흰 글자 워드마크를 흰 카드 위에** 얹어 브랜드 이름이 안 보였다
(첫 로그인 사용자가 반드시 거치는 화면). `clovirone-wordmark-dark.svg`로 교체.

**의도한 편차**: DS의 내부 화면(Dashboard.html)은 흰 사이드바 + 그라디언트 상단바다. 우리는 어두운
사이드바 유지(스펙 §24.1, 지금은 브랜드 잉크라 히어로와 이어짐). 폰트 Pretendard는 단일 TTF 6.7MB라
시스템 스택 유지(로그인도 원래 같은 스택).

**검증**: 로그인 계산색 수정 전후 완전 동일(회귀 0). 채팅/관리자 실브라우저에서 브랜드 잉크·인디고 확인.
다크 포함. 플랫폼 451 / 러너 109 / 화면 JS 32 통과, STATIC_CHECKS_OK.
기록: `docs/product-quality-audit/DESIGN_CONSISTENCY_REVIEW.md`.

**주의(하네스 함정)**: 검증 하네스가 `window.fetch`를 가로챈 상태에서 fetch로 정적 파일을 검사하면
자기 스텁을 읽는다(admin.css가 41바이트로 보이는 오탐을 겪었다). 파일 검증은 서버에서 직접 하라.

## 2026-07-16 — 로그인 이후 화면 재디자인 + 검수 3라운드

**사용자 피드백이 출발점**: "https://clovirone-ai.gooddi.lab 로 보면 사용자 페이지·관리자 페이지에
변한 게 없다." → 확인해 보니 **적용은 돼 있었다**(사용자 브라우저의 살아있는 세션에서 사이드바
`#141B34`·버튼 `#536CD6` 실측, 서비스 워커 없음, HTML `no-store`, CSS는 새 지문 주소로 캐시됨).
그런데 사용자 말도 맞았다 — **색만 바꿨고 레이아웃은 한 픽셀도 안 바뀌었다.** 이전 색(#4F46E5)과
브랜드(#536CD6)는 둘 다 인디고라 기억과 비교하면 알아채기 어렵다.

이어서 "눈에 띄는 재디자인(레이아웃·컴포넌트 변경)도 나는 원했었음" → **1차의 '의도한 편차'가
잘못된 판단이었다.** 디자인 시스템 `ui_kit/Dashboard.html`이 로그인 이후 화면 설계를 이미 갖고
있는데 "업무 화면 전체 정보 구조를 다시 짜는 일이라 범위를 넘는다"고 밀어낸 것이 문제였다.

### 재디자인 (플랫폼 458 → 러너 3.30.0)

- **50px 브랜드 그라디언트 상단바** 신설: `app/static/css/topbar.css` + `app/templates_html/_topbar.html`.
  채팅과 관리자가 **파일 하나를 공유**한다(로그인 CSS를 복사하지 않았던 것과 같은 원칙).
  로고 · **사용자/관리자 세그먼트**(우리 제품 구조와 정확히 맞음, 일반 사용자에겐 안 보임) ·
  **알림 벨**(`/api/notifications/unread-count` 실제 값, 0·실패면 감춤) · 인사말 · 아바타.
- **사이드바 흰 면 + 우측 그림자**로 전환. 어두운 면은 이제 상단바가 맡는다.
- 관리자에 **브레드크럼 + 22px/800 페이지 제목** 관례 도입(`--color-heading` #1B2235 신규).
- **안 넣은 것**: 데모의 검색창·KR|EN·"담당자 010-1234-5678". 우리 제품에 그 기능이 없다.
  껍데기 UI와 전화번호 하드코딩은 금지 원칙 위반이다.

### 디자인 시스템도 검증했다 — 두 곳이 AA 미달

| 자리 | DS 값 | 대비 | 조치 |
|---|---|---|---|
| `--g-top-bar` 41% | `#7EBCD4` | **2.09** | `#347F9C` (4.50) |
| `--g-top-bar` 98% | `#8E7ED4` | 3.45 | `#7A67CC` (4.50) |
| 사이드바 활성 글자 | `#758AE1` on `#EAF0FF` | **2.84** | `--color-primary-strong` (5.24) |

그라디언트는 **HSL 색상·채도를 한 도도 안 바꾸고 명도만** 낮췄다. 브랜드의 색 여정은 그대로이고
흰 글자가 가로 어디에 놓여도 통과한다(전 구간 최악 4.53). 데모(1920px)는 41%가 빈 공간이라 이
문제가 안 드러났지만, 우리 상단바는 오른쪽 글자 묶음이 60~98%에 걸린다.

**내가 만든 결함도 배포 전에 잡았다**: DS의 흰색 반투명(`rgba(255,255,255,.08)`)을 그대로 쓰니
흰 틴트가 배경을 밝혀 그 위 흰 글자가 **3.50**(아바타 **3.19**)이 됐다. DS의 그라디언트가 더 밝아서
성립하던 값이다. 잉크 틴트 22%로 뒤집어 6.06.

### 드로어가 열리면 첫 메뉴를 누를 수 없던 문제 (양쪽 화면)

로고가 상단바로 가자 사이드바 맨 위를 **첫 메뉴 항목**이 물려받았는데, 헤더가 드로어 위로 떠 있어
(z-index 45 > 40) 헤더 제목이 그 버튼을 덮었다. **실측 36px 중 34px, `elementFromPoint`가 H1 반환**
(채팅은 '+ 새 대화'가 33/40px). 예전엔 그 자리가 로고(장식)라 아무도 몰랐다 — 모바일에선 보이지도
않았다. 헤더를 안 올리는 쪽으로 바꿨고 **수정 후 실측 0px, 드로어 열린 채 상단바 클릭 가능**.
`admin_drawer_test.js`가 이 결함을 핀으로 잡고 있었다("헤더 z-index 45 > 사이드바 40") —
**테스트가 결함을 지킬 수 있다.**

### 두 화면이 갈라져 있던 것들 (통일)

모바일 분기점 768/860 → **860**, 드로어·백드롭 z-index 30·25 / 40·35 → **40·35**,
헤더 z-index → **둘 다 없음**, `active_area` 템플릿/라우터 → **라우터**,
로그아웃 id `logout-button`/`admin-logout` → **`logout-button`**.

### 전체 회귀 검수 3라운드 (55건 제기 → 31 확정 / 24 기각)

`Workflow` 9관점 병렬 + 주장마다 서로 다른 렌즈의 반증자 3명. 확정 31건(Critical 1·High 13·
Medium 11·Low 6, 회귀 9). 주요 수정:

- **[HIGH·회귀] 지문 캐시가 문서화된 절차를 무효로 만듦** — `assets.py`가 지문을 프로세스 수명
  동안 고정했는데 문서는 "정적 파일만 바꿀 때 재시작 불필요"라고 안내한다. 그대로 하면 캐시
  버스팅이 통째로 무효 = **사용자가 겪은 "안 바뀐다"의 진짜 원인**. 이번엔 내가 재시작해서 우연히
  적용된 것이었다. 매 요청 stat으로 수정. 기존 테스트는 `cache=False`로만 확인해 통과하는 동안
  운영(`cache=True`)은 깨져 있었다 → 운영 설정으로 회귀 테스트 추가(옛 구현에서 RED 확인).
- **[CRITICAL] 러너가 못 알아들은 조건을 '그런 프로젝트 없다'고 단정** — "프로젝트 전체에서 배포
  실패 티켓 보여줘"가 0건 + 지어낸 프로젝트 이름. `names_a_project`가 '프로젝트'라는 낱말의 존재만
  봤다. 이제 실제로 이름을 지목한 증거를 요구한다.
- **[HIGH] '제목 다시 해줘'가 retry로 읽혀 Notion에 티켓 중복 생성** — 중복 방지 가드를 우회했다.
  "이 가드가 없어서 티켓이 중복됐다"는 주석이 가리키던 사고가 되돌아왔다.
- **[HIGH·회귀] n8n dedupe가 이름만 있는 요청자를 전부 anonymous로 뭉갬** — 남의 티켓 제목·URL·
  대화 문맥이 그대로 반환됐다. 러너의 `requester_state_key`와 같은 순서·정규화로 맞춤.
- **[MEDIUM] 도움말·안내 문구에 '용인 프로젝트'·'민지원' 하드코딩** — 워크스페이스의 실제
  프로젝트와 물어본 본인 이름에서 뽑는다. 스윕으로 변경 안내(3490행)에도 같은 하드코딩 발견.
- **[MEDIUM] 첨부 사진이 TTL로 사라져도 사용자가 모름** — n8n 첨부 체인은 막다른 길이라(마지막
  노드에 나가는 연결 없음 + 전부 `continueRegularOutput`) 실패가 응답에 합류 못 한다. 승인 시점에
  러너가 보관소를 확인해 알려준다. 못 읽는 상황에선 침묵한다(거짓 경고 금지).
- **[MEDIUM] 비밀번호 변경 화면만 테마 미적용** — 테마 로직이 두 파일에 복붙돼 있고 이 화면만
  빠졌다. 공용 `theme.js`로 추출.

**기각 24건**은 반증자 다수가 근거를 무너뜨린 것들이다.

**측정 도구를 먼저 의심하라 (이번에도 세 번)**: 배경 탭은 rAF·CSS transition·프레임을 돌리지
않는다. `await requestAnimationFrame`은 영영 안 오고 `Page.captureScreenshot`은 타임아웃한다.
"채팅 화면이 멈췄다"로 잘못 읽을 뻔했으나 동기 eval은 즉시 답했다 — 제품이 아니라 관측 장비였다.

### 에이전트가 내 지시의 오류를 잡은 세 번 (이번 라운드)

셋 다 "시키는 대로 했다"가 아니라 **실제로 돌려보고 반박**했다. 이게 없었으면 결함을 심었다.

1. **러너**: 내가 "`_OWN_WORK_RE`의 수량자를 두 어절로 제한하면 `'제 동료 김민수 티켓 보여줘'`가
   고쳐진다"고 했다. 실행해 보니 **안 고쳐진다** — 그 문장은 정확히 두 어절이라 정상 표현
   (`'제가 맡은 급한 업무'`)과 구분되지 않는다. 대신 관형형 어미로 판정하는 방식을 만들었다.
2. **채팅**: 내가 프로젝트 점 색을 `--color-accent-sky`로 쓰라고 했다. 재보니 **라이트 배경 위
   2.00** — 다크의 결함을 라이트로 옮길 뻔했다. 대비를 넘는 5톤만 골랐다.
3. **채팅**: 검수가 "chat.css 주석이 태어날 때부터 거짓"이라고 확정했는데, 그 주석은
   **저장소 어느 리비전에도 없다**(`git log -S` 0건). 검수도 틀린다. 없는 것을 지어내
   고치는 대신 주석의 주장을 테스트로 박았다.

### 조용히 통과하는 테스트가 가장 위험하다

`chat.js`에 `window.addEventListener("resize", …)`를 넣었더니 테스트가 **첫 줄만 찍고 exit 0**으로
끝났다. 하네스의 `window` 스텁에 `addEventListener`가 없어 chat.js가 던졌고, 그 예외가 async
경계에서 삼켜진 것이다. **실패가 통과로 읽혔다.** 스텁에 이벤트 API를 넣고 부팅 예외를 잡아
exit 1로 죽이게 고쳤다(옛 스텁 재현으로 실제 exit 1 확인).

같은 계열: 채팅 에이전트가 주석을 고치다 `*/`를 하나 더 남겨 CSS를 깨뜨렸는데 **정규식 테스트는
전부 통과했다.** 파일을 다시 읽어 발견하고 구조 검사(주석 짝·중괄호)를 추가했다.
**정규식으로 CSS를 검사하면 깨진 CSS도 통과한다.**

### 내가 만든 회귀 (분기점을 옮기고 반쪽만 고침)

`chat.css`의 모바일 분기점을 768 → 860으로 옮기면서 `chat.js`의 `window.innerWidth <= 768`을
두고 갔다. 800px 화면에서 드로어는 열리는데(CSS) 대화를 골라도 안 닫힌다(JS). 지금은 네 곳
(chat.css / chat.js / admin.css / admin/app.js)이 전부 860이고 JS는 상수로 두어 CSS와 같은 값임을
명시한다. **CSS 분기점을 바꾸면 그 값을 읽는 JS를 반드시 함께 찾아라.**

### 검수 결과를 표결로만 믿지 않는다

"admin이 `approval_required`를 꺼서 승인 게이트를 우회한다"가 반증 2/3으로 기각됐는데, 반증에
실패한 한 명은 **익스플로잇을 실제 앱에 대해 실행해 재현**했다. 보안 항목이라 직접 확인했고,
기각이 옳았다 — 워크플로 수정과 승인 결재가 같은 역할이라 권한 상승이 아니고, 스펙 §20은
자기승인 금지를 '옵션'으로 규정하며, 변경은 감사 로그에 남는다. 다만 감사자가 알아야 할
성질이라 `docs/KNOWN_LIMITATIONS.md`에 기록했다. **코드로 막지 않은 이유**: 문서화된 admin
권한을 내 판단으로 축소하는 일이기 때문이다.

### 에이전트가 동시에 돌 때 `git add -A`를 쓰지 마라

작업 중인 다른 에이전트의 파일까지 쓸어 담는다. 실제로 "로그인 저대비 수정"이라는 제목의
커밋이 러너 4건 수정과 채팅의 미완성 TDD RED 상태까지 담았다 — **이력이 거짓이 되고,
그 커밋만 보면 무엇이 왜 바뀌었는지 알 수 없다.** 아직 push 전이라 `reset --soft`로 쪼갰다.

세션 초반에 다른 에이전트가 `git stash`로 남의 작업을 쓸어간 것과 같은 계열이다.
**파일을 이름으로 지정해서 add 한다.** 무엇을 고쳤는지 아는 사람이 그것만 담는다.

### 측정 도구를 먼저 의심하라 (이번 라운드에만 두 번 더)

1. **`color(srgb 1 1 1 / 0.78)`**: 브라우저는 `color-mix()` 결과를 0~1 실수로 돌려주는데
   내 파서가 0~255로 읽었다. 저작권 문구가 1.35, placeholder가 **20.06**으로 나왔다.
   20.06은 물리적으로 불가능한 값이라(최대 21) 제품이 아니라 파서를 의심했고 그게 맞았다.
   고친 뒤 실제 값은 4.93 / 4.60이다.
2. **배경 탭**: rAF도 CSS transition도 프레임도 돌지 않는다. `await requestAnimationFrame`은
   영영 안 오고 `Page.captureScreenshot`은 타임아웃한다. "채팅 화면이 멈췄다"로 잘못 읽을
   뻔했으나 동기 eval은 즉시 답했다.

**불가능한 값이 나오면 그것이 단서다.** 20.06 같은 값을 보고 "대비가 좋다"고 넘어갔으면
placeholder는 2.31인 채로 남았을 것이다.

### 내 검증 범위가 부족했던 자리

"다크 테마 미달 0"이라고 보고했는데 **상단바 안의 요소를 안 쟀다.** 벨 배지는 그때 hidden
상태였고(JS 없는 하네스), 세그먼트는 글자 대비만 보고 "선택 상태 구분"은 안 봤다.
2차 재검수가 둘 다 잡았다(2.77 / 2.60).

교훈: **"이 화면 다 쟀다"가 아니라 "무엇을 쟀는지" 목록으로 말해야 한다.** 안 잰 것은
안 잰 것이다. 지금은 상단바 내부까지 포함해 라이트·다크 양쪽을 잰다.

### 하네스가 HTML을 깨뜨려 "제품 결함"으로 보인 일

벨 배지 대비를 재려고 `hidden`을 풀면서 `3<!--`를 넣고 뒤에서 `-->`로 닫으려 했는데, 그
닫는 자리(`</span>\n  </a>`)가 벨이 아니라 **뒤쪽의 다른 요소**였다. 사이에 있던 사용자 메뉴가
통째로 주석 처리됐고, 브라우저는 정직하게 "`.topbar-user` 없음"이라고 답했다.

**하마터면 "로그아웃 수단이 사라졌다"고 보고할 뻔했다.** 문자열 카운트로 HTML엔 있는데
브라우저가 못 본다는 모순을 보고 하네스를 의심해서 살았다.

지금 하네스는 자기 검증을 한다: 가공 후 필수 요소(`topbar-user`/`-avatar`/`-greeting`)가
남아 있는지, 본문에 주석이 생기지 않았는지 확인하고 아니면 그 자리에서 죽는다.

**측정 도구가 조용히 거짓말하면 그 거짓이 제품 결함으로 둔갑한다.** 이번 세션에서만
CSP 상속, 배경 탭 rAF, `color(srgb)` 파싱, 그리고 이것 — 네 번이다.

---

## 사이클 0 (계속) — `system_admin` 화면 · AI 실대화 · 프로덕션 실사용 집계 (2026-08-08 오후)

**Opus 전수조사 단계.** 제품 코드는 고치지 않았다. 조사 도구(`scripts/ui_qa/*`)와
지속 기억 문서만 손댔다.

### 이 구간에 한 것

1. **`system_admin` 전용 4화면 최초 시각 검사.** `qa-admin`(role=admin)으로 찍은 캡처에서
   `/system`·`/setup`·`/notion-console`·`/llm-console` 이 **4장 모두 권한 거부 화면**이었는데
   하네스는 `ok`로 집계했다 — `QA-04`는 절반만 해결돼 있었다. 실계정으로 다시 찍었고
   **그 4화면에서만 새 결함 18건**(`SYS-01`~`11`, `VIS-110`~`116`).
2. **`app/sysops/` argv 를 실서버 바이너리와 대조.** 읽기 전용 11종을 직접 실행.
   - **`SYS-01`(Critical)** — TLS 인증서 교체가 `/etc/ssl/clovirone/server.crt` 에 쓰는데
     nginx 는 `/etc/clovirone-web-assistant/tls/<DNS>.crt` 를 읽는다. 두 경로가 설치
     스크립트 안에서 13줄 떨어져 있다. **성공 메시지·새 인증서 subject·만료일까지 보여 주면서
     실제로는 아무것도 바뀌지 않는다.** 올바른 경로는 이미 `settings.tls_cert_path` 에 있다.
   - **`SYS-02`** — `hostnamectl show -p` 는 systemd 255 에 **없는 verb**. `/system` 의
     호스트 이름이 영구히 "확인하지 못했습니다". 같은 파일의 `hostname.set` 은 동작하는
     폴백(`status --static`)을 이미 갖고 있다.
   - **`SYS-04`** — `FakeRunner` 는 코드와 같은 argv 가정을 공유하므로 이 부류는 **테스트로
     검증 불가능**하다. 대상 OS 대조 검사가 필요하다.
3. **AI 도우미 실대화 E2E.** 실화면에서 3턴 + 대조 실험.
   - **`AI-30`(Critical, 확정)** — 2026-07-28 에 중단된 티켓 생성 모드가 **11일 뒤 무관한
     질문을 납치**했다. `assistant.py:5156` 이 `mode=="CREATE"` 면 메시지를 보지 않는다.
     러너 문맥에 만료가 없다(첨부 사진만 24h 스윕). **대조 실험**: 같은 문장을 새 대화에서
     물으면 **정상적으로 되묻는다** → 원인은 메시지가 아니라 문맥.
   - **`AI-31`** — 의도 분류가 부분 문자열 하나("보여")로 결정돼 티켓과 무관한 질문에
     **전체 티켓 184건**을 냈다. *단, 조건 제거는 조용하지 않다* — 코드가 반드시 고지하고
     그 주석에 세 번의 회귀 이력이 적혀 있다. 고칠 곳은 앞단의 분류다.
   - **정확성은 확인됐다** — "완료 제외 7건"을 DB 로 검산해 일치. **조회 엔진은 맞다.**
4. **프로덕션 실사용 전수 집계**(`web.sqlite3` 74테이블).
   - **`USE-01`** — 승인 · 문서 자동 생성 · 스케줄 실행 · 오프보딩 · 메일 · 복구 리허설 ·
     대리 보기 · AI 사용 상한 · 공지 배너 · 주간 리포트 · 저장된 뷰 · 휴지통 = **실행 이력 0**.
   - **`USE-02`** — `jobs` 130건이 전부 `chat_message`(128) + `notion_mapping_sync`(2).
   - 그중 하나(**저장된 뷰**)를 끝까지 돌려 보니 **완전히 정상 동작**했고 DB 에 1행 남았다.
     → "0행"이 "고장"을 뜻하지 않는다. 질문은 "동작하는가 + 왜 아무도 안 쓰는가"다.
5. **하네스 자체 결함 3건.** `tiny_text` 가 1920 캡처에서 전부 skip 돼 요약표가 "문제 없음"으로
   읽혔다(3840 재실행 시 **6/6 실패**, `QA-10`) · 권한 거부를 "데이터 없음"으로 오보고(`QA-11`) ·
   역할로 못 보는 라우트를 `ok` 로 집계(`QA-12`).

### 이 구간에 **철회한** 것 (중요)

- **「클로비가 ~를 가린다」 계열 7건 전부 철회.** `full_page=True` 스크린샷은
  `position:fixed` 를 뷰포트 좌표대로 캔버스에 한 번만 그려서, 6,000px 페이지에서는 우연히
  어떤 행의 버튼 위에 찍힌다. 살아 있는 DOM 으로 재니 **60라우트 중 1건**, 긴 표 8종 ×
  스크롤 4위치에서 **0건**. **하네스의 `fab_overlap` 은 내내 옳았고, 정확한 검사가 통과한 것을
  내가 PNG 로 반박했다.** → `DECISIONS` D-23.
- `USE-03`(저장된 뷰 빈 상태 없음) — **클릭해 보지 않고 판정했다.** 실제로는 잘 만들어져 있다.
- `VIS-107~109`(지금 오류가 나 있다) — **전부 3주 전 것**이고 원인 하나는 이미 고쳐졌다.
  진짜 문제는 **아무도 3주간 재시도를 안 눌렀다**는 것(`VIS-108R`).

살아남은 것 중 실측으로 **강해진** 것: `VIS-113` — 관리자 내비 37항목 중 **16개(43%)가
1920×1080 에서 화면 밖**, 900 에서 20/37, 768 에서 23/37.

### 새로 만든 조사 도구

`scripts/ui_qa/ai_e2e.py` · `ai_probe.py` · `ai_verify.py` (AI 실대화·대조 실험) ·
`fab_occlusion.py` (fixed 겹침을 DOM 좌표로 측정) · `saved_view_e2e.py` (미사용 기능 실행 검증).

### 다음

`docs/WORK_STATE.md` §3. 요약: ① 미사용 12기능을 하나씩 실환경에서 돌린다 ② 하네스 3건을
고치고 다시 돌린다(고치기 전 요약표는 믿지 않는다) ③ 화면 판독 계속(24/70).

### 사이클 0 (이어서) — 하네스 정직성 수정 · 역할 매트릭스 완주 · 미실행 기능 4건 실행

**하네스를 먼저 고쳤다** — 조사 도구가 거짓을 말하면 그 위 결론이 전부 무의미하다.
`QA-10`(미실행 검사를 "문제 없음"으로 보이게 함) · `QA-11`(403 을 "데이터 없음"으로 뭉갬) ·
`QA-12`(역할로 못 보는 라우트를 `ok` 로 셈) + 조사 중 새로 찾은 **`QA-14`**(원격 서버를 겨눈 채
**로컬 DB** 에 계정을 만들고 "생성됨"이라고 보고 — 실제로 로컬 개발 DB 에 미사용 QA 계정 2개가
쌓여 있었다). 회귀 테스트 7건(`tests/regression/test_ui_qa_harness_honesty.py`).

**역할 매트릭스 완주** — 4역할 197페이지. **화면 게이팅 결함 0**: 거부 화면 0 · 4xx 0 ·
실패 검사 0. `routes.py` 의 역할 표가 앱의 실제 게이팅과 정확히 일치함을 확인.
정직한 분모: user 27 / operator 55 / auditor 57 / admin 66 / system_admin 70
— 기존의 "70라우트 완료"는 최상위 역할에서만 참이었다.

**`USE-01` 미실행 기능 실행 (4건 완료 · 2건 보류)**
- **저장된 뷰** ✅ 필터→저장→새로고침→DB 1행. 빈 상태·미리보기까지 잘 만들어져 있다.
- **대리 보기** ✅ (코드) 자기 순위 이상 금지 · 범위 밖 404 · 레이트 리밋 · **쓰기 차단이
  단일 관문**에 있고 카운터는 별도 세션이라 fail-open 되지 않는다.
- **복구 리허설** ✅ **프로덕션 DB 로 `RESTORE_REHEARSAL_OK`** (75표·7,209행 일치, 복원본으로
  앱 부팅, ORM 69표 조회). `--record` 후 `/restore-drills` 반영까지 확인 — **실행→DB→화면**
  3단계가 이후 검증의 본보기다. 그 화면이 **자동 백업 꺼짐 + 마지막 백업 20일 전**을 드러냈다.
- **승인** ✅ 요청(202 pending, 즉시 적용 안 됨) → SLA `due_at` +24h → **자기 승인 403** →
  결재 → 역할 적용 → **요청자에게 `approval_requested`+`approval_decided` 둘 다** → 되돌리기.
- **문서 자동 생성** ⛔ 이 설치에 **생성용 워크플로가 없어** 실행 불가(`DGEN-02`).
- **스케줄 실행** ⛔ 유일한 스케줄이 **AI 채팅 웹훅을 주간 리포트 생성기로** 가리킨다
  (`SCHD-01`). 켜면 매주 월요일 09:00 에 `{"task":"weekly_report","delivery":"notion"}` 이
  채팅 웹훅으로 나간다 — [D-21](DECISIONS.md) 때문에 **켜지 않았다.**

**정정 3건** — `ADM-02`(메일 미설정이 CLI 사용의 원인이라는 추정) **틀렸다**: 관리자 재설정은
응답에 임시 비밀번호를 직접 주고, 자가 재설정 링크는 **메일을 보낼 수 있을 때만 표시**된다.
살아남는 것은 `/setup` 체크리스트에 **메일 항목이 없다**는 것뿐(`ADM-02R`).
`ADM-06`(잠금 상태를 안 보여 준다) **틀렸다** — 배지·버튼 다 있고 **`locked` 필터만 없다**.
승인 메모가 `null` 로 보인 것도 내 키 이름 오류였다(`decision_comment`).

### 사이클 0 (이어서) — 새 축 셋: 반응형 · 대비 · 실패 상태

**`RESP` 반응형** — `/users` 가 **1024×768 에서 사용 불가**(이메일 6줄·이름 4줄·표가 뷰포트 밖).
원인은 `kit.jsx:415` 의 전역 상수 `TABLE_CARD_BREAKPOINT = 899.95px` 하나이고,
**768 에서 도는 카드 레이아웃은 이미 훌륭하다.** 5화면을 더 재서 과장을 걷어냈다 — 1024 에서
깨지는 것은 **9열짜리 `/users` 하나**이고 6열 `/integrations` 는 멀쩡하다. 즉 실패는 뷰포트가
아니라 **열 개수의 함수**라 전역 상수로는 맞출 수 없다([D-33](DECISIONS.md)). 모달 7종은
1024·768 양쪽 통과.

**`CTR` 대비(새 축 `K`)** — 자동 검사 21종에 **대비 검사가 없었다.** 실측: **라이트 8중 6 무결점,
다크 8/8 위반.** 원인은 `theme.js:185` 가 `primary.main` 을 두 테마에 **같은 hex** 로 쓰는 것.
고를 수 있는 강조색 **4개 전부** 다크에서 미달(최악 「진한 파랑」 2.68). 콘솔 전환 버튼 2.86.
`tokens.css` 에는 대비 계산 주석이 촘촘한데(4.68·4.57·4.81·5.03·그라디언트 4.50 맞춤)
**링크 색에만 적용이 안 됐다.**
※ 첫 프로브가 그라디언트 배경을 못 읽어 상단바 흰 글씨를 전부 위반으로 셌다 — 지금은
**판정 불가를 세어 함께 보고**한다(화면당 34~50개). 보고된 위반 수는 **하한선**이다.

**`FAIL` 실패 상태** — 라우트 가로채기로 `500 / abort / 200+비JSON / 지연` 을 주입.
**제품이 실패를 「~가 없습니다」로 바꿔 말한다**(`FAIL-01`, Critical) — `/my-tickets`·`/projects`·
`/chat`(대화 52개인데 「아직 대화가 없습니다」)·`/users`. **`200+비JSON` 이 정직한 500 보다 나쁘다** —
8화면 전부 재시도 버튼이 사라지고 콘솔 오류도 0건이라 실패 흔적이 남지 않는다(`FAIL-02`).
`/team-docs` 는 **끝나지 않는 로딩**(`FAIL-03`). 좋은 패턴(「다시 시도」)은 500 경로의 4화면에
이미 있다 — 퍼뜨리는 것이 작업이다.

### 사이클 0 (이어서) — 워크플로 병렬 판독 · AI 능력 경계 · 키보드/시맨틱

**워크플로(에이전트 13개)로 미판독 40화면을 병렬 판독**하고 그룹별로 적대적 반증을 붙였다.
**175건 중 102건 폐기(58%), 73건 채택**(High 7 · Med 42 · Low 24). 종합이 **근본 원인 7가지**를
뽑았고 그중 **R1**(공용 규칙이 옵트인이라 12곳에서 조용히 빠짐)이 가장 값싸다 — `EmptyState` 에
`KO_WORD_BREAK` 한 줄이면 31개 파일이 함께 좋아지고 `ROUTE_OWNER` 2줄이면 High 1건이 사라진다.
**워크플로의 코드 참조 2건을 직접 검증했고 둘 다 정확했다.**

**자격증명 노출(High)** — 미러링된 Notion 문서 **1건**(107건 중)의 본문에 접속 URL·계정·비밀번호가
평문으로 있고 인증된 사용자 전원이 본다. **앱 버그가 아니라 원본 콘텐츠 문제**다.
※ 종합의 "QA 캡처 PNG 가 git 히스토리에 있다"는 **반증했다** — `.gitignore:12` 가 `dist/` 를 제외,
`git ls-files dist` = 0, 이력에도 없다.

**`AI-SCOPE`** — AI 도우미의 능력 경계를 실측했다. 티켓·프로젝트는 **보이고 정확하다**.
게시판·팀 문서·채팅방·작업 큐는 **안 보인다.** 문제는 안 보이는 것이 아니라 **태도**다 —
LLM 경로는 **"이 챗봇은 Notion의 팀 티켓·프로젝트 데이터만 다룰 수 있어서…"** 라고 정직하게
말하는데(정답 문구가 이미 있다), 규칙엔진 경로는 말없이 티켓으로 갈아 끼운다.
**최악은 `AI-40`** — "실패한 백그라운드 작업 몇 건?"(정답 4)에 **「조건에 맞는 티켓 완료 제외:
184건입니다.」** 라는 **단정적인 틀린 숫자**를 냈다. 목록은 눈으로 아니라고 알지만 숫자는 모른다.
그리고 `AI-42` — 모델이 스스로 **"제공된 데이터가 전체 티켓 중 일부만 포함된 상태"** 라고 밝혔다.
**모든 집계 답변이 부분 집합 위에서 계산된다.**

**`KBD`·`SEM`** — 키보드 포커스는 나쁘고(정지점 45개 중 38~45개가 `outline:0`, 틴트 대비
1.05/1.45 vs 기준 3:1), 접근성 시맨틱은 **강점**이다(이름 없는 버튼 0/125, `th[scope]` 100%).
원인 추정: vanilla→MUI 이관에서 `:focus-visible` 만 누락.

**정정 누적** — 내 자작 프로브가 이 세션에 **네 번** 틀렸고 네 번 다 "결함 있음" 방향이었다.
`D-44` 로 규칙화했다: 새 프로브의 첫 결과는 위양성으로 가정하고 표본을 개별 확인한다.

### 사이클 0 (이어서) — 워크플로 2회차: 미조사 6영역 병렬 심층 (2026-08-09)

입력검증·설치배포·게시판/문서·프로젝트/스프린트·러너 의도분류·화면 간 반영(`L`축).
에이전트 13개. **67건 중 11건 폐기, 56건 채택**(Critical 2 · High 11 · Med 27 · Low 16).
검증자가 **TestClient 로 실제 재현**하고 원 보고의 원인 지목을 두 번 정정했다.

**Critical 2건 — 내가 재확인함**
- `DEPLOY-01` **문서대로 업그레이드하면 서비스가 멈춘 채 남는다.** upgrade 가 installer 에
  `DNS_NAME`·`BIND_IP` 를 안 넘겨 `exit 2` 인데, 그 전에 web·worker 를 정지시켰고 복구 코드가 없다.
- `FN-40` 공지 「내용」을 비우고 저장 → **500**(`NOT NULL`). POST 는 막고 PATCH 만 빠진 비대칭.

**설치·배포 영역이 이번 조사에서 가장 나빴다** — Critical 1 + High 3(실패 처리 전무 ·
"되돌릴 것이 없다" 주석이 사실과 다름 · 롤백이 특권 헬퍼를 안 되살리는데 `ROLLBACK_OK` 는 찍힘).

**홈 위젯 2개가 각 도메인의 단일 판정 함수를 우회한다**(`SEC-12`·`SEC-13`). 서버 실측으로
**현재 유출은 없음**을 확인하고 High→Med 로 정밀화했다(조직 1개 · 전원 `admin_scope=global`).
다만 **부서는 이미 2개**라 dept 스코프를 한 명만 줘도 문서 위젯이 샌다.
`visible_posts` docstring 이 *"판정이 두 벌이 되면…"* 이라며 **같은 사고를 이미 기록**해 뒀다.

**러너 미탐 발견** — `_READ_OR_QUESTION_RE` 에 조합 불가능한 **호환 자모**(`ㄹ까` U+3139,
`ㄴ지` U+3134)가 들어 있어 「될까」·「할까」·「바꿀까」가 질문으로 인식되지 않는다(`AI-45`).

**4K 전수 스윕**(64라우트 × 2테마 = 128페이지)으로 `DS-32` 범위 확정 — **2요소 × 126페이지
= 252건**이 전부이고 나머지 12개 검사는 128/128 통과. **4K 레이아웃 자체는 건강하다.**

**`VIS-158R`** — AI 결과 카드 패널이 **폭 2200px 이상에서만** 존재하는데 **실제로 잘 동작한다**
(2560 실측: 티켓별 상태·담당자·마감·프로젝트 + Notion/상세 링크). 1920 이하 사용자는 말풍선
텍스트만 본다. `AI-31`·`AI-32`(말풍선 렌더 한계)의 해답이 이미 제품 안에 있다.

### 사이클 0 (이어서) — WF3 수렴 판정 라운드 (2026-08-09) → **수렴 안 함**

에이전트 6개(공백 탐색 3 · 상위 발견 재검증 2 · 종합 1).

**① 한 번도 조사되지 않은 영역 38개**(`docs/wf3_gaps.json`, 각 항목에 grep 0건 근거 + 첫 프로브).
High 10개 중 무거운 것: `app/team_chat/`(1,953줄, 스스로 선언한 IDOR 경계가 미검증이고 seq
할당기를 동시성 버그가 났던 games 에서 복제) · `app/core/uploads.py`(업로드 = 접근통제 경계,
소비자 3모듈) · **백업에 사용자 업로드 파일이 없다**(`RSTR` 이 증명한 것은 DB 뿐) ·
`app/cli/user_cli.py` · `app/core/sync_prune.py` · `/games/:id` · 디스크 가득 참.

**② 상위 12건 재검증 — CONFIRMED 8 / PARTIALLY_WRONG 4 / WRONG 0.**
- **`ADM-01` 철회** — 내 세션 최대 오판. 액션별 건수만 보고 "관리자가 웹 대신 SSH 를 쓴다"고
  단정하고 WORK_STATE 최상단에 올렸는데, **타임스탬프를 보니 설치 초기 온보딩 1회분 +
  이번 조사가 만든 QA 계정**이었다. 올바른 해석은 "아직 일상 운영 데이터가 없다".
- **`NOTI-04` 정정** — "딥링크 3건"이 아니라 **94/97 이동 가능**. 프런트에 폴백 표
  (`NotificationBell.jsx:33-44` + `serverRoute || objRouteHref`)가 따로 있었다. 살아남는 결함은
  `user` 유형 52건이 사람 한 명이 아니라 목록으로 가는 것뿐.
- **`HOST-01` 정정** — 수치는 진짜지만 **모든 문자열을 동시에 300자로 바꾼** 불가능한 입력에서
  나왔다. 근본 원인(열 폭 제약 부재)은 유효, 심각도는 현실적 페이로드로 재측정.
- **`AI-40` 재서술** — "고지문이 없다"는 전제가 틀렸다(내 저장 파일에 있다). 틀린 숫자를 답으로
  낸 것은 사실이므로 유지하되 `AI-41` 과 같은 뿌리로 묶는다.

**판정: 인계하지 않는다.** 수렴 기준 ①②를 둘 다 못 넘었다.
새 규칙 `D-49`(로그 집계는 시간분포+내 흔적 제외 없이 해석 금지) · `D-50`(서버에 없으면 프런트
폴백을 본다) · `D-51`(적대적 데이터는 일어날 수 있는 모양으로).

### 사이클 0 종료 — WF6 마지막 라운드 → **탐색 수렴, Sonnet 인계** (2026-08-09)

마지막 미조사 19영역(전부 Med/Low). **51건 중 14건 폐기, 37건 채택 — Critical 0 · High 2.**
5라운드 만에 처음으로 Critical 이 0이다.

**수렴 근거**: Critical `0→2→2→1→0` · High 비중 **5.4%**(최저) · Low 비중 **62%**(최고)이고
그 Low 23건 중 **10건이 "코드는 맞는데 주석·문서가 거짓"** 유형 · **신규 범주 0개** ·
반증률 27~35% 로 평평. 실행 결함이 고갈되고 문서 정합만 남았다.

**이번 라운드 High 2건** — `UX-50` **`/settings` 「세션 정책」을 열면 화면이 크래시한다**
(`fmtDuration` 미import, **실서버에서 재현**: `ReferenceError` + ErrorBoundary).
`S` 축(화면 캡처)이 못 잡은 이유가 명확하다 — **목록은 멀쩡하고 행을 눌러야 터진다.**
`FN-50` Notion 본문 저장이 1레벨만 읽고 자식 있는 블록을 지운다(**손자 유실**, D-21 로 미재현).

**`WORKER-01`(Med)** 이 지배적 패턴의 마지막 사례다 — 워커 동기화 틱이 설정 캐시를 다시 읽지
않아 노션 DB id 변경이 최대 600초 안 닿는데, **코드 주석 4곳이 정반대를 약속한다**(그중 하나는
그 배선을 하는 파일 자신). 600초라는 상한조차 백업 틱의 부수 효과다.

**인계**: `docs/SONNET_HANDOFF.md` 작성(392줄) — 사용자 조치 3건 · 구현 11단계 ·
먼저 읽을 파일 5개 · 손대면 안 되는 것 · 남은 불확실성 · 조사 도구 목록 ·
**내가 틀렸던 것 12건**.
