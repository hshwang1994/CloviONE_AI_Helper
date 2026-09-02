# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-09-02** (문서·조직·프로젝트 3영역 재설계 + 카테고리 축 + 엑셀 내보내기 — D-403~D-406)
- phase: **F — Acceptance 완료(S22) 뒤의 일반 개발**(CLAUDE.md §7.0)
- session: **「문서·조직·프로젝트 화면이 예쁘지 않고 검색이 중간에 있다」는 요청에서 시작해,
  세 영역을 표준 골격(상단 전폭 검색·필터)으로 재설계하고 카테고리 축과 엑셀 내보내기를
  세웠다.**
  ① **문서 카테고리 축**(D-404 · 0026): `document_categories` 표 + `documents.category_id`
  (SET NULL) + 태그와 대칭인 CRUD API + 「분류 관리」 모달(카테고리·태그 탭). 이관
  `doc_type` 값에서 시드했고 doc_type 컬럼은 이관 정본으로 남는다. 저장은
  `model_fields_set` 게이트로 「안 보냈다 ≠ 해제」를 가른다.
  ② **/knowledge 재설계**(D-405): 3칸 그리드(탐색기|목록|곁열)를 표준 골격으로 — 전폭
  FilterSurface(보기·프로젝트·분류·태그·작성자·정렬) + 조건 칩 + 좌측은 구조(공간·폴더)만.
  1,409줄 한 파일을 `screens/knowledge/` 일곱으로 나눴다(queryKey 접두사
  `["knowledge",...]` 유지 — D-313 재발 방지). 곁열 폐지로 목록이 넓어졌고 hideNarrow
  보강으로 제목 열이 산다(P-59 의 문서 표 건). 새 문서 모달은 카테고리 칸과
  `lockedProject` 를 얻어 프로젝트 문서 탭과 **한 벌**이 됐다(다른 공간 폴더가 보이던
  잠복 결함도 함께 수정).
  ③ **조직 콘솔 재구성**(D-406): 3판(트리|전체 표|인원)을 [헤더 하나 + 요약 타일(부서
  미지정을 타일로) + 전폭 탐색 줄 + 트리|선택 반응형 상세 판]으로. 소속 인원은 부서
  상세의 절이 되어 **모든 폭**에서 보인다(옛 셋째 판은 1920 미만에서 통째로 사라졌다).
  선택은 주소다(부서 `/departments/:id` · 조직 `?org=`). registry 의 조직 세 조각을
  걷었고(org-tree 설정 절반은 죽은 코드였다) 직책은 D-149 대로 남는다. 소속 인원 캐시
  뿌리를 `["users"]` 로 옮겨 Users 무효화가 닿는다.
  ④ **엑셀 내보내기**(D-403): `GET /api/projects/{id}/export.xlsx` — 개요·WBS·마일스톤
  세 시트, 화면과 같은 함수·같은 표본. openpyxl==3.1.5(순수 파이썬 — 폐쇄망 wheelhouse
  요구 충족, D-258 의 쓰기 절반만 뒤집음). 수식 주입은 쓰기 층(`app/core/xlsx.py`)이
  `data_type="s"` 로 끈다(값 원문 보존). 상한 5000행 + 잘림 안내 행 + `-partial` 파일명 +
  감사 로그 `project.export_xlsx`.
  ⑤ **프로젝트 화면**: WBS 접기/펼치기(button + aria-expanded, 기본 전부 펼침, 접힌
  가지는 「하위 n건」), 마일스톤 상태 톤 + 서버 판정 「n일 지남」(판정은 `milestone_unmet`
  하나 — D-390), 개요의 진행률·Health 나란히(alignItems start), 목록 상태 고르개(타일과
  같은 `filters.status` 축), 상세 헤더의 「엑셀 내보내기」 앵커.
  ⑥ 덤 둘 — `registry-active-badge` 가 REGISTRY["integrations"] 죽은 참조로 **HEAD 에서
  이미 파일째 빨갛던** 것을 실측으로 확인하고 걷었다(bc55228c 가 연동 화면을 걷을 때
  목록이 안 따라온 것). setup-wizard 의 죽은 링크 검사도 registry 이탈을 따라잡게 했다.
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — 이번 회차도 안 옮긴다(이유는 S11~S22 와 같다).
- this_commits: `f0391ac8`(카테고리 백엔드+0026) · `6d70467d`(문서 목록) ·
  `c9ae5432`(문서 상세·프로젝트 탭) · `7d1dc38b`(조직 콘솔) · `6435589a`(registry 정리) ·
  `32193a70`(엑셀 백엔드) · `0b9c9ae0`(프로젝트 프런트) · `c8f8363c`(마감 fix+번들) ·
  `6d3b583e`(D-403~406 기록)
- prev_session_commit: `d6a32933` · `1d6e0514` · `b27f948c`
- working_tree: **깨끗하다**(이 문서 커밋 뒤 기준).
- deployed: **`6d3b583e`** 가 운영에 나갔다 (2026-09-02 11:42 · `scripts/deploy-upgrade.sh`).
  Stage 0~18 전부 OK · `VERIFY_OK` · `UPGRADE_OK` · 스냅샷 `/var/backups/clovirassist/20260902-114215`.
  **스키마가 올라갔다** — alembic `0025_ticket_body_doc` → **`0026_document_categories`**
  (public 표 **95개** · 사용자 26명). 서버 venv 에 **openpyxl 3.1.5** 가 깔렸다(서버
  wheelhouse 는 빈 디렉터리라 Stage 4 가 온라인 설치를 탔다 — 부분적으로 wheel 을 넣으면
  오프라인 모드로 전환돼 전체가 깨지므로 일부러 안 넣었다). **이번 커밋의 것이 실제로
  돌고 있다**: `/opt/clovirassist` 에 `app/knowledge/categories.py` ·
  `app/projects/export.py` · `app/core/xlsx.py` 가 있고, 새 진입 번들
  `index.D1ImdgdJ.js` 와 새 화면 청크 `OrgConsole.CXxRXl0Z.js` ·
  `Knowledge.CkinapyL.js` · `KnowledgeDoc.Vm5ZUn4j.js` 가 전부 **200**(`ssl_verify_result=0`).
  스모크(`--cacert` + `--resolve clovirassist.gooddi.lab:443:10.100.64.71`):
  `/healthz` `{"status":"ok","ticket_source":"native"}` · `/readyz` `{"status":"ready"}` ·
  제품 유닛 6종 + postgresql + nginx 전부 active.
  순서는 언제나 **빌드 → 소스 고침 끝 → `check_bundle_fresh.py --write` → 커밋**이다.
  되돌리려면 `sudo /home/cloviradmin/clovirassist-upgrade/deploy/install.sh rollback --target /var/backups/clovirassist/20260902-114215`
- verification: **vitest 전량 373파일 2,811시험 전부 초록**(최종 소스에서 재실행 — 옛
  상시 빨강 `editable-body-identity-reset` 도 이번엔 초록, exit 1 은 prosemirror/jsdom 의
  기존 unhandled 경고이고 시험 실패 0). 백엔드는 `tests/security` **전량 초록** + 도메인
  스윕(knowledge·org·project·backup unit·migration 0026 왕복·검색 인덱서) 초록. 신규
  시험: 카테고리 통합 18 + 스코프 2 + 마이그레이션 4 + xlsx 단위 14 + export 통합 8 +
  export 스코프 1 + 분류 관리·카테고리 필터 vitest + 조직 콘솔 재작성 20 + 액션 7 +
  모달 4 + WBS 접기 4. `static_checks --scope full` **`STATIC_CHECKS_OK`**(`BUNDLE_FRESH_OK`
  포함). 백업은 제외 목록 방식이라 새 표가 **자동으로** 실린다(`app/backups/policy.py` —
  화이트리스트 없음·표 수 단언 시험 없음을 확인, 백업 unit 초록).
- browser: **실브라우저 캡처 8라우트 × 2테마**(`three-area-redesign` 라벨 —
  user_knowledge · user_knowledge-doc · admin_org-tree · admin_organizations ·
  admin_departments · admin_departments-detail · user_projects · user_project-detail).
  치명 실패 0. 캡처가 잡은 셋을 그 자리에서 고쳤다: 조직 선택 상태의 브랜드 워시
  (재캡처로 `brand_role_coverage` **8/8**), 「보기」 고르개의 개체 낱말 오판, setup-wizard
  죽은 링크 검사. 문서 상세의 `oversized_empty_surface` 1건은 **s22-final 원장에 같은
  라우트 14조합 전부 기존 실패**라 이번 회차 회귀가 아니다(원장 대조로 확인).
- capture: 전량 정본은 **`s22-final`** 그대로다. 부분 캡처는 전량 원장을 안 덮는다(D-306) —
  `capture_labels.after` 를 옮기지 않았다.
- ui_gate: 변화 없음 — `--stage plan` PASS 기준 유지, W15 잔여는 P-44.
- 스키마는 **95 표**다. alembic head 는 **`0026_document_categories`** — 이 회차가 표
  하나(`document_categories`)와 칸 하나(`documents.category_id`)를 더했고, 시드는 org 별
  distinct `doc_type` 에서 왔다(멱등 · downgrade 무손실 — doc_type 원본 불변).

## 이번 회차가 **안 고친** 것 — 그리고 그 이유

- **「부서 없음」 사용자 필터**: 조직 콘솔 타일이 수는 정확히 말하지만 사용자 화면에 그
  조건이 없다(서버 센티널 부재). 클라이언트 필터는 첫 쪽 밖 인원이 빠진 거짓 목록이 된다 —
  그래서 숫자와 링크만 뒀다. **P-61**.
- **WBS 엑셀의 담당자 열**: WBS 계약(`service.project_wbs`)에 이름이 없다. 화면과 같은
  표본 원칙을 지키느라 뺐다 — **P-62**.
- **`pilot_b11` 하네스**: 옛 조직 콘솔 구조(DataScreen 정렬·`org-console-people`)를
  조준한다. 기능 계약은 vitest 가 잇고, 수용 회차 재작성으로 넘겼다 — **P-63**.
- **문서 상세의 빈 편집기 면**(`oversized_empty_surface`): s22-final 원장에 14조합 전부
  있던 기존 표본이라 이번 범위에서 안 건드렸다(P-54 갈래).
- **`Callout` 판형 · `text` 열 정렬 계약**: 앞 회차가 적은 그대로 남는다(범위 밖).

## 🔴 운영이 PostgreSQL 위에서 돈다

`10.100.64.71` 의 `/healthz` 가 `{"status":"ok","ticket_source":"native"}` 로 답한다.
데이터는 전부 넘어갔고 서비스는 열려 있다. 원장은 [`EVIDENCE/S14/`](EVIDENCE/S14/README.md).

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 26 · 22 · **1,145** |
| 티켓 번호 | 1,130건에 붙어 있고 **중복 0** · 고유 1,130 · 나머지 15 는 컷오버 뒤 만든 native 티켓이다 |
| 프로젝트 코드 | **22 / 22** · 중복 0 · 전부 여섯 자 대문자 · UNIQUE 인덱스가 지킨다 |
| 첨부 | `files` 58 · 티켓 첨부 237 · 문서 첨부 54 · **DB 가 가리키는 바이트 누락 0** |
| 이관 예외 | 미해결 11 — 그중 사람이 프로젝트를 정해야 하는 **9 건은 `/integrity` 가 전부 보여 준다**(P-52) |
| 옛 이름 층 | **없다** · 옛 포트(5678·5679·8787·8788·8789) 청취 **0건** |

## 완료

- **S0~S22** — 기반 · PostgreSQL · Identity/TLS · 설치 자동화 · RBAC · Work · Knowledge ·
  Storage · AI 1·2 · n8n 제거 · Backup/Restore · Migration · Cutover · Functional E2E ·
  Final Audit. 결정 D-187~D-334.
- **화면 셋 고도화 + Legacy 정리 · 대시보드 높이 예산 · 목록 무한 스크롤 · 서버 필터/정렬 ·
  티켓 만들기 · 신호 축** ✅ — 결정 D-335~D-402.
- **문서·조직·프로젝트 3영역 재설계 + 카테고리 축 + 엑셀 내보내기 ✅** — 이번 회차,
  결정 **D-403~D-406**.

## NEXT — 다음 기능 개발은 §7.0 일반 개발 흐름을 탄다

**새 Stage 를 자동으로 만들지 않는다.** 남긴 것은 전부 Backlog 다:

1. **P-44** — 사슬의 서버 칸 982. W8·W15 게이트의 마지막 축.
2. **P-54 · P-55 · P-56 · P-59** — S22 가 적은 시각 축 넷(P-59 는 문서 표 건이 닫혔고
   전 테이블 접기 어휘 계약이 남았다).
3. **P-61 · P-62 · P-63** — 이번 회차가 새로 적은 셋(위 「안 고친 것」).
4. **P-50 · P-52 · P-57 · P-35 · P-37** — 플랫폼 축 잔여.

## BLOCKERS

- 없음.
