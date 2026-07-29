# ClovirONE 자율 검수·개선 루프 — 재개 상태 파일

> 세션이 끊겨도 이 파일 + git 로그 + PER_PAGE_FINDINGS.md로 정확히 이어서 작업한다.
> 완료 판정: 두 차례 연속 전체 재검수에서 새 Critical/High/해결가능 문제가 0.

## ★ 루프 종료(사용자 지시, 최종 라운드 = 라운드30 마무리)
사용자가 "이번 라운드를 마지막으로 루프 종료, 나온 문제 전부 처리 + 테스트까지 마무리"를 지시 → 실행 완료.
- **라운드30 non-test 158건 전부 수정·배포**(3.5단계: A/B/D/E ~95건 + 이전 E 재실행 등). 빌드 CKDPl3oN 배포, health 200.
- **테스트 인프라 완성(그동안 "나중에"로 미뤄둔 것)**: 프런트 **vitest 82건**(신규 러너 도입, npm test green) + 백엔드 **pytest 신규 11건**. 매 라운드 1순위 재등장하던 test-gap Critical(프런트 러너 부재) 해소.
- **죽은 vanilla 하네스 삭제 + CLAUDE.md 정정**.
- **최종 검증**: pytest **613 passed**, vitest **82 passed**, 정적검사 OK, CSP 위반 0, 서버 health 200 + 배포번들 CKDPl3oN 일치.
- **미결/한계(정직)**: ① 브라우저 무로그인 런타임 sweep은 `gooddi.lab` 자체서명 인증서 인터스티셜로 이번엔 못 돌림(코드문제 아님, 사용자가 인증서 1회 통과 필요). ② 라운드마다 감사가 새 Low/Medium 폴리시 항목을 계속 만들어내는 특성이 있어 "0 findings 2회 연속"이라는 산술적 종료조건에는 도달하지 않음 — 사용자 지시에 따라 라운드30에서 전량 처리 후 루프 종료. ③ 러너/콘텐츠 실데이터(§7/§8)와 반응형 매트릭스 육안검증은 로그인 세션·서버조사가 필요한 잔여 항목.

## 배포/검증 방법 (하네스)
- 프런트 빌드: `cd frontend && npm run build` (CSP-safe, 해시 번들 app/static/react/).
- 정적 핫배포: `tar -czf /tmp/react-bundle.tgz -C app/static react` → scp → 서버에서 `sudo` react 디렉터리 교체(무재시작).
- 백엔드 배포: 변경 .py scp → `py_compile` → `systemctl restart clovirone-web-assistant.service`(+worker_main 바뀌면 clovirone-web-worker). sudo=stdin(`printf '[REDACTED]\n' | ssh ... "sudo -S -p '' bash -c '...'"`).
- 테스트: `.venv/Scripts/python -m pytest -q` (전체 green 유지). static: `bash scripts/static_checks.sh`.
- 라이브 검증: MCP 크롬 탭 = 사용자 크롬 세션 공유. 세션 만료 시 로그인 폼 비번 입력·세션 위조 금지(하드 규칙) → 정적 셸 `/static/react/index.html`로 UI 렌더 확인 + pytest + SSH DB로 우회 검증. 사용자 재로그인 시 authed 클릭 검증 재개.

## 완료(이번 세션, 배포·검증됨)
- 유예 백엔드 하드닝(스케줄 misfire/run_at·retention 정리·chat 멱등키·문서 재시도·헬스 cert·워커 하트비트 스레드) — 테스트+라이브(worker up).
- 페이지별 감사 Critical 22건 대부분: DataScreen 상세 detailFields(전체 필드·JSON)·서버 페이지네이션·하위리소스 드로어(버전/실행이력); 승인 payload·감사 before/after·프롬프트/정책 내용·문서 미리보기·notion 후보 노출; 설정 object 편집; 사용자 임시비번 모달·재설정·잠금해제·세션해제·보관보기; 잡 재시도/취소.
- High 다수: 헬스/검증 결과 정직 표시, 대시보드 성공률 색, 감사 actionKo 다중세그먼트, 에러 경계, 채팅 jump-latest CSS, 비번정책 안내 동적화.
- 디자인 오버홀: 사이드바 구조화 트리(아이콘·접기·강조선·밑줄제거), 콘텐츠 폭 2040, 제목 경량화, 대시보드 서비스 라벨 단축·실시간 폴링·신선도·조치링크.
- Medium 일부: 대시보드 실시간/새로고침 피드백, 설정 저장 토스트, 채팅 입력창 자동확장.

## 남은 작업 (다음 반복)
1. Medium 잔여(약 90건, PER_PAGE_FINDINGS.md / scratch_med.md): change-password(show/hide·오류배지·csrf-race disable·라이브검증·빈필드), login(재발급 연락처), users(세션관리 상세·페이지네이션·역할/활성 필터·검색 대소문자), settings(dry-run·is_default·역할 게이트·maintenance 확인), diagnostics/maintenance(역할 게이트·maintenance_message 편집·복사 폴백), chat(낙관적 에코·대화 보관·티켓 status 정규화), 각 화면 잔여.
2. Low 잔여(약 94건) + test-gap(73건) — test-gap은 마지막에(프런트 vitest 러너 도입 포함).
3. 콘텐츠/자동화 실사용 항목 구성(프롬프트·정책·템플릿·스케줄·문서·승인 실제 흐름) + n8n/Notion 종단 검증.
4. AI 채팅 시나리오 매트릭스(정상/부족/모호/혼합/부정/다중/티켓/승인/중복/첨부/실패재시도/권한/새로고침) + API·DB·n8n·Notion 대조.
5. 반응형 매트릭스(390~3840 + 확대125/150/200%) 자동+육안 + 디자인 비판 재판정.
6. 전체 재검수 워크플로 2회 연속 clean까지 반복.

## 감사 반복 진행
- 라운드1(wf_0b8e5ded): 324건 → Critical 22 대부분 수정(근본원인=DataScreen 상세/페이지네이션), High 다수.
- 라운드2(wf_1aa7273c, 개선 코드 대상): 323건 / Critical 5(2 test-gap, 3 실수정: 감사 필터·notion 페이지네이션·백업 복원안내 — 완료), High 76·Medium 132·Low 110.
  - 라운드2 High 완료 배치: 버전기록/롤백(연동·러너·워크플로), 헬스/테스트 결과 정직표시, detailFields(연동·러너·템플릿·백업), 알림 읽음/모두읽음+읽음배지, 작업 상태필터, 사용자 페이지네이션·역할/활성 필터, 채팅 대화목록 갱신, 감사 actionKo 다중세그먼트, 테스트상태 한국어.
- **라운드2 High 배치3 완료**: 권한 기반 nav 게이팅(진단·유지보수는 admin+, 알림벨 푸터 role=user 숨김), 채팅 모바일 드로어(☰ 토글+오프캔버스+백드롭), 문서 페이지네이션, 스케줄 실행 재시도(runs rowAction), 승인 메모 수집(approve/reject fields).
- **라운드2 잔여 High(소수, 다음)**: 프롬프트/정책 롤백·diff(버전 피커 UI 필요), FormModal 편집 시 빈값 클리어(민감), 진단 JSON 가독화, 문서 period 표시(백엔드 미반환), jobs stats 요약.
- **검증 팁**: 무로그인 정적 셸은 `/static/react/index.html?cb=N` 로 캐시버스트해야 최신 번들이 뜬다(index.html 직접접근은 StaticFiles 캐시). /admin·/ 실경로는 no-store라 항상 최신.
- **라운드3(wf_3f281424) 완료 — 멀티에이전트 병렬 수정 ~99건 통합·배포·검증**: 3개 에이전트가 겹치지 않는 파일세트를 나눠 맡음(registry+DataScreen 45 / 커스텀화면+auth+be 33 / kit+css+shell 21). diff를 git apply로 통합 → 빌드(index.tyTgPKoq) → pytest green → 정적핫배포 + 백엔드 4파일 restart(active·health200). 라이브검증: 로그인 show/hide 토글 실동작·재발급안내, React셸 모바일햄버거·알림벨SVG·에러바운더리無·콘솔에러0.
  - 주요: 워크플로 payload/response_schema, 프롬프트/정책 되돌리기·보관·롤백, 러너 maintenance_state 편집·clone, 스케줄 dry-run·run-now dedup, notion error_message·sync결과, 백업 false-success 수정, linkCol(published_ref 링크); 대시보드 역할링크·하트비트경보·D-45 인증만료, Ops 진단 구조화렌더+복사폴백+maintenance_message 편집, 설정 라벨맵·is_default·dry-run·역할게이트, 채팅 보관/낙관에코/첨부파일명; 로그인/비번 show-hide·빈필드검증·per-line오류·재발급연락처; 백엔드 대소문자검색·actor이름; kit FormModal null클리어·Modal 포커스트랩+스택·Badge한국어·DataTable a11y·토스트 role=alert; 모바일 사이드바 드로어.
  - **라운드3 스킵(다음)**: format.js OBJECT_KO/TYPE_KO 보강(소유 에이전트 없었음), 프롬프트/정책 버전 diff 뷰어(새 모달 필요).
- **라운드4(wf_4cbf17d3) 완료**: 42에이전트 316건. **기능·디자인 Critical 0**(Critical 6건 전부 test-gap → 사용자 지시대로 마지막 단계 보류). non-test High 33·Medium 91·Low 108=232건.
- **라운드5(wf_f3c7f696) 완료 — 5에이전트 병렬 수정 ~138건 통합·배포**: A=registry 48 / D=kit+CSS+format 26 / C=custom 23 / B=chat+users 21 / E=backend+auth 20. git apply 5개 클린 통합 → 빌드 → pytest green → 배포(DYJBJY9u). 주요: pollWhile 자동갱신·드라이런 미리보기·서브드로어 페이지네이션, 채팅 어시스턴트 타이핑버블·캐시즉시반영, 대시보드 폴백유지·타일추가, format.js 열거 한국어 완비, kit 상태 한국어·모달포커스, 로그인/비번 탈출경로·세션만료 구분.
- **라운드5 회귀 크래시 즉시 수정(중요 교훈)**: 무로그인 정적 셸 route sweep에서 대시보드가 `Cannot read 'jobs_24h' of undefined`로 크래시(빌드·pytest는 못 잡음 — 프런트 런타임 테스트 부재) → data 없을 때 DashboardBody에 undefined 넘기던 가드 수정 + ErrorBoundary를 본문으로 한정(경로별 리셋). 재배포(xO-CD-aI) 후 **22개 경로 전수 sweep: 크래시 0·사이드바 유지**. **교훈: 프런트 diff 통합 후 반드시 `?cb=N` 셸에서 전 경로 sweep으로 런타임 회귀를 잡는다**(빌드 성공≠런타임 정상).
- **라운드6(wf_f826f967) 완료**: 285건(라운드4 316↓). non-test Critical **2건**(감사 화면 회귀: 행위자 UUID 노출 + object_type 필터 죽은 값 5개) + High 24·Med 74·Low 98=197. Critical 3건은 test-gap.
- **라운드7(wf_b8cbfe49) 완료 — 5에이전트 병렬 수정 ~111건 통합·배포(-RUXEVC2)**: 에이전트가 AREA 헤더 무시하고 소유 파일 기준 자율 선별(오배치 커버리지 구멍 해소). A=34 B=18 C=18 D=18 E=23. 감사 Critical 2건 해결(행위자 실명·필터 교정+object_id), 채팅 IME 조합 가드(한글 글자유실), 정책 롤백+diff·프롬프트 diff·잡 큐통계·설정 버전기록·템플릿 적용, 알림 전체보기 일반사용자, 터치 대화액션, RequireRole 데이터화면+액션 role게이트, change-password 링크/CSRF, 스케줄 run_at, 템플릿 enabled 소비. pytest 592 green.
- **라운드7 후속 수정**: round7이 auth 401→`/login` 하드 리다이렉트를 넣어 무로그인 셸 검증이 깨짐 → **'세션이 만료되었습니다' 안내 화면+로그인 링크**로 변경(자동 튕김 대신 명시 안내, 무로그인 셸 렌더 유지).
- **검증 방식 변화(중요)**: 무로그인 셸은 이제 authed 경로에서 세션만료 화면을 보여준다(정상 동작). 따라서 **데이터화면의 '데이터 렌더 경로' 크래시 감지는 로그인 또는 vitest 하네스 필요**(최종 test 단계). Layout/셸 크래시는 여전히 sweep로 감지. 프런트 diff 통합 후엔 build+diff리뷰(undefined 역참조 주의)+pytest+셸 sweep로 검증.
- **라운드8(wf_a5177272) 완료**: 291건. **non-test Critical 0**(Critical 5 전부 test-gap; R6 감사 Critical 계속 해소). non-test High 26·Med 67·Low 103=196. 신규 High = vanilla→React 이관 때 사라진 채팅 서식(어시스턴트 평문·티켓 중복·TicketCard 배열 미처리).
- **라운드9(wf_1f9c89dd) 완료 — 5에이전트 병렬 수정 ~89건 통합·배포(CsUjaFDa)**: A=16 B=19 C=24 D=17 E=13. 핵심: **채팅 리치텍스트 포팅**(vanilla chat.js→React RichText, textContent 전용, msg-h/list/kv, 티켓 중복제거, TicketCard 배열, 이미지 다운스케일, IME 가드) + **액션 역할 게이팅 일괄**(WRITE_ROLES/OPS_ROLES 전 화면) + 라우트 게이팅(users/jobs) + 진단 오류표시 + 문서 period 영속화 + 백업/직책 정합. pytest green. sweep 크래시 0.
- **라운드9 후속**: 대시보드 백업 링크 NAV_ROLES를 App.jsx READ_ROLES와 정합(C·D 교차 불일치 해소).
- **라운드10(wf_4eec1644) 완료**: 281건. non-test Critical 0(Critical 2 전부 test-gap). non-test High **18**(26↓)·Med 67·Low 102=187. bug 27→14. 잔여 High 근본원인: DataScreen 생성/수정 버튼 미게이팅, 채팅 구조화 카드 tickets만 렌더.
- **라운드11(wf_7791e6dd) 완료 — 5에이전트 병렬 수정 ~104건 통합·배포(DIShD4II)**: A=38 B=16 C=20 D=14 E=16. DataScreen 생성/수정 버튼 role 게이팅(create.roles/edit.roles), 승인 자기결재 차단(auth.id 주입), 채팅 구조화 카드 6종 복원, 사용자 보관이메일 409→복구, notion 동기화 폴링, 문서 period 컬럼, 잡유형 한국어, 허용도메인[] 허용, 템플릿 바인딩 소비. pytest green, sweep 크래시 0.
- **라운드12(wf_3ff67b6e) 완료**: 266건. **non-test Critical 0**, non-test High **9**(18↓). 잔여 High: allowed_email_domains 도움말 stale(x2, 백엔드는 []허용하나 문구는 "빈목록 저장불가"), health verdict가 web/worker만 봄, 승인 요청자/결정자 UUID, 문서 requested_by 미노출, 스케줄 빈상태 CTA 권한, 프롬프트 runner_id 도움말, 감사 결과열 항상 성공, 감사 action 필터 free-text.
- **세션만료 게이트 제거(검증 복원)**: R7의 세션만료 전체화면이 무로그인 셸 렌더를 막아 디자인 검증 불가 → 제거. 이제 401이어도 셸(사이드바·상단바) 렌더, 데이터화면은 ErrorState+로그인링크. 무로그인 sweep/디자인 검증 복원(배포 DDhVS3yS).
- **사용자 신규 디자인 지시(§1~§10) 루프에 포함**: 사이드바 전면재검수(폭 확대·NavigationGroup/Item 공통화·선택배경 행 정확일치·왼쪽 색막대 제거·유저/관리자 통일·드로어), 채팅목록 선택정렬, 채팅본문 폭/반응형(2560활용·읽기폭), 페이지 간격 토큰(PageHeader/Section/Help/Toolbar/EmptyState), 대시보드 재설계(굵기계층·중요도별 카드·반응형그리드), **왼쪽 색막대 전수 제거**(bg/border/icon/badge로 대체), 빈상태 안내강화, 러너 실데이터 연결(§7), 콘텐츠/자동화 실항목(§8). 판정기준 §10 각 항목 0건.
- **라운드13(wf_1fa1b640) 완료 — 디자인 시스템 오버홀 배포·검증(Ca5IZjiA)**: SHELL 사이드바 전면(폭 260→280px·NavigationGroup/Item 공통화·선택배경 행정확일치·왼쪽 색막대 제거·라벨 말줄임), KIT 토큰(--space-*/--fw-*)+공통컴포넌트(PageSection/PageHelp/Toolbar/EmptyState 안내슬롯), CHAT-DASH 채팅목록/본문 반응형+대시보드 굵기계층, SCREENS 잔여High(allowed_email_domains 도움말 [] 허용 반영·승인 UUID→"요청자 ID" 라벨·health verdict 이미 정상). **검증(무로그인 셸 육안)**: border-left 색막대 런타임 0개, 사이드바 긴 라벨 한 줄, 선택배경 행 정확일치, CSP 0, sweep 크래시 0, border-left CSS grep 0. 채팅 빈상태+칩+composer 정상.
- **라운드13 잔여**: 승인 요청자/결정자는 백엔드가 이름 미해소(UUID만) → 라벨만 "ID"로. 이름 표시하려면 백엔드 approval_view에 actor_name 해소 추가 필요(다음). 대시보드 카드·채팅 메시지 레이아웃 육안검증은 로그인 필요(무로그인은 401→ErrorState).
- **라운드14(wf_4e539100) 완료**: 281건. non-test Critical 0, non-test High **9**(디자인 findings는 Medium/Low로 안착=오버홀 수용). Med 66·Low 117.
- **라운드15(wf_cb536a4f) 완료 — 5에이전트 ~37건 통합·배포(D8beb8wW)**: non-test High 9건 정리 — 프롬프트 빈상태 역할인지, 템플릿 문서생성 동선(해시 프리필), 승인 payload 렌더, 정책 라이프사이클, notion 검증 info-톤(A); 사용자 안내 Callout(B); Ops 헬스 전 컴포넌트 반영(C); 감사 operator 게이팅(D); 정책 policy_id stale 버그·승인자 이름 해소(E). pytest green, sweep 크래시 0. (E의 새 회귀테스트 파일은 저널 truncate로 스킵 — 백엔드 코드 수정은 적용됨.)
- **라운드16(wf_fcdb6ff5) 완료**: 276건. non-test **Critical 1**(신규 발견: 스케줄 생성 폼 misfire/concurrency select가 값 없으면 null 전송→백엔드 non-Optional str 거부→기본 경로로 스케줄 생성 시 항상 422) + **High 8**(채팅 TicketCard 담당자 미할당 고정노출, 알림벨 포커스트랩 a11y, Ops 헬스판정 통합상태 미반영, 사용자 화면 감사연동 누락, 승인 요청자/결정자 이름 미직렬화 추정, 템플릿 러너타깃 막다른길, notion 검증 오탐성공, 알림 관련항목 라우트 불일치).
- **라운드17(wf_21580578) 완료 — Critical 1+High 8 정리, 배포(DNXOHs_a)**: 스케줄 생성 422 Critical 수정(misfire/concurrency select value:"skip"), 채팅 TicketCard 미할당 오표시, 알림벨 focus-visible, 템플릿 러너타깃·notion검증·알림라우트, DataScreen 검색 디바운스+confirm함수+페이지네이션시맨틱. pytest green(+1 신규), sweep 크래시 0.
- **라운드18(wf_ade7164e) 완료**: 256건. non-test **Critical 4**(핵심원인 3개: ①감사딥링크 DataScreen onQuery filter미지원=3에이전트 중복발견, ②알림벨 401패턴 미재사용, ③워크플로 화면 n8n 연결 프레이밍 결함) + **High 36**(workflows/integrations/documents/schedules/templates/runners/policies/prompts/jobs/backup/notifications/audit 전반의 dead-affordance/missing-feature + 공유인프라 ErrorState/RequireRole/busy-flag 결함). **주의**: 라운드17에서 추가한 사용자→감사 딥링크 버튼 자체가 회귀(onQuery 미구현)로 지적됨 — 새 기능 추가 시 소비측 배선까지 같은 라운드에서 확인 필요.
- **라운드19(wf_094aaee0) 완료 — Critical 4(근본원인 3)+High 36 대량정리 ~70건, 배포(Bcj9H3w1)**: DataScreen onQuery filter 인텐트(감사딥링크 근본수정), 채팅↔시드 Workflow 레지스트리 실연결, 알림벨 ErrorState 재사용, 채팅 초안정리·응답지연 잠금해제, 사용자 diff전송, 비번변경 무차별대입 방지, 감사 role_change 정합, 승인 payload 보강, 정책 작성자 이름, 러너 auth_type, 프롬프트 목록상한, 백업 오류한글화. pytest 796+ green, sweep 크래시 0. (D 저널 truncate 1건 수동 재적용 완료.)
- **라운드20(wf_4ce377b0) 완료**: 239건(256↓). non-test **Critical 4**(템플릿 러너타깃 처리, 워크플로 시드행 안내문구 현실불일치, 스케줄이 승인필요 워크플로를 우회활성화 가능, 연동 버전기록 필드 누락) + **High 17**(36↓ — 뚜렷한 수렴). Med 69·Low 76.
- **라운드21 — 서브에이전트 세션 한도 도달(4개 전부 실패, 리셋 23:50 KST)**: 사용자 피드백("자잘하게 하지 말고 크게크게, 21라운드째 뭐가 바뀐지 모르겠다")에 따라 서브에이전트 대신 **직접 수정**으로 전환, Critical 4건만 우선 처리(Low/Medium 긴 꼬리는 보류):
  - 템플릿 러너 대상 생성 불가(TARGET_OPTS에 워크플로만 있었음) → TEMPLATE_TARGET_OPTS 추가
  - 워크플로 시드행 안내문구가 "실제 채팅에 영향 없음"이라고 (라운드19 이후) 거짓말 → 문구 수정 + 비활성화 강한 경고
  - 연동 버전기록에 백엔드가 민감필드로 명시한 health_url/secret_ref 누락 → 노출
  - 스케줄이 승인필요 write 워크플로를 대상으로 하면 항상 런타임 실패 → 백엔드 생성/수정 시 422로 거부(회귀테스트 2건 추가)
  - pytest 전체 green, 빌드/CSP/sweep 통과, 배포(BvVMKWSX).
- **다음 세션 유의**: 서브에이전트 워크플로 재개 시 findings를 잘게 쪼개지 말고 우선순위 상위(Critical/High)만 큰 배치로 처리, Low는 별도 백로그로 명시적으로 미루고 사용자에게 "무엇이 바뀌었는지" 구체적 확인 방법(URL/화면/조작)을 매번 제시할 것.
- **라운드22(wf_571dffc6) 완료**: 232건. non-test Critical 2건(둘 다 신규/직접수정) + High 31.
  - Critical① 템플릿 러너대상: 라운드21에서 옵션만 노출하고 소비자를 안 만든 half-fix가 스스로 죽은기능을 만듦 → 워크플로만으로 롤백(정직한 원복).
  - Critical② 연동 활성/비활성이 장식용 스위치였음 → 러너의 유일한 integration_id 소비 경로(RunnerHttpProvider.invoke)에 실제 차단 로직 연결(진짜 킬스위치화). 둘 다 직접 수정·pytest green·배포(DUFNToG4).
- **사용자 정정**: "Low/Medium 건너뛰지 말고 매 라운드 나오는 건 다 작업해라, 우선순위 두지 말고" — 이후 모든 라운드는 Critical/High/Medium/Low 전부 처리(우선순위별 분리 금지).
- **라운드23(wf_e8b55a1b) High 31건 완료·배포(DuHh2HDC)**: 정책 페이지네이션 경고, 스케줄 실행이력 전체보기, 러너 secret_status, 워크플로 롤백 예약행 경고, 채팅 티켓우선순위 Badge, Ops 리소스카드 클릭화, 알림벨 z-index, DataScreen 상세필드 중복제거, 백엔드 비번변경 자기감사·로그인 무JS리다이렉트·재시도 속도제한·change_password 전용CSS. pytest green.
- **라운드23b(wf_893bbff4) Medium 60+Low 71건 완료·배포(CxarQRT0, ~76건 수정)**: registry role별 필드함수·해시쿼리 재소비, 채팅 폴링백오프·재시도대화ID·세션복원, kit RequireRole onRetry·배지어휘, 백엔드 429 Retry-After 실제화 등. pytest green. (B 에이전트 큰 diff 저널truncate 1건 수동복구.)
- **라운드24(wf_874f1c89) 완료**: 226건. **non-test Critical 0**(10건 전부 test-gap — 처음으로 완전 클린). non-test High 29·Med 50·Low 66=145.
- **라운드24 수정(wf_64496679) 완료 — 4에이전트 전체심각도 배치 ~90건, 배포(jIHVh5gj)**: A=30 B=33 D=15 E=12(pytest green). 러너 auth_type role인지, 정책 페이지네이션, 워크플로 버전기록 확장, 문서 교차화면 링크, DataScreen 401→로그인 이동, 성공률 분모 문구, 인증서 만료 오프바이원, 대시보드 카드 드릴다운, 모달/로그아웃 포커스링, 로그인 무JS 실제 리다이렉트. sweep 크래시 0, 4개 diff 모두 클린 적용(저널 truncate 없었음).
- **라운드25(wf_6606b674) 완료(감사 에이전트 4개 일시적 분류기 오류로 로그인/채팅 커버리지 약간 얕음)**: 206건. non-test Critical 1·High 24·Med 48·Low 59=132.
- **라운드25 수정(wf_02193b92) 완료 — 4에이전트 전체심각도 ~82건, 배포(CCIMkhsD)**: A=31 B=32 D=8 E=11(pytest green). keepPreviousData(목록/알림벨 팝오버 스켈레톤 방지), 처리중 라벨, optionsFrom create/edit 확장, notion 링크 복사폴백, 승인 실행경로 버그. sweep 크래시 0.
- **라운드26(wf_f0682553) 완료**: 229건. **non-test Critical 0**(2회 연속). High 23·Med 47·Low 71=141.
- **라운드26 수정(wf_0d1f6d88) 완료 — 4에이전트 전체심각도 ~86건, 배포(BRWCxTF8)**: A=25 B=34 D=15 E=12(pytest green, 기존 리다이렉트 테스트 3건 정당 갱신 확인). 로그인 후 원래 페이지 복귀(?next=, open-redirect 방지 검증), '내 프로필' 메뉴(GET /api/profile 최초 소비), onQuery select 딥링크, 페이지 클램프. 라이브 검증: `/admin` 무인증 접속 시 실제로 `/login?next=%2Fadmin` 반환 확인. sweep 크래시 0.
- **라운드27(wf_12d4cdae) 완료**: 213건, **라이브로 실제 크래시 재현**(POST /login에 배열 등 non-dict JSON → 500) → 즉시 직접수정+회귀테스트+배포, master 병합. 나머지 non-test High 23·Med 47·Low 57=127.
- **라운드27 수정(wf_9628d25e) 완료 — 4에이전트 전체심각도 ~74건, 배포(D_aZrgbA)**: A=24 B=19 D=12 E=19(pytest green). onQuery id딥링크 다수화면, finishAction 공통화(입력폼 액션도 pollJob 등 적용), notion매핑 권한경계 수정, 러너 필터 실제적용화. sweep 크래시 0, 4개 diff 모두 클린.
- **라운드28(wf_417162e3) 완료**: 218건. **non-test Critical 0**(3회 연속). High 23·Med 44·Low 58=125.
- **라운드28 수정(wf_abe963b8) 완료 — 4에이전트 전체심각도 ~78건, 배포(DkyxuQPv)**: A=25 B=27 D=9 E=17(pytest green). busy를 액션키 기반으로, clientFilter 개념, datetime-local KST변환, runner_unavailable 알림 딥링크, _safe_next_path를 app/core/urls.py로 공유화(로그인 크래시 수정 파일과 함께 안전하게 병합 확인). sweep 크래시 0.
- **라운드29(wf_452a5357) — 라이브 크래시/보안취약점 2건 직접 발견·수정**:
  1. **오픈 리다이렉트(보안)**: 로그인 `?next=` 검증이 `//evil.com`은 막았지만 `/\evil.com`(WHATWG URL 표준상 특수스킴에서 `//`와 동일하게 해석되는 CWE-601 백슬래시 우회)은 통과시켰음 — 로그인 직후 공격자 도메인으로 리다이렉트되는 실제 취약점. `app/core/urls.py` 가드 추가+회귀테스트 3건, curl로 라이브 재현→수정 확인.
  2. **워크플로 tags 크래시**: 편집 폼에서 태그를 모두 지우면(null 전송) 백엔드 재검증이 bare pydantic.ValidationError로 500. `update_workflow`에서 null→빈배열 정규화 + **전역 pydantic.ValidationError 핸들러 신설**(향후 같은 종류의 계약실수 전부 500→422로 격상, 시스템적 방어). 회귀테스트 추가.
  - 둘 다 즉시 직접수정→pytest green→배포→커밋(별도 2건), master 반영. **감사가 test-gap 태그를 붙여도 실제 라이브 크래시/취약점이면 직접 검증 후 즉시 고친다는 패턴 재확인**.
- **⚠️ 서브에이전트 주간 한도 도달(2026-07-21) — 리셋 2026-07-25 07:00 KST**: `w6u667v3n` 4개 에이전트 전부 즉시 실패("weekly limit"). Workflow/Agent 툴로 새 세션을 못 띄운다(세션 한도와 달리 며칠 단위). 재개 시 `Workflow`/`Agent` 호출이 다시 되는지 먼저 짧게 확인.
- **라운드29 Critical 3건 전부 직접수정 완료(서브에이전트 없이) — 배포(DP_3Li22)**: ①오픈 리다이렉트(위 기록) ②워크플로 tags 크래시(위 기록) ③**must_change_password 계정이 관리콘솔 전역 403 막다른길**: App.jsx Layout이 /api/me 응답으로 즉시 /change-password 이동, api.js 이중 방어, kit.jsx ErrorState가 실제 메시지+올바른 링크 표시. 빌드/CSP/정적검사/sweep 통과.
- **라운드29 잔여(서브에이전트 재개 대기)**: High 20+Med 38+Low 56≈114건, `docs/product-quality-audit/REMAINING_FINDINGS.md`에 영역별(A/B/D/E) 정리돼 있음 — 그대로 재사용 가능(단 이미 고친 3개 Critical 관련 문구는 제거됨).
- **라운드29 잔여 백로그 전부 정리 완료(주간한도 해제 후 재개)**: A/B/D 배치 ~70건(CeW7hFEj) + E 백엔드 12건, 전부 통합·배포·pytest green.
  - **교훈(에이전트 diff 회수)**: A가 diff를 산문요약으로 반환(적용불가) → **worktree에서 `git -C <wt> add -A && git diff --cached HEAD`로 실제 패치 직접 회수**해 적용. D도 저널 diff가 컨텍스트 불일치라 같은 방식으로 worktree에서 재생성. 앞으로 diff가 산문이거나 apply 실패하면 worktree 회수가 1순위 복구법.
  - E는 처음에 일시적 분류기 오류로 실패 → 단독 재실행으로 성공(12건). 기존 직접수정 3건(pydantic핸들러·오픈리다이렉트·login가드) 보존 확인.
- **⚠️ 브라우저 런타임 sweep 일시 불가**: `clovirone-ai.gooddi.lab` 자체서명 인증서 인터스티셜("개인정보 보호 오류")에 Chrome이 걸려 MCP JS 부착 실패. 코드문제 아님. 사용자가 한 번 통과시키거나 인증서 신뢰하면 재개. 그동안은 빌드+static+pytest+CSP+배포해시로 검증(런타임 undefined-deref 크래시 감지만 공백).
- **누적(이번 세션)**: R3~R29로 ~1290건+ 수정·배포·검증 + 라운드29 라이브 Critical 3건 직접수정.
- **누적(이번 세션)**: R3~R21(직접수정 포함)로 ~700건+ 수정·배포·검증. 가장 눈에 띄는 가시적 변화는 라운드13 사이드바 디자인 오버홀(폭 확대·좌측 색막대 제거·선택배경 정렬) — `/static/react/index.html?cb=N#/dashboard`에서 무로그인으로도 확인 가능.
- **디자인 후속(별도, 서버조사 필요)**: §7 러너 실데이터(업무도우미/티켓러너/요청해석기 등 실제 프로세스 자동발견·연결 — 서버 10.100.64.71 프로세스+n8n+runner :8787/8788/8789 조사), §8 콘텐츠/자동화 실항목(프롬프트/정책/템플릿/일정/문서/승인 실사용 구성 + 종단 흐름 n8n→Notion→알림/감사). 프로덕션 데이터라 신중히.
- **누적(이번 세션)**: R3~R11로 ~541건 수정·배포·검증. non-test High 추이 33(R4)→24(R6)→26(R8)→18(R10)→**9(R12)**.
- 종료 판정: 2회 연속 non-test Critical/High/해결가능 0. (test-gap 최종 단계: vitest 러너 + 죽은 tests/js 하네스 정리 + 핵심 스모크/로직 테스트.)
- **누적(이번 세션)**: R3~R9로 ~437건 수정·배포·검증. non-test High 추이 33(R4)→24(R6)→26(R8)→R10 대기.

## 감사 findings 원본
- scratch_round2.md (라운드2 actionable Critical/High), scratch_med.md(Medium), PER_PAGE_FINDINGS.md(라운드1).
- 저널: subagents/workflows/wf_1aa7273c-cea/journal.jsonl (파서로 재추출 가능).
- 재감사 재실행: `Workflow({scriptPath:".../clovirone-per-page-audit-wf_0b8e5ded-266.js"})` (fresh run).

## 재개 절차
1. 이 파일 + `git log --oneline -20` + `docs/product-quality-audit/PER_PAGE_FINDINGS.md` 읽기.
2. 남은 Medium/Low를 공통원인별로 배치 수정 → 빌드 → 배포 → pytest.
3. 페이지별 감사 워크플로 재실행(scriptPath: clovirone-per-page-audit) → 생존 findings 수집 → 반복.
4. 2회 연속 clean이면 최종 보고.

## ★ 사용자 추가 피드백 처리(라운드30 이후 — 실사용 UI/데이터)
사용자가 실제 로그인 화면에서 본 구체 이슈 처리:
- **채팅 렌더링/디자인**: 본문·컴포저 폭 1000→1400px(넓은 화면 전폭 활용), 대화목록 날짜에 .chat-conv-time + scrollbar-gutter로 스크롤바 겹침 해결·hover 시 날짜↔액션 스왑, 입력창 높이 점프를 단일 useLayoutEffect+min-height로 제거. 배포 CD5B3q6M, vitest 82 green.
- **관리화면 간격**: DataScreen 루트 .c-screen + 설명 콜아웃/요약 dash-grid에 margin-bottom → 작업 큐 등에서 제목·설명·요약·툴바 붙어보이던 문제 해결(루트 직계에만 적용).
- **§7 러너 실데이터**: 실 서비스 3개(티켓러너:8787·요청해석기:8788·업무도우미:8789, allowlist 등록됨)를 scripts/seed_content.py로 등록(비활성, §15.5). 
- **§8 콘텐츠/자동화 실데이터**: 프롬프트 3(발행)·정책 2(발행)·템플릿 2·스케줄 1(주간리포트) 시드. 전부 앱 서비스 계층·멱등·실 업무 콘텐츠. 프로덕션 web.sqlite3에 백업(web.sqlite3.pre-seed-*) 후 적용, DB 재조회로 검증.
- **교훈**: 에이전트가 diff/verify를 산문으로 반환 → worktree에서 파일 직접 회수 + 내가 로컬 임시DB로 2회 실행(생성→skip) 재검증 후 프로덕션 적용. 프로덕션 데이터 변경은 반드시 백업 먼저.
- **잔여(정직)**: 러너/템플릿/스케줄은 설계상 비활성 등록 — 사용자가 승인 흐름으로 활성화해야 실행됨(정상). 채팅 대화행 정렬·입력높이·작업큐 간격의 로그인 상태 육안검증은 8090 터널 이슈로 소스·vitest로만 확인(사용자 화면 새로고침 시 확인 가능).

## ★ 사용자 채팅 UX + AI 러너 개선 (실사용 피드백 2차)
- **캐시 근본원인 수정(중대)**: /static/react/index.html이 max-age=3600으로 서빙돼(미들웨어) 배포가 사용자에게 최대 1시간/하드리프레시 전까지 안 닿던 게 "여전히 그대로"의 진짜 원인. 미들웨어에서 /static 하위 .html은 no-store로 수정(app/core/middleware.py) + 회귀테스트 2건. 이제 새로고침만으로 즉시 반영.
- **채팅 전체 너비**: chat-body/composer max-width 캡 제거(1000/1400→100%), 버블 1120px. (스크롤 겹침·입력높이 점프 수정은 이전 커밋에 포함됐으나 사용자가 옛 캐시라 못 봤던 것 — 캐시 수정 후 보임.)
- **AI 러너 경직성(claude-work-assistant, /opt/claude-work-assistant/assistant.py, 모델 sonnet 유지=사용자 결정) 3-loop 개선**:
  - loop1: is_capability_question/is_bulk_modify_request → 역량·가능여부·일괄·dry-run 발화를 claude_query(정직한 LLM 답변)로 라우팅. QUERY_PROMPT 역량안내. (+10 테스트)
  - loop2: how-to/취소·정정/복합의도/애매단편/영어혼용 확대 + 프롬프트 강화. (+19 테스트, 총 246)
  - loop3: 적대적 오분류 점검 — 정상 생성/수정/조회 발화가 새 술어에 안 잡힘 확인(코드 변경 불필요).
  - 러너 테스트 217→246 green, 서비스 배포·재시작·배포파일 라우팅 검증 완료.
- **정직한 한계**: 실제 LLM 답변 품질은 RUNNER_TOKEN(시크릿)이라 curl 불가 → 라우팅+246테스트+적대점검으로 검증. 실제 대화 품질은 사용자 라이브 검증 필요. "일시적 문제" 반복은 당시 Claude CLI 일시장애(이후 복구), sonnet 유지로 안정성 우선.
