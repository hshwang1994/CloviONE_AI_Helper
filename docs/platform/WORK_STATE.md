# WORK STATE — ClovirAssist 자체 데이터 플랫폼 전환

<!-- 이 파일은 덮어쓴다. 날짜 절·이력 표·완료 목록을 누적하지 않는다. 이력은 이 파일의 git log 다.
     기록하는 것은 넷뿐이다: 지금 어디인가 · 무엇이 끝났나 · 다음에 무엇을 하나 · 진짜 Blocker. -->

> **세션은 여기서 시작한다.** 계획 정본은 [`MASTER_PLAN.md`](MASTER_PLAN.md),
> 큰 작업 단위는 [`BACKLOG.md`](BACKLOG.md), 설치 사양은 [`INSTALLATION.md`](INSTALLATION.md),
> 실측 목록은 [`INVENTORY/`](INVENTORY/README.md), 결정은 [`../DECISIONS.md`](../DECISIONS.md) D-187~.

## CHECKPOINT

- checkpoint_at: **2026-08-23** (S8)
- phase: **B — 도메인**
- session: **S8 완료.** 다음은 **S9 — AI Model Gateway**
- branch: `ui/mui-migration`
- last_stable_commit: **`eec4886c`** — S2 본체 커밋이고 `check_test_strength.py` 가 이 값을 읽는다.
  **S8 도 옮기지 않는다.** S8 의 시험 변경은 전부 강화 방향이다 — **시험 9파일 신설**
  (unit 5 · integration 4 · security 1 · regression 1) + 옛 시험 2파일 강화
- s1_commit: `95a89189` · s2_commit: `eec4886c` · s3_commit: `e88e4de3` · s4_commit: `6909bb96` ·
  s5_commit: `aa9c8c63` · s6_commit: `971a31fa` · s7_commit: `87dd8707`
- working_tree: clean
- **Runtime Component 가 하나 늘었다** — 파일 저장소. Installer 계약(D-205)을 **같은 세션에서
  이행했다**: Stage 11 이 SKIP 에서 OK 가 됐고, 마운트 유닛·drop-in·health probe·uninstall 경로·
  재부팅 복구가 전부 섰다. **프런트 의존과 번들은 무변경**(S8 은 화면을 안 건드렸다)

## S8 이 실제로 한 것

파일의 축이다. 이제 **파일은 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.**

| | |
|---|---|
| **마운트 판정이 함수 하나** | 가장 조용한 사고는 마운트가 안 붙은 채로 로컬 디스크에 쌓이는 것이다. 오류가 한 번도 안 나고, 마운트가 붙는 날 파일이 한꺼번에 사라진 것처럼 보인다. `mount.py::write_target_state` 하나가 답하고 `check_domain_single_source.py` 가 그 규칙을 지킨다 (**D-249**) |
| **커밋은 rename 하나** | 임시 이름에 쓰고 `fsync` 한 뒤 `os.replace`. 실패하면 **최종 이름은 한 번도 존재한 적이 없다**. 순서는 파일 먼저·DB 행 다음이다 — 거꾸로면 「행은 있는데 파일이 없다」가 되고 그건 거짓말이다 (**D-250**) |
| **마운트 옵션의 기본값을 제품이 정한다** | NFS `soft,timeo=50,retrans=2` · SMB `uid`·`gid`·`file_mode=0640`. 실검증이 찾은 결함 둘이 전부 이 한 줄이었고 **둘 다 마운트는 멀쩡했다** (**D-251**) |
| **역할마다 켜진 저장소는 하나** | 부분 유니크가 강제한다. 바꾸는 것은 두 단계다 — 자동으로 옛것을 끄면 「업로드가 어디로 가는지」가 사람 모르게 바뀐다. 운영과 백업이 같은 장치면 경고한다 (**D-252**) |
| **첨부는 부모 문서가 지킨다** | 첨부 id 는 상세 응답에 실려 나간다. 라우트 셋이 전부 `get_scoped_document_or_404` 를 먼저 지난다. 문서를 지우면 연결만 사라지고 파일 행은 남는다 (**D-253**) |
| **판정기는 넓히되 새로 안 만든다** | 오피스 문서를 받으려고 `sniff_media_type` 하나를 넓혔다. **옛 네임스페이스의 허용 집합은 한 글자도 안 바뀌었다.** OOXML 은 zip 안의 실제 항목 이름을 본다. 일반 ZIP 은 일부러 안 받는다 |
| **설치가 저장소를 안다** | Stage 11 이 기본 저장소를 세우고, **제품 렌더러로** 마운트 유닛과 drop-in 을 만들어 깔고, `storage_cli status` 의 **종료코드**로 판정한다. 셸이 `stat` 으로 장치 번호를 비교하지 않는다 |

## S8 이 드러낸 것 — 마운트가 멀쩡한데 안 되는 결함 셋

전부 실 NFS·실 SMB 위에서만 나왔다. 셋 다 `st_dev` 가드도 fstype 검사도 통과한다.

**1. NFS 기본값에서 서버가 죽으면 쓰기가 안 돌아온다.**
`Options=defaults` 는 `hard,timeo=600` 이다. 공유 서버를 내리고 파일 하나를 쓰자 **5분이
지나도 안 끝났다.** 그 상태에서는 「Storage unavailable 은 503 이지 500 이 아니다」가
**성립할 수가 없다** — 503 도 500 도 안 나가고 요청이 영영 안 끝난다. `--workers 4` 짜리
웹이 NAS 장애 하나로 통째로 멈춘다.

**2. SMB 공유에서 서비스 계정이 아무것도 못 쓴다.**
`uid=0,gid=0` 으로 붙은 cifs 는 모든 파일의 주인이 root 로 고정되고 `chown` 도 안 받는다.
증상은 「올릴 때마다 503」뿐이다.

**3. `.mount` 유닛 이름의 역슬래시가 셸에서 먹힌다.**
`/mnt/clv-nfs` → `mnt-clv\x2dnfs.mount`. 문자열에 그대로 이어 붙이면 bash 가 `\x` 를 `x` 로
먹어 **다른 유닛 이름**이 되고, `systemctl start` 가 조용히 「그런 유닛 없음」으로 끝난다.

**그리고 하네스 자신의 결함 하나.** 권한 반례를 공유 **안에** 만들었더니 cifs 가 모드
비트를 강제하지 않아 반례가 통과했다. 반례를 마운트 밖으로 옮겼다 — 거기서 확인하려는
것은 「탐지기가 거절을 알아보는가」이지 그 파일시스템의 권한 모델이 아니다.

**회귀와 자기 코드 검토가 잡은 것 셋도 함께 고쳤다.** ① 새 저장소 라우트가 점검 모드
분류에 없었다(예외로 등록했다 — 저장소가 안 붙어 점검을 켠 상황이 정확히 그 화면을
쓰는 상황이다). ② 감사 화면이 `knowledge_document`·`storage_provider` 의 한국어 이름을
몰랐다. ③ **고아 청소가 방금 올라온 파일을 지울 수 있었다** — 순서가 「파일 먼저, 행
다음」이라 그 사이의 파일은 정상인데도 가리키는 행이 없다. 청소는 이제 충분히 늙은
파일만 본다.

## 완료

- **S0 — Plan 기록.** Architecture · Decision · S0~S22 실행계획을 저장소 지속 문서로 정착.
- **S1 — 기반 정직화 · 실측 · 성능 검증.** 프로브 8건 · PG 스택 실측(D-209~D-212) ·
  `VARCHAR(n)` 감사(D-214). **제품 코드 diff 0.**
- **S2 — PostgreSQL Foundation.** 70 표 · 256 인덱스가 `0001_pg_baseline` 하나로 선다.
  SQLite Runtime 의존 0 · `--workers 1→4`. 결정 **D-215~D-221**.
- **S3 — Product Identity · Hostname · TLS.** CN/SAN 일치 · `ssl_verify_result=0`.
  결정 **D-222~D-224**.
- **S4 — 설치 · 배포 자동화 Foundation.** Clean OS 에서 세 줄, 재부팅하면 스스로 복귀.
  결정 **D-225~D-229**.
- **S5 — Identity & Access.** 권한이 표가 되고 가시성이 함수 하나가 됐다. 결정 **D-230~D-235**.
- **S6 — Work Domain.** 티켓이 세 이름으로 불리고 그 셋이 같은 티켓을 가리킨다.
  결정 **D-236~D-243**.
- **S7 — Knowledge Domain (+P-14a).** 본문의 정본이 블록이 되고 그 블록에 이름이 붙었다.
  결정 **D-244~D-248**.
- **S8 — File Storage Providers.** 위 두 절. 결정 **D-249~D-253**.

## ⚠️ 코드는 옮겼고, **데이터는 아직 안 옮겼다** (S2 가 남긴 구분, 그대로 유효)

| | 상태 |
|---|---|
| **코드** | PG 전용이다. `sqlite://` 를 주면 **기동을 거부한다**(`normalize_database_url`) |
| **스키마** | `0001`~`0006` 이 **96 표**를 만든다 (S8 이 3 표 신설) |
| **운영 데이터** | **여전히 `/var/lib/clovirone-web-assistant/web.sqlite3` 에 있다.** 아무것도 옮기지 않았다 |
| **운영 서버에 도는 것** | **아직 S2 이전 빌드다.** 운영 설치를 새 slug 로 이전하는 것은 데이터 이관과 함께 갈 일이고 S13·S14 의 몫이다 |

**S13 이 알아야 하는 것 여섯** (앞 다섯은 S6·S7 이 남긴 것 그대로):
1. 표 이름이 `departments` → `org_units`(D-234), `ticket_cache` → `tickets`(D-238)로 바뀌었다.
   **컬럼 이름은 둘 다 그대로**다.
2. 적재 직후 `app/work/numbering.py::seed_counters()` 를 부른다.
3. **Project Key 20건은 확정됐다**(D-243). 순서는 하나다 — 프로젝트 적재 →
   `project_keys.apply_confirmed(db)` → `numbering.seed_counters(db)` → 재채번.
4. **날짜 컬럼 16개가 `date`/`timestamp` 다**(D-248). 소스 문자열을 그대로 대입하면
   못 읽는 값에서 **500** 이 난다 — `app/core/dates.py::parse_date`/`parse_dt` 를 지난다.
5. **본문을 옮길 때 앞판을 함께 넘긴다**(D-247). `blocks.derive(body, carry_from=앞판)` 을
   안 쓰면 재실행마다 판이 새로 쌓인다. 다리는 `documents.legacy_page_id`(부분 유니크)다.
6. **파일을 옮길 때 `app/storage/service.py::store_bytes` 를 지난다**(D-250). 직접
   `files` 행을 만들면 체크섬·저장 키·원자적 커밋이 전부 빠지고, 그렇게 만든 행은
   `verify_files()` 에서 「바이트가 없다」로만 드러난다. 옛 첨부 셋(게시판·티켓·채팅)은
   아직 `app/core/uploads.py` 의 로컬 경로에 있고 **S14 까지 그대로 남는다**.

## 상태 — 전환 축 다섯

| 축 | 현재 | 목표 | 소유 Session |
|---|---|---|---|
| **PostgreSQL** | **설치까지 끝났다.** Installer Stage 6·7 이 cluster·role·DB·extension 을 세운다 | PG16 + pgvector + pg_trgm 이 System of Record | S2 ✅ · S4 ✅ |
| **SQLite 제거** | **Runtime 의존 0.** 코드 수준 13항이 전부 닫혔다. 다만 **운영 데이터는 아직 SQLite 에 있다** | Runtime 0 + 데이터 이관 완료 | S2 ✅ · S7 ✅ → S13·S14 |
| **Notion Migration** | **Runtime 의존 중이고 동기화 셋이 전부 실패 상태.** 미러 `tickets` 1,124 · `document_cache` 110. **받을 그릇은 이제 다 있다** — 식별자·채번(S6) · 본문·앵커·다리(S7) · **파일과 첨부(S8)** | Notion Runtime 의존 0, 데이터는 PG 로 | S13 → S14 |
| **AI** | **권한 필터 없음.** n8n → `claude-work-assistant`(8789) 가 Notion 전량을 모델에 싣는다. 인용 앵커는 있다(블록 id) — S10 은 `effective_visibility_clause` 에 연결하고 그 앵커를 쓰면 된다 | Model Gateway + 권한이 앞서는 Hybrid Retrieval | **S9** · S10 · S11 |
| **Backup** | **기본형 + 설치 스냅샷 + 파일 저장소 이관.** `pg_dump -Fc` + 체크섬 + `--exit-on-error` 복원. S8 이 **파일 쪽**을 더했다(`app/storage/archive.py`, 쓴 뒤 다시 읽어 체크섬 확인) | + Policy·Schedule·Retention·Manifest·복원 후 앱 기동 검증 | S2 ✅ · S4 ✅ · S8 ✅ → S12 |

**Identity 축은 닫혔다** — 호스트명·TLS 는 S3, slug 는 S4, 역할·권한·가시성은 S5.
**남은 한 건은 세션 쿠키 이름**(`clovirone_session`)이고 S14 다 (`BACKLOG.md` **P-33**).

**UI 축(W0~W5)은 별개로 완료돼 있고 자산은 보존한다.** 근거와 수치는
[`../ui-renewal/WORK_STATE.md`](../ui-renewal/WORK_STATE.md).
**W5B~W15 는 동결**이고 재개는 Phase E(S15~S20)다 (D-207).

## 최근 테스트

S8 은 **공유 계층 셋**을 바꿨다 — 업로드 판정기(`app/core/uploads.py`), 요청 본문 상한
(`app/core/middleware.py`), health(`/readyz`·대시보드). 그래서 백엔드 전 회귀를 다시 돌렸다.

| 대상 | 결과 |
|---|---|
| 백엔드 전 회귀 (PostgreSQL) | **통과** — `pytest tests` 전체 초록 (**3,842건**). 결과는 파일로 받고 종료코드를 따로 읽었다(**파이프 뒤에서 읽지 않는다**, S7 이 여기서 두 번 속았다). ⚠️ 첫 회차는 **도는 중에 소스를 고쳐** 결과가 그 소스를 안 담았다 — 회귀가 잡아 준 실패 둘을 고친 뒤 **처음부터 다시 돌렸다**. 도는 시험 아래에서는 소스를 안 만진다 |
| **Storage 16항 매트릭스** (S8 Exit) | **실 NFS 16/16 · 실 SMB 16/16.** 테스트 서버 **호스트에서** 돌렸다(컨테이너 아님). 원장은 [`EVIDENCE/S8/`](EVIDENCE/S8/README.md) |
| **마운트 가드** | **17건.** mountinfo 파싱(공백 이스케이프 · 잘린 줄 · 파일 없음) · 안 붙은 디렉터리를 거절 · **부모가 마운트인 것은 이 자리가 마운트인 것이 아니다** · 기대 밖 파일시스템 거절 · mountinfo 를 못 읽는 환경에서 `st_dev` 가 답한다 · **쓰기 경로가 마운트된 장치 위에 있는지까지** |
| **Adapter** | **21건.** 원자적 커밋 · **실패 시 최종 이름도 임시 파일도 안 남는다** · traversal 6종 거절 · 임시 파일이 같은 파일시스템에 산다 · 오래된 `.part` 만 치운다 · 안 붙은 저장소는 **디스크를 건드리기 전에** 거절 |
| **마운트 유닛** | **22건.** systemd 이스케이프 7종(`-`·공백·중복 `/`) · `_netdev` · **NFS 는 `soft`+시간 제한** · **SMB 는 서비스 계정 소유** · 운영자가 적은 값은 안 덮는다 · drop-in 이 **옛 값을 먼저 지운다**(`RequiresMountsFor=` 는 누적된다) |
| **판정기 확장** | **28건.** 옛 네임스페이스의 답이 **한 글자도 안 바뀐다** · OOXML 셋을 zip 안 항목으로 가른다 · 일반 ZIP 은 안 받는다 · BOM · 널바이트 · EUC-KR |
| **저장소 API** | **13건.** 권한(`STORAGE_CONFIGURE`=시스템 관리자) · 안 붙은 저장소를 그렇다고 말한다 · **역할당 하나**(409) · 마운트 밖 경로 422 · 낙관적 잠금 · 동일 장치 경고와 **그 반대편** |
| **문서 첨부** | **18건.** 바이트가 디스크와 표에 함께 선다 · 저장명은 판정된 형식에서 나온다 · 오피스 문서 · 상세 응답의 첨부 칸 · nosniff·RFC 5987 · **여러 문서가 가리키는 파일은 한 번 떼도 안 지운다** · 고아 청소와 **반대 방향은 안 치운다** |
| **저장소 백업/복원** | **8건.** 쓴 뒤 **다시 읽어** 체크섬 · 같은 것은 안 다시 쓴다 · 깨진 원본은 안 옮긴다 · 고아는 안 옮긴다 · 복원 왕복 · **「0건 성공」과 「시작조차 못 함」을 구별한다** |
| **범위 (음성)** | **11건.** 남의 부서 문서에 첨부를 **못 붙이고 못 보고 못 내려받고 못 지운다**(전부 404) · 각 단정에 「우리 것은 된다」를 함께 둔다 · 저장 키는 손으로 지어도 뿌리 밖으로 안 나간다 |
| **쓰기 거부 (회귀)** | **9건.** 안 붙은 저장소는 **503**(500 아님) · 행도 바이트도 안 남는다 · 오류 문구에 경로가 안 샌다 · `/readyz` 가 `storage_not_writable` · 커밋 실패 시 부분 파일 없음 · 행을 못 쓰면 바이트를 되돌린다 · 저장소가 사라진 파일 읽기는 **503 이지 404 가 아니다** |
| **저장소 CLI** | **9건.** Stage 11 이 부르는 그 코드다. 종료코드가 계약(쓸 수 있으면 0) · **저장소 행 → 마운트 유닛** 경로(실검증 하네스가 못 지나는 자리) · 소스 없는 저장소는 거절 |
| **스키마 ↔ 코드** | **12건.** 마이그레이션에 얼려 둔 어휘가 코드와 같은가 · **역할당 켜진 것은 하나**(그리고 꺼 둔 것은 여럿 가능) · 마운트 짝 · 상대 경로 거절 · 파일이 남은 저장소는 못 지운다 · 체크섬 길이 · **문서를 지워도 파일 행은 남는다** |
| 시험 합계 | **신설 11파일 · 168건**(unit 100 · integration 48 · security 11 · regression 9) + 설치 배선 4건. 백엔드 전체 3,669 → **3,842건** |
| `check_domain_single_source.py` | 규칙 10→**13**, 자기검증 14→**19사례**(검출 15 · 위양성 4). 마운트 판정·첨부 연결·파일 행이 각각 한 곳에서만 쓰인다 |
| 마이그레이션 왕복 | `upgrade`→`downgrade`→`upgrade` 를 실 PG 에서. `0006`: 표 93→**96** · 인덱스 358→**377** · 제약 872→**912** 가 **대칭** |
| 모델 ↔ 스키마 | autogenerate diff **0** |
| 프런트 | **안 돌렸다.** `frontend/` diff 0 이고 번들 지문이 그대로다(E1). S8 은 화면을 안 건드렸다 |
| `static_checks.sh` | S8 이 만든 실패 **0**. 남은 셋은 전부 P-09a 소유 |

### ⚠️ `static_checks.sh` 는 아직 빨간불이다 — **S8 이 만든 것이 아니다**

`BACKLOG.md` **P-09a** 가 Owner 를 갖는다. **S8 은 자기가 넣은 것 둘을 그 자리에서
고쳤다**(생성되는 systemd 주석의 가운뎃점 · 하네스의 `subprocess` encoding 누락).

| 무엇 | 어디서 왔나 |
|---|---|
| 사용자 문구의 가운뎃점(·) 7건 · em 대시 1건 · `tokens.css` 드리프트 | S5·S6 이 기록한 것 |
| `tests/unit/test_deploy_wiring.py` 의 `subprocess` encoding 누락 | S4(`6909bb96`) |

## NOW

**S8 은 끝났다.** 파일이 DB 밖에 살고, 그 자리가 진짜 그 저장소인지 매번 묻는다.

이 세션에서 가장 값이 나간 것은 표를 만든 것도, 어댑터를 만든 것도 아니라 **실제 NFS 와
SMB 를 붙여 본 것**이다. 셋 다 코드만 읽어서는 안 나온다: `hard` 마운트가 요청을 영영
안 끝내는 것도, cifs 가 `uid=0` 이면 서비스 계정을 막는 것도, 유닛 이름의 역슬래시가
셸에서 먹히는 것도 전부 **마운트가 멀쩡한 상태에서** 일어난다. 그래서 가드도, fstype
검사도, 시험도 통과한다.

두 번째는 **거부를 실패와 구분한 것**이다. 마운트가 안 붙었을 때 하는 일은 「쓰다가
실패하기」가 아니라 「아무것도 안 하기」다. 그래야 로컬 디스크에 흔적이 안 남고, 그래야
사용자가 받는 답이 500 이 아니라 503 이 된다.

## NEXT — 다음 시작점: S9 (요청 시)

**S9 = AI Model Gateway.** 사용자 요청 없이 착수하지 않는다.
범위와 Exit 는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §9.1, 설계 요지는 §5.4(D-200~D-201).

S8 이 다음 Session 에게 넘기는 것:

1. **권한 어휘 `AI_CONFIGURE` 는 이미 있다** (S5 가 미리 고정했다). 새 이름을 짓지 말고
   그것을 쓰고, 소비처를 연결한 뒤 `tests/unit/test_identity_access_seed.py` 를 본다 —
   S7 이 `SPACE_*` 에, S8 이 `STORAGE_CONFIGURE` 에 그렇게 했다.
2. **Installer Stage 12 와 색인 레인 유닛이 S9 의 몫이다.** Stage 12 는 지금 「AI Gateway 가
   소스에 있는데 이 Stage 가 설치하지 않는다」를 **실패로 만든다** — `app/ai/gateway` 를
   만드는 순간 설치가 막힌다(의도한 것이다). Stage 11 이 S8 에서 어떻게 채워졌는지가
   그대로 본보기다: 제품 CLI 를 부르고, **종료코드를 계약으로 삼고**, 셸에서 판정을 다시
   하지 않는다.
3. **모델 파일도 파일이다.** 임베딩/리랭크 모델을 어디에 둘지는 `storage_providers` 와
   별개다 — 그것은 사용자 데이터가 아니라 **재생성 가능한 자산**이고 백업 대상이
   아니다(D-203·D-204). 저장소 표에 끼워 넣지 않는다.
4. **큰 파일을 읽을 때 `service.file_path` 를 쓴다.** 바이트를 전부 메모리에 올리는
   `read_bytes` 는 첨부 하나가 10MB 라 괜찮지만, 색인이 전량을 훑을 때는 아니다.
5. **`kit.jsx` 는 S8 도 안 건드렸다.** S9 와 겹치지 않는다.

## RISK — 지금 살아 있는 것

전체는 [`MASTER_PLAN.md`](MASTER_PLAN.md) §12.

| # | Risk | 상태 / Owner |
|---|---|---|
| ~~R1~~ ~~R2~~ ~~R3~~ | (S2 가 닫음) | 해소 |
| ~~R4~~ ~~R5~~ ~~R6~~ ~~R7~~ | (S1 이 닫음) | 해소 |
| ~~R13~~ ~~R14~~ | 제품 slug · 설치 자동화 | 해소 (계약 이행은 매 Session 이 계속 진다) |
| ~~R15~~ | LXD 컨테이너가 실 장비와 다르다 | **해소** — 재부팅 축은 S4(D-229), Storage 축은 S8 이 **호스트에서** 닫았다 |
| R11 | **시험 Storage 가 실 NAS 와 다르다** | **살아 있다(의도한 대로)** — 증거 파일과 EVIDENCE 양쪽에 「실 NAS 가 아니다」를 적었다. 실 정보 수령 시 **설정만** 바꾼다 |
| R16 | GitLab 주소 부재 | **완화** — Installer 가 Remote 중립이다 |
| R17 | pgvector 검색 품질 | S10(하이브리드 가중치) |
| — | **저장소 장애 중 쓰기가 21초~180초 이상 걸린다** | **알려진 성질**(D-251). `soft` 로 돌아오게는 했지만 NFSv4 세션 복구가 겹치면 상한이 안 지켜진다. 「몇 초 만에 503」이라고 **약속하지 않는다** |
| — | **운영 데이터가 아직 SQLite 에 있고, 운영 서버는 아직 옛 slug 설치다** | S13 · S14 |

## BLOCKERS

- **없음.**

## 입력 — Blocker 는 아니지만 다음 Session 이 알아야 하는 것

| 항목 | 상태 |
|---|---|
| **20개 Project Key 명명** | **확정됐다** (2026-08-22 · D-243). 정본은 `app/work/project_keys.py::CONFIRMED`, 사람이 읽는 사본은 [`PROJECT_KEYS.md`](PROJECT_KEYS.md). **지금 적용된 프로젝트는 0건이고 그것이 정상이다** — PG 의 `projects` 가 비어 있다(적재는 S13) |
| **테스트 서버 접속** | **쓸 수 있다** — `10.100.64.71` 한정. SSH 키 인증 · sudo 는 `dist/ops/server.env`(gitignore). 값을 tracked 파일·커밋·로그에 복사하지 않는다 |
| **테스트 서버의 시험 Storage** | **세워 뒀다** — NFS export `/srv/clv-nfs-export` · Samba share `/srv/clv-smb-share`(`[clvtest]`) · 마운트 `/mnt/clv-nfs`·`/mnt/clv-smb`(enabled, 재부팅 복귀 확인) · 하네스 사본 `/opt/clv-matrix-src` · 시험 계정 `clvsvc`. SMB 자격증명은 `/etc/clovirassist/secrets/smb_matrix`(0600, root)이고 **값은 저장소에 없다**. S22 가 그대로 다시 돌릴 수 있다 |
| **LXD** | 이 서버에 **초기화해 뒀다**(dir 스토리지 풀 + `lxdbr0`). `sudo bash scripts/lxd_rehearsal.sh <src.tar.gz>` 로 언제든 다시 돈다. **`/dev/kvm` 이 없어 LXD VM 은 못 쓴다** — 실 재부팅이 필요하면 서버 자체를 재부팅한다(S8 이 그렇게 했다) |
| **리허설 소스 tarball** | 작업 트리를 그대로 tar 로 만들어 넣는다(`.git`·`node_modules`·`docs`·`tests`·`var` 제외). **LF 로 저장돼 있어야 한다** |
| **canonical 호스트** | `https://clovirassist.gooddi.lab` → 10.100.64.71. 옛 이름은 DNS 에 없다(NXDOMAIN). 인증서는 자체서명이고 사본이 `dist/ops/` 에 있다 |
| **하네스를 원격에 겨눌 때** | `UI_QA_TLS_CA` 로 그 인증서를 준다 — `tls.py` 가 파이썬과 Node 양쪽에 심는다. **Chromium 의 페이지 이동만은 운영체제 신뢰 저장소를 본다.** QA 계정 `ui-qa@goodmit.co.kr` 은 **보관 상태**다 |
| **시험용 PostgreSQL** | 개발 머신 컨테이너 `clovir-s2-pg`(포트 55433). `CLOVIR_TEST_PG_URL` 로 덮어쓴다 — 주소는 `postgresql+psycopg://` 로 적는다(`psycopg2` 는 안 깔려 있다) |
| **전 회귀를 백그라운드로 돌릴 때 (Windows)** | **`run_full_regression.sh` 가 이제 스스로 `< /dev/null` 을 붙인다** (P-09e). 근본 조치는 P-09e 가 소유한다 |
| **회귀 결과를 읽을 때** | **파이프 뒤에서 읽지 않는다.** `pytest … \| grep …` 의 `$?` 는 **grep 의 종료코드**다. 파일로 받고(`> out.txt 2>&1`) 종료코드를 따로 찍은 뒤 그 파일을 본다. 그리고 **도는 시험 아래에서 `git stash` 를 하지 않는다** |
| **원격에서 오래 걸리는 명령을 돌릴 때** | **하네스가 걸릴 수 있는 자리에는 시간 제한을 건다.** S8 이 `hard` 마운트에서 5분을 통째로 잃었다 — 걸린 하네스는 결과를 한 줄도 안 내므로 「걸렸다」는 사실조차 증거로 안 남는다 |
| **`pg_dump`/`pg_restore`** | 개발 머신(Windows)에는 **없다**. `PG_BIN_DIR` 를 비워 두면 안 된다 |
| **Notion 토큰** | 운영 정본은 `/etc/clovirone-web-assistant/secrets/notion_{docs,report}_token`(0640, sudo), 개발 사본은 `var/secrets/`(gitignore) |
| 실 NFS/NAS 장비 정보 (현재 없음이 **확인됨**) | **S8 은 시험 Storage 로 끝났다.** 실 정보를 받으면 `storage_providers` 행의 `source`·`options` 만 바꾸고 `deploy/install.sh storage` 를 다시 돌린다 — Application 수정은 없다 (U8·U9) |
| 제품 Domain 밖 Notion DB 3종 (179 · 23 · 9) | 기본값 = 이관하지 않음 (U19) |
| GitLab Repository 주소·자격증명 | Installer 가 Remote 중립이라 **주소가 정해지면 설정만 바꾼다** (R16) |

<!-- 형식: `- <무엇을 못 하는가> / 원인 <외부 주체> / 우회 <있으면> / 요청일 <YYYY-MM-DD>`
     "시간이 없다", "코드가 많다", "테스트가 오래 걸린다" 는 blocker 가 아니다. -->
