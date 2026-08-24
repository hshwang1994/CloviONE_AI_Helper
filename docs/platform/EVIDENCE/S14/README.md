# EVIDENCE — S14 (Project Code 정책 · Cutover · Legacy 제거)

> 이 폴더의 파일이 정본이다. 아래 글은 **그 파일을 어떻게 읽는가**만 적는다.

## 1. Project Code 정책이 바뀌어서 Dry Run 을 다시 돌렸다

S13 의 회차는 **사람이 확정한 Project Key 20건**을 이름으로 붙였다. 그 정책이
2026-08-24 에 바뀌었다(**D-282** · **D-283**): 코드는 서버가 짓는 대문자 여섯 글자이고,
사람이 입력할 수도 바꿀 수도 없으며, 옛 `GIT-*` 이름은 이관하지 않는다.

정책이 티켓의 **이름**을 바꾸므로 S13 의 증거는 그대로 쓸 수 없다. 같은 소스로 세 회차를
다시 돌렸다.

| 회차 | 대상 DB | 무엇을 증명하나 |
|---|---|---|
| [`dry_run_pass1`](dry_run_pass1.txt) | `clovir_s14a` (빈 DB) | 새 정책으로 전부 건너간다 |
| [`dry_run_pass2`](dry_run_pass2.txt) | `clovir_s14a` (같은 DB) | **재실행이 아무것도 안 바꾼다** |
| [`dry_run_passB`](dry_run_passB.txt) | `clovir_s14b` (**다른** 빈 DB) | **Cutover 가 Dry Run 과 같은 이름을 낸다** |

세 회차 모두 **검사 64건 전부 통과 · blocking 0 · 분류된 예외 14** 다.

### 왜 세 번째 회차가 있나 — 이 정책의 핵심이 거기 있다

Dry Run 과 Cutover 는 같은 도구가 **서로 다른 데이터베이스**에 대고 도는 회차다. 코드를
무작위로 지으면 같은 프로젝트가 두 회차에서 다른 코드를 받고, 그 순간 Dry Run 이 검증한
티켓 이름 1,120개가 Cutover 에서 **전부 다른 문자열**이 된다 — Dry Run 이 증명한 것이
Cutover 에서 성립하지 않는다는 뜻이다.

「재실행해도 같다」로는 이것을 못 잡는다. 재실행은 **이미 붙은 코드를 안 건드리기만
하면** 통과하기 때문이다. 그래서 세 번째 회차는 `clovir_s14a` 를 전혀 모르는 **빈 DB** 에
같은 소스를 처음부터 다시 적재하고, 두 DB 를 행 단위로 대조한다.

[`determinism.txt`](determinism.txt) 가 그 대조다:

```
프로젝트 수                 : 22 / 22
티켓 수                     : 1133 / 1133
프로젝트 코드가 다른 건수   : 0
티켓 이름이 다른 건수       : 0
번호를 받은 티켓            : 1120
코드 모양 위반 (재계산)     : 0
코드에서 안 나온 canonical  : 0
옛 이름 표가 남았나         : 0
tickets.legacy_key 가 남았나: 0
```

마지막 넷은 **제약을 믿지 않고 다시 센 값**이다. `ck_projects_code_shape` 가 있으니
모양이 틀릴 리 없다는 것은 사실이지만, 그 제약이 사라지는 날에도 이 숫자가 답해야 한다.

### 무엇이 S13 과 달라졌나

| | S13 (옛 정책) | S14 (새 정책) |
|---|---|---|
| 코드를 가진 프로젝트 | **20 / 22** — 확정표에 없는 둘은 못 받았다 | **22 / 22** |
| 코드의 근거 | 사람이 확인한 이름 표 | 소스가 주는 안 변하는 값(`notion_page_id`, 없으면 `projects.id`)의 SHA-256 |
| 이름 층 | 셋 (`canonical` · `legacy` · 별칭) | **둘** (`canonical` · `uuid`) |
| `legacy_key` | 1,125건 | **컬럼이 없다** (`0012` 가 내렸다) |
| `ticket_key_aliases` | 1,125행 | **표가 없다** |
| `project_key_registry` | 21행 | **표가 없다** — 유일성의 정본이 `projects.code` 하나다 |
| 검사 수 | 64 | 64 (넷이 빠지고 넷이 들어왔다) |

빠진 검사 넷은 「중복 `legacy_key`」·「legacy/canonical 충돌」·「예약 Key 가 서 있는가」·
「고아 별칭」이고, 전부 **대상이 사라져서** 뺐다. 대상이 없는 검사를 남겨 두면 언제나
0 을 세고 통과한다 — 이 저장소가 D-213 에서 이름 붙인 그 실패 모양이다.

들어온 검사 넷은 「코드를 본 프로젝트」·「코드 없는 프로젝트」·「모양이 틀린 코드」·
「겹친 코드」다. 첫 번째가 나머지 셋의 **표본 수**를 함께 남긴다: 프로젝트가 0건인 DB
에서는 셋 다 0 이라 전부 통과하는데, 그 통과는 「검사했다」가 아니라 「볼 것이 없었다」다.

### 옮기지 않은 것 — 사용자가 정한 그대로

* **10MB 초과 첨부 2건**(34MB 회의 녹음 · 15MB PDF)은 이관하지 않는다. 제품 업로드
  한도를 넘고, 한도를 넓히는 것은 이 Session 의 범위가 아니다(D-280).
* **매칭되지 않는 Notion 사용자 3명**은 활성 사용자로 만들지도, 이름으로 추측 매칭하지도
  않는다. `user_unmapped` 로 분류돼 사람이 하나씩 정할 목록에 남는다(U11).

## 2. 어디서 돌렸나

| | |
|---|---|
| 소스 (SQLite) | `10.100.64.71:/var/lib/clovirone-web-assistant/web.sqlite3` 의 무중단 스냅숏. S13 이 뜬 것과 **같은 파일**이라 두 Session 의 수를 그대로 비교할 수 있다 |
| 소스 (Notion) | 실 워크스페이스. 토큰은 운영 정본 `/etc/clovirone-web-assistant/secrets/notion_docs_token` 을 그 자리에서 읽었다. 저장소·로그·보고서 어디에도 값이 없다 |
| 대상 | 테스트 서버의 사용자 공간 PG `~/s1pg`(16.15) 안의 **임시 DB 둘** — `clovir_s14a` · `clovir_s14b`. 운영 DB 가 아니다 |
| 스키마 | `0012_project_code_policy` 까지. 실 PG 에서 `upgrade` 가 통과했다 |

## 3. Cutover — 운영을 실제로 옮겼다 (2026-08-24)

**운영 서버 `10.100.64.71` 이 이제 PostgreSQL 위에서 돈다.** `/healthz` 가
`{"status":"ok","ticket_source":"native"}` 로 답한다 — 제품이 자기 DB 를 읽는다는 뜻이다.

| 파일 | 무엇인가 |
|---|---|
| [`cutover.txt`](cutover.txt) · [`cutover.json`](cutover.json) | Cutover 회차 원장. **검사 64건 전부 통과 · blocking 0 · 분류된 예외 14** |
| [`cutover_db_counts.txt`](cutover_db_counts.txt) | 적재된 **운영 DB 에 직접 물은** 수. 보고서를 믿지 않고 다시 센 값이다 |
| [`determinism_cutover.txt`](determinism_cutover.txt) | 🔴 Dry Run 두 DB 와 **운영 DB** 의 이름 대조 |
| [`cutover_app_read.txt`](cutover_app_read.txt) | 앱이 실제로 읽는가 — 읽기 경로 **16개 전부 200** |

### 🔴 결정성이 실제로 성립했다

이 정책의 핵심 약속은 「같은 프로젝트가 Dry Run 과 Cutover 에서 같은 코드를 받는다」였다.
서로 데이터를 공유하지 않는 **세 데이터베이스**에서 잰 결과다:

```
프로젝트 수  a/b/운영      : 22 / 22 / 22
코드가 다른 건수 a↔b       : 0
코드가 다른 건수 a↔운영    : 0
티켓 수 a/운영             : 1133 / 1133
티켓 이름이 다른 건수 a↔운영: 0
```

임시 DB 에서 `ZCYMPW` 였던 프로젝트는 운영에서도 `ZCYMPW` 다. 티켓 1,133건의 이름이
한 글자도 다르지 않다.

### 적재된 운영 DB

| | |
|---|---|
| 사용자 · 프로젝트 · 티켓 | 25 · 22 · 1,133 |
| **코드를 받은 프로젝트** | **22 / 22** — S13 에서는 20 이었다. 확정표에 없던 둘(`S협회 …` · `M. 고려대학교 …`)이 처음으로 코드를 받았다 |
| 이름을 받은 티켓 | 1,120 (미해결 예외 13) |
| 문서 · 판 · 관계 · 첨부 | 110 · 110 · 121 · 6 |
| 다리(`legacy_mapping`) | 1,372 |
| 옛 이름 표 · `tickets.legacy_key` | **0 · 0** — `0012` 가 내렸다 |
| 파생 넷 | **전부 0** — 적재 직후에는 비어 있는 것이 정상이다(D-270 · D-276). 색인 레인이 채운다 |

### Cutover 가 찾아낸 것 — 설치기 결함 넷

리허설이 아니라 **실제 설치**라서 보인 것들이다. 넷 다 「설치가 `OK` 를 찍는데 제품이
안 되는」 모양이고, 넷 다 고쳐서 `deploy/install.sh` 에 들어갔다. (다섯 번째는 백업 쪽에서
나왔다 — 아래 §5 의 CREATEDB.)

| # | 무엇이 | 어떻게 드러났나 |
|---|---|---|
| 1 | 옛 설치의 `DATABASE_URL=sqlite://…` 를 **존중**했다 | Stage 9 가 `alembic upgrade head` 에서 죽었다. 제품이 PG 전용이라 스킴을 보고 거절한다(D-215) |
| 2 | 이전이 **디렉터리를 안 파고들었다** | 새 자리에 `secrets/` 가 이미 있어서(S8 의 SMB 자격증명) 옛 `secrets/` 가 통째로 안 옮겨졌다 — Notion 토큰 넷이 옛 경로에 남고 설치는 `OK` 를 찍는다 |
| 3 | 「이전할 것이 있나」 판정이 **남은 것을 안 봤다** | `/opt` 와 `web.env` 가 먼저 사라지고 `/etc/<옛>/secrets` 만 남자, 다시 실행해도 영원히 안 옮겼다 |
| 4 | 비밀 디렉터리가 **0700** 이었다 | 소유가 `root` 라 그룹(서비스 계정)에 권한이 없다 — 제품이 자기 비밀을 못 읽는다. 파일이 0640 이어도 디렉터리를 통과 못 하면 소용없다. Cutover 이관이 Notion 토큰을 읽으려다 `PermissionError` 를 냈을 때 처음 보였다 |

넷 다 `tests/unit/test_deploy_wiring.py` 가 성질로 고정한다.

### 그리고 이관 검증이 **자기 일을 했다**

첫 Cutover 회차는 검사 셋이 빨갰다: `config_versions` 24→25 · `integrations` 4→5 ·
`search_documents` 0→1,238. 데이터 결함이 아니라 **순서 문제**였다 — 설치 Stage 10 이
행을 심고 Stage 17 이 유닛을 띄우는 바람에, 이관이 「아무도 안 만진 DB」가 아닌 곳에
적재했다. 그 셋은 정확히 그것을 잡으라고 있는 검사다.

DB 를 스키마만 있는 상태로 되돌리고(`dropdb`/`createdb`/`alembic upgrade head`) 다시
적재하자 64건 전부 통과했다. **검사를 조정하지 않았다.**

## 4. 되돌리기 지점 (S14 Exit)

| 시점 | 되돌릴 수 있나 | 무엇으로 |
|---|---|---|
| Dry Run | **전면** | 임시 DB 를 지우면 된다. 운영은 읽기만 했다 |
| 설치 이후 · 적재 전 | **전면** | `/var/backups/clovirassist-precutover-20260823T163710Z/` — 옛 SQLite(`web.sqlite3` · 워커 정지 뒤의 `web-final.sqlite3`) · `var-lib.tgz`(업로드·생성물) · `etc.tgz`(설정) · `opt-clovirone-web-assistant.tgz`(**옛 코드 전체**, venv 제외) · `systemd/`(유닛 · nginx vhost · cron). 전부 `SHA256SUMS` 가 붙어 있다 |
| 적재 이후 · 서비스 Open 전 | **전면** | 위와 같다. 옛 코드와 옛 데이터가 둘 다 있으므로 옛 설치를 그대로 되세울 수 있다 |
| **서비스 Open 이후** | **부분** | 그 뒤 사용자가 넣은 것은 유실된다. 그래서 Open 직전에 위 셋(원장 · DB 직접 확인 · 읽기 경로 16개)을 전부 통과시켰다 |

옛 SQLite 원본(`/var/lib/clovirassist/web.sqlite3`)은 **지우지 않았다.** 설치가 새 자리로
옮겨 놓았고 제품은 그것을 열지 않는다 — `normalize_database_url` 이 `sqlite://` 를 거절한다.

## 5. Legacy 제거 — 코드가 없어야 껐다고 말할 수 있다

Cutover 로 데이터가 넘어간 뒤, 런타임에서 Notion 을 읽고 쓰는 코드 **열다섯**을 지웠다
(D-284 가 목록과 「남긴 것」을 표로 적는다).

지우기 전에 **왜 설정으로는 안 되는지**를 실제로 겪었다. Cutover 직후 워커를 올리자 미러
동기화 틱이 **PostgreSQL 을 향해** 돌기 시작했다 — 그 표들은 이제 미러가 아니라 정본이다.
DB 설정을 비웠는데도 계속 돌았다. **환경파일이 이겼다.** 그리고 그 값이 유효한 데이터베이스
id 라 동기화가 성공하기 시작했다. 확인해 보니 데이터는 무사했지만(티켓 1,133 · 이름 1,120
그대로) 그것은 운이었다.

되살아나지 않는 것을 `tests/unit/test_notion_runtime_removed.py` 가 고정한다 — 파일 열다섯이
없고, `app/` 어디서도 그 이름을 부르지 않고, 워커에 틱이 없고, 런타임 SSRF 목록에
`api.notion.com` 이 없다. **이관 도구의 목록에는 있어야 한다**는 반대편 단언도 함께 건다.

### 백업이 「복원할 수 있다」를 다시 증명했다 — 그리고 그전엔 못 했다

S12 가 세운 복구 리허설(`scripts/restore_rehearsal.py`)을 운영 데이터로 돌렸더니 세 번
연속 실패했다. 셋 다 **덤프가 아니라 권한**이었다:

| # | 무엇이 | 어떻게 고쳤나 |
|---|---|---|
| 1 | DB role 에 **CREATEDB 가 없다** | 리허설이 조용히 `structure_only` 로 떨어져 「복원했다」를 영원히 증명하지 못한다. `install.sh` 가 role 에 CREATEDB 를 준다 |
| 2 | 비수퍼유저가 `CREATE EXTENSION vector` 를 못 한다 | 확장을 `template1` 에 넣는다 — 새로 만드는 DB 가 그것을 물고 태어나고, 덤프의 `CREATE EXTENSION IF NOT EXISTS` 는 그냥 지나간다(실측으로 확인) |
| 3 | `COMMENT ON EXTENSION pg_trgm` 에 **소유자가 아니라며** 죽는다 | `pg_dump`/`pg_restore` 양쪽에 `--no-comments`. 덤프에 실제 COMMENT 객체가 둘뿐임을 세어 보고 넣었다 |

고친 뒤 **8단계 전부 통과**(`restore_rehearsal.txt`)했고, 복원본을 물고 띄운 앱이 읽기 경로
13개를 전부 200 으로 답했다. 🔴 이 셋은 **백업 자체는 매일 성공**하므로 리허설을 돌려 보기
전에는 아무 데도 안 보인다.

### 걷어내고 나서야 보인 것 — 자체 행이 이류 시민이었다

이관 전에는 모든 행이 소스에서 왔고 그래서 전부 `notion_page_id` 를 가졌다. 코드 곳곳이 그
칸을 **행의 이름처럼** 썼다. Cutover 뒤로는 새 프로젝트와 새 티켓에 그 칸이 없다.

일곱 자리가 `None` 을 받아 「그런 것 없음」으로 읽었다 — 진행률·헬스·트리가 동시에 비고,
새 티켓이 검색에서 전역 관리자에게만 보이고, 판에서 카드가 안 열리고 상태를 못 옮기고 버린
티켓이 안 사라지고, 알림 제목이 폐기한 `GIT-*` 였다. 전부 조용하다 — 오류를 안 낸다.

목록과 고친 방법은 D-284 의 표에 있다. 변환을 함수 하나로 모으고
(`app/tickets/models.py::api_page_id`) `tests/regression/test_native_rows_are_first_class.py`
가 **행을 심고 화면이 부르는 경로를 그대로 태워서** 일곱을 한 번에 지킨다.

그중 하나는 성질이 달라서 따로 적어 둔다: **진행률 재계산이 부르는 사람을 잃었다.** 유일한
호출부가 지워진 동기화 회차였다. 계산기는 남고 부르는 사람만 사라지는 — 이 저장소가 이미
한 번 겪은 사고와 **똑같은 모양**이다(운영 프로젝트 22건 전부 "아직 계산하지 않았습니다").
그래서 주기 스윕에 붙였고, `tests/regression/test_project_progress_actually_computed.py` 는
이제 「계산기가 옳은가」가 아니라 **「누가 부르는가」**를 본다.

### 옛 slug 운영 스크립트 아홉 — 그리고 두 벌 사이로 빠진 것

S4 가 설치·업그레이드·롤백·백업을 `deploy/install.sh` 하나로 합쳤는데, 옛 slug 스크립트
아홉이 저장소에 남아 있었다(`install-`·`upgrade-`·`rollback-`·`backup-`·`validate-clovirone-
web-assistant.sh` · `backup-cron.sh` · `install-backup-cron.sh` · `update-from-git.sh` ·
`apply-app-update.sh`). 옛 systemd 유닛 넷과 옛 nginx vhost·logrotate 사본도 함께 있었다.
INSTALLATION.md §9 가 「걷어내는 것은 S14」라고 적어 두었다.

시험도 두 벌이었다 — `test_update_script_contract.py` · `test_upgrade_script_contract.py` 와
`test_deploy_wiring.py` 안의 열넷. 그 시험들은 **아무도 안 쓰는 스크립트**를 지키고 있었다.

🔴 **두 벌 사이로 성질 하나가 빠졌다.** 옛 백업은 사용자가 올린 파일(`/var/lib/<slug>`)을
담았는데 `deploy/install.sh::take_snapshot` 은 안 담았다. `install.sh upgrade` → `rollback`
경로가 DB 만 되돌리고 첨부 파일은 안 되돌린다는 뜻이다 — 화면에는 오류가 아니라 **빈 첨부**로
보인다. 옛 스크립트의 시험이 계속 초록이라 이 갭이 안 보였다.

**지운 것보다 옮겨 오지 않은 것이 조용하다.** 설치기에 넣었고(`data.tar.gz` · 옛 slug 용
`data-legacy.tar.gz`, 되받을 수 있는 `ai/models` 는 제외) rollback 이 풀고 소유권까지 다시
잡는다. 시험은 한 벌로 합쳤다 — `test_deploy_wiring.py` 가 **배포되는 것 하나만** 본다
(`qa-contract-replaced-by:` 두 줄).

남긴 것 둘과 이유:

* `scripts/build-bundle.sh` — `MANIFEST.sha256` 을 만드는 **유일한** 자리이고
  `install.sh --source bundle` 이 그것을 읽는다. 산출물 이름만 새 slug 로 갈았다.
* `scripts/lxd_rehearsal.sh` — 옛 slug 설치를 **일부러 만들어** 이전을 리허설한다. 옛 이름이
  거기 있는 것이 그 시험의 내용이다.

### 화면 문구 — 하나는 사용자에게 **거짓말**을 하고 있었다

코드가 아니라 **말**이 남는 자리도 훑었다. 휴지통의 영구 삭제 확인 창이 이렇게 말하고 있었다:

> 「지금 영구 삭제하면 노션 원본이 보관처리되어 목록에서 사라집니다(노션 휴지통에서 30일 내
> 복구 가능). 계속할까요?」

되돌릴 여지를 주던 것은 **노션의 휴지통**이었지 우리가 아니었다. 그 안전망이 사라진 지금
영구 삭제는 행을 진짜로 지우고 딸린 댓글·첨부까지 CASCADE 로 가져간다. 되돌릴 수 없는
동작을 「복구 가능」이라고 말하면 사용자는 그것을 믿고 누른다. `trash.test.jsx` 가 이제
「되돌릴 수 없습니다」가 그 창에 있고 「노션」이 없는 것을 함께 본다.

나머지 문구는 두 부류였다. 하나는 **고칠 방법이 없는 경고**다 — `notion_sync_error` 와
`notion_missing_at` 은 쓰는 코드가 없어져 이관 시점 값이 영원히 남는데, 그 배너를 계속
띄우면 사용자는 배너 자체를 안 읽게 되고 그러면 진짜 경고도 함께 묻힌다. 다른 하나는
**없어진 선택지를 있는 척하는 갈래**다(WBS 탭의 「노션 짝이 없어 작업을 가져올 수 없습니다」).

그리고 그 사이에서 결함 하나가 더 나왔다: 프로젝트 상세의 **티켓 탭이 목록을 아예 안
불렀다.** 화면이 `notion_page_id` 로 조건을 걸었기 때문이다 — Cutover 이후에 만드는
프로젝트에는 그 칸이 영원히 없으므로 그 탭은 언제까지나 비어 있게 된다. 티켓은 붙어 있고
화면만 비고, 오류는 안 난다. 조건을 포털 `project.id` 로 바꿨고(서버는 이미 두 축으로
맞춘다) `test_native_rows_are_first_class.py` 와 `projects.test.jsx` 가 양쪽에서 붙든다.

## 6. 완료 보고 뒤 실 화면 재점검 — 행 수 검증은 이관 품질을 증명하지 못한다

사용자가 운영 `/team-docs` 를 직접 열어 옛 Notion 문구·동기화 실패 메시지가 남은 것과
문서 다수가 「제목 없음」·「기타」로 보이는 것을 잡았다. 「문서 110건이 있다」는 행 수
검증이었지 **내용 검증이 아니었다.**

[`fidelity_audit_final.txt`](fidelity_audit_final.txt) 가 그 내용 검증이다.
`scripts/audit_migration_fidelity.py` 로 Notion 캐시 원본과 대상 DB 를 축마다(제목·본문·
작성자·날짜·관계·태그·첨부·블록 종류) 대조한다. **첫 결과는 손실 42,321건·17개 축**
(image·table 블록 보존율 0%, 원본 생성/수정일 100% 손실, 티켓 첨부 「파일은 있는데 안
붙었다」)이었다.

진짜 결함 셋을 찾아 고쳤다:

1. `data:` URI 이미지(본문에 이미지가 base64 로 그대로 박힌 「external」타입)가 네트워크로
   못 나가 문서 하나를 통째로 막던 것 — `app/migration/transform.py::media_bytes` 가 그
   자리에서 디코드한다.
2. 티켓의 페이지 속성 첨부("파일과 미디어")가 문서 경로(`files`+`document_attachments`)로만
   가서 조용히 고아가 되던 것(D12 — 티켓은 `ticket_attachments` 하나뿐) —
   `app/migration/load.py::load_files` 가 본문 미디어와 같은 판정으로 갈래를 나눈다.
3. 안전한 재이관(`reimport-bodies`, D5)이 **첨부를 아예 안 건드리고 있었다** — 함수
   docstring 의 약속과 달리 `load_files()` 호출 자체가 없었다. 배선을 넣었고, 이미 2번
   버그로 잘못 옮겨진(운영에 실제로 있던) 흔적을 자가 치유하는 경로도 같은 함수에 넣었다
   (`_reroute_file_to_ticket`) — 다시 안 받고 저장된 바이트를 그대로 옮긴다.

셋 다 Known-Bad/Known-Good 로 검증했다(가지를 되돌리면 새로 추가한 시험이 빨개진다):
`tests/unit/test_migration_transform.py`, `tests/integration/test_migration_bodies_and_visibility.py`,
`tests/integration/test_migration_dry_run.py`.

운영 백업을 그대로 복원한 로컬 사본(`s14_full_migration_probe`)에 다시 돌려 **손실
42,321→44건, 손실 난 축 17→6개**(문서 축 하나 · 티켓 축 셋 · 블록 축 둘)로 줄였다. 남은
6개는 전부 설명된다:

* `doc.project`(34건) — `document_relations` 는 문서↔문서만 가리켜 프로젝트를 못 가리킨다.
  손실이 아니라 **태그로 대신 남긴 설계 선택**(D6)이고 화면 검색·필터에 걸린다.
* `ticket.status`/`ticket.assignee`(각 1건, 같은 티켓) — 컷오버 뒤 실사용자가 포털에서
  실제로 고친 값이다. **아무 손도 안 댄 별도 백업 사본**으로 되짚어 컷오버 시점 이후에
  값이 바뀐 것을 확인했다 — 되돌리면 그것이야말로 실사용자 작업을 지우는 사고다(D5).
* `ticket.attachment`(2건) — 로컬 샌드박스에 운영 파일 바이트가 없어서 못 옮긴 것뿐,
  코드 결함이 아니다(운영 재실행에서는 문제없이 옮겨졌다 — 아래 §6-1).
* `block.image`/`block.table`(합 6건) — 10MB 업로드 상한과 "사용자가 고친 본문은 안
  덮는다"(D5) 두 제품 정책이 정직하게 낸 대가다.

**티켓도 같은 관점으로 재검증했다** — 행 수가 아니라 제목·본문·상태·우선순위·담당자·
프로젝트·날짜·댓글·첨부를 원본과 대조했고 위 셋 말고 새 손실은 없었다.

### 6-1. 실제 운영 DB에 적용 — [`fidelity_reimport_production.txt`](fidelity_reimport_production.txt)

`reimport-bodies` 를 운영에 돌렸다: 티켓 본문 갱신 153건, **댓글 신규 324건**(이관 첫
회차가 한 건도 안 옮긴 채로 남아 있었다), 문서 갱신 110건, 첨부 신규/갱신 8건, 그리고
공간 「팀 문서」의 소속(`owner_kind`)이 `unset` 이던 것을 자동으로 조직 소유로 고쳤다
(D7 이 이미 잡은 그 결함이 운영 데이터에 실제로 남아 있었다). **blocking 0.** 로컬
샌드박스에서 「바이트가 없다」로 막혔던 첨부 2건은 운영(진짜 바이트가 있다)에서는
`html`/`sql`/`py` 확장자가 티켓 첨부 허용 목록(이미지·PDF 뿐, D12)에 안 맞아 분류된
예외로 남았다 — 상한을 이관 때문에 넓히지 않는다는 원칙(D-280)과 같은 결이다.

### 6-2. 재배포 직후 화면에서 결함이 둘 더 나왔다

`/knowledge` 의 분류·태그가 화면에서 전부 사라져 있었다. 원인 둘:

* `Knowledge.jsx` 가 `/api/tags` 를 불렀는데 실제 라우트는 `/api/knowledge/tags` 다 — 주소
  오타. 시험(`knowledge-list.test.jsx`)도 같은 틀린 주소를 흉내 내고 있어서 안 잡혔다.
* 문서 목록 API 가 `doc_type`/`tags` 를 안 실었다 — 상세 API(`_document_json(...,
  tags=...)`)는 실었는데 목록 호출부만 그 인자를 안 줬다. 데이터는 안 사라졌고(운영
  `document_tags` 106행 그대로) **화면이 그것을 안 그렸을 뿐이다.**

`app/knowledge/tags.py::of_documents` 로 문서 수만큼 안 묻고 한 질의로 배치 조회하게
고쳤고(즐겨찾기와 같은 이유), `Knowledge.jsx` 목록 줄에 분류·태그 칩을 그렸다. 둘 다
Known-Bad 로 검증했다(`test_knowledge_favorites.py::test_the_list_carries_doc_type_and_tags`,
`knowledge-list.test.jsx`). 임시 검증 계정으로 운영 화면에서 직접 확인했다 — 분류 필터가
21개 값으로 채워지고, 문서 줄마다 칩이 보이고, 본문 안 이미지가 실제로 렌더링된다(검증
계정은 확인 뒤 지웠다).

전체 회귀에서도 하나 더 잡았다: 주간 다이제스트 시험 셋이 죽은 미러 표(`document_cache`)
에 표본을 심고 있었다 — 리더 함수는 이미 정본(`documents`)을 읽게 고쳐졌는데 시험은
안 따라가 늘 0건으로 통과했다. 시험을 정본 표로 옮겼다(`test_assistant_api.py`).
