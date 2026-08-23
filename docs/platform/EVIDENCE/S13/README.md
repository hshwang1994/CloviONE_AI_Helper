# EVIDENCE — S13 (Migration Tool + Dry Run)

> 이 폴더의 파일이 정본이다. 아래 글은 **그 파일을 어떻게 읽는가**만 적는다.

## 무엇을 어디서 돌렸나

**실 운영 SQLite** + **실 Notion** → **임시 PostgreSQL**. 운영 원본은 읽기만 했다.

| | |
|---|---|
| 소스 (SQLite) | `10.100.64.71:/var/lib/clovirone-web-assistant/web.sqlite3` 의 무중단 스냅숏. `sqlite3 'file:…?mode=ro' ".backup"` — 읽기 전용 URI 라 체크포인트도 안 일어난다 |
| 소스 (Notion) | 실 워크스페이스. 토큰은 운영 정본 `/etc/clovirone-web-assistant/secrets/notion_docs_token` 을 **그 자리에서** 읽었다(sudo). 저장소·로그·보고서 어디에도 값이 없다 |
| 대상 | 테스트 서버의 사용자 공간 PG `~/s1pg`(16.15) 안의 **임시 DB `clovir_s13`**. 운영 DB 가 아니다 |
| 소스 지문 | alembic `0061` · 표 75 · `ticket_cache` 1,123 · `document_cache` 110 · `users` 25 · `audit_logs` 1,401 |

## [`dry_run_pass1.txt`](dry_run_pass1.txt) · [`dry_run_pass1.json`](dry_run_pass1.json) — 1회차

**검사 64건 전부 통과 · blocking 0 · 분류된 예외 14.**

Exit 조건 세 항이 이 파일 안에서 각각 보인다:

| Exit 조건 (MASTER_PLAN §9.1) | 어디서 보이나 |
|---|---|
| **무결성 전항 0 (또는 Exception 분류)** | 「검증」 절 64줄 전부 `OK`. 못 옮긴 것은 `## Finding` 의 `classified` 14건이고 **하나도 빠짐없이 사유가 붙어 있다** |
| **길이 초과 0** | `길이 초과: 기대 0 / 실제 0` — 그리고 바로 아래 `길이를 본 컬럼: 471`. 두 줄이 함께 있어야 「아무 컬럼도 안 봤다」와 구별된다 |
| **legacy/canonical 충돌 0** | `legacy/canonical 충돌: 0` · `중복 legacy_key: 0` · `중복 canonical_key: 0` · `예약 Key 가 서 있는가: 1` |
| (§7.3) **Notion 임시 File URL 을 새 DB 에 저장하지 않는다** | `Notion 임시 파일 주소: 0` — 그리고 `임시 주소를 본 컬럼: 573`. 표 하나가 아니라 **문자열 컬럼 전수**를 본다 |

### 옮긴 것

| | |
|---|---|
| 표 복사 | **64 표**(이름이 같은 62 + 이름이 바뀐 2). 안 옮긴 10 표와 그 이유가 `## Finding` 의 `table_dropped` 에 있다 |
| 티켓 | **1,133**(Notion 1,125 + 미러에만 남은 8). 번호를 받은 것 **1,120**, 예외 **13** |
| 세 층의 이름 | `legacy_key` 1,125 · `canonical_key` 1,120 · 별칭 `ticket_key_aliases` 1,125 |
| 프로젝트 | 22, Project Key **20건 적용**. Key 없는 둘은 확정표에 없는 프로젝트다 |
| 문서 | **110** + 판 **110**. 본문이 **103건**에 들어갔다(평균 2,585자) — 미러에는 **0건**이었다 |
| 문서 분류 | 유형이 `doc_type` 으로(회의록 24 · 작업 계획서 21 · Knowledge base 15 …), 카테고리가 **태그 11종 · 연결 70건**으로. 미러에서는 **둘 다 비어 있었다** |
| 문서 작성자 | **19건**. 검증된 이메일로 이어진 사람만 붙는다 |
| 티켓 본문 | **613건**이 Notion 에서 왔다 — 미러에는 31건뿐이었다 |
| 관계 | `subtask_of` 76 + `blocks` 45 = **121** |
| 첨부 | 9 중 **6건**을 실 저장소로. 나머지 셋은 분류됐다(아래) |
| 다리 | `legacy_mapping` **1,372행** |

### 분류된 예외 14건 — 「임의로 안 했다」의 목록 (U11)

| 분류 | 수 | 무엇인가 |
|---|---|---|
| `ticket_multiple_parents` | 6 | 상위 작업이 둘 이상이라 첫 번째만 썼다. 몇 개였는지를 함께 적었다 |
| `user_unmapped` | 3 | Notion 사람 셋의 포털 사용자를 못 찾았다. **이름으로 잇지 않는다** |
| `attachment_rejected` | 2 | 제품 업로드 한도(10MB)를 넘는다 — 34MB 회의 녹음과 15MB PDF |
| `attachment_external_link` | 1 | Notion 에 바이트가 없는 바깥 링크(SharePoint)다 |
| `project_source_missing` | 1 | Notion 응답에 없는 프로젝트. 지우지 않고 그대로 뒀다 |
| `property_never_filled` | 1 | 문서의 ` 출처` 속성이 110행 중 한 번도 값을 안 냈다 |

**티켓 예외 13건**은 위 목록과 **다른 것**이고 `migration_exceptions` 표에 있다:
`source_missing` 8 · `missing` 3 · `ambiguous` 2. 셋 다 `project_uid`/`seq`/`canonical_key`
가 전부 NULL 이고, 검증의 「번호 없는 티켓 = 열린 예외: 13 / 13」이 그 짝을 확인한다.

## [`dry_run_pass2.txt`](dry_run_pass2.txt) · [`dry_run_pass2.json`](dry_run_pass2.json) — 재실행

**같은 DB 에 같은 도구를 한 번 더 돌렸다. `신규 = 0`.**

`## 단계` 절의 모든 줄이 `신규 0`이고, `counts` 가 1회차와 **한 글자도 다르지 않다.**
판 수(`document_versions` 110)도 그대로다 — 같은 본문에 판이 또 쌓이지 않는다(D-247).

이것이 R8 이 요구한 「재실행 가능」의 증명이다. 1,200회가 넘는 외부 호출이 중간에
끊겨도 다시 돌리면 되고, Cutover 직전 Delta 도 같은 도구가 진다.

## 두 회차 사이에 무엇이 바뀌었나 — 그리고 왜 원장에 남기나

이 폴더의 두 파일은 **고친 뒤**의 회차다. 그 전에 두 번 돌렸고, 두 번 다 무언가를
드러냈다:

| 회차 | 무엇이 걸렸나 | 무엇이 원인이었나 |
|---|---|---|
| 첫 회차 | 재실행 2회차가 **죽었다** — `ticket has a sequence number but no project` | 표 복사와 재채번이 **같은 컬럼의 주인**이었다. 2회차 복사가 `project_uid` 를 NULL 로 되돌렸는데 `seq` 는 1회차 값이 남아 있었다 |
| 둘째 회차 | 첨부 하나가 **blocking**, 다른 하나는 **classified** | 같은 사실(「너무 크다」)에 한도가 둘이었다. 내려받는 쪽이 25MB, 제품이 10MB |

둘 다 **회차를 돌려 보기 전에는 안 보이는** 종류다. 첫 번째는 오류를 내서 잡혔지만,
같은 결함이 `projects.code` 에도 있었고 그쪽은 **오류를 안 낸다** — 2회차 복사가
1회차에 붙인 Project Key 를 조용히 지웠을 것이다.

고친 자리는 `app/migration/plan.py::DERIVED_COLUMNS` 와
`app/migration/source_notion.py::_MAX_FILE_BYTES` 이고, 각각
`tests/regression/test_migration_reruns_do_not_fight_themselves.py` 와
`tests/regression/test_migration_attachment_size_has_one_owner.py` 가 고정한다.

## 검증하는 코드를 먼저 검증했다

`tests/regression/test_migration_validate_probe.py` 가 **Known Good · Known Bad ·
반례**로 검증기 자신을 시험한다(CLAUDE.md §7 · S12 의 교훈). 실 DB 를 자리마다 하나씩
망가뜨려 **그 항이** 실패하는지 본다 — 누락 · 번호와 이름의 어긋남 · 사유 없는 무번호 ·
낡은 예외 · 깨진 관계 · 판 없는 문서 · 파생 표의 행 · **Notion 임시 주소** · 뒤처진
카운터 · 고아 별칭 · legacy/canonical 충돌 · 사라진 예약 Key.

그리고 **검사를 하나도 안 돌린 보고서는 통과가 아니다**(`MigrationReport.passed` 가
`bool(self.checks)` 를 함께 본다).

## 증거가 나온 코드 = 커밋되는 코드

[`source_fingerprint.json`](source_fingerprint.json) 이 이 회차를 돌린 파일들의 sha256
앞 16자다. 서버에서 실제로 돈 파일의 지문과 같다:

```
2f958c9ec99e14ec app/migration/load.py
dc4d30a052aba890 app/migration/validate.py
966a3dcdbd54ac54 app/migration/transform.py
c331915d986ae888 app/migration/runner.py
```

증거가 나온 코드와 커밋되는 코드가 다르면 그 증거는 **다른 물건의 증거**다
(S12 가 같은 이유로 마지막 회차를 다시 돌렸다).

## 운영 원본을 만지지 않았다

**mtime 이 그대로라는 말은 못 한다** — 그 파일은 지금도 돌고 있는 앱이 계속 쓰고 있다.
말할 수 있는 것은 **우리가 연 방식**이다:

* 스냅숏은 `sqlite3 'file:…?mode=ro' ".backup"` 으로 떴다. 읽기 전용 URI 라 WAL
  체크포인트도 안 일어난다.
* 이관 도구도 같은 방식으로만 연다 — `app/migration/source_sqlite.py` 가
  `path.as_uri() + "?mode=ro"` 로 열고, **이 파일 밖에서 `sqlite3.connect(path)` 를
  부르지 않는다.**
* 쓰기는 전부 목적지 PostgreSQL 에서만 일어난다. Dry Run 은 그 목적지가 임시
  데이터베이스라는 뜻이지, 원본을 만져도 된다는 뜻이 아니다.

## 다시 돌리려면

```bash
# 소스 스냅숏 (운영 원본은 읽기만 한다)
sqlite3 'file:/var/lib/clovirone-web-assistant/web.sqlite3?mode=ro' ".backup '<snapshot>'"

python -m app.cli.migrate_cli plan    --sqlite <snapshot>
python -m app.cli.migrate_cli extract --sqlite <snapshot> --cache <cache> --bodies
python -m app.cli.migrate_cli dry-run --sqlite <snapshot> --cache <cache> --report <out>
```

`DATABASE_URL` 이 임시 DB 를 가리키면 Dry Run 이고 운영을 가리키면 Cutover 다 —
**코드 경로는 같다.** 다르면 Dry Run 이 증명한 것이 Cutover 에서 성립하지 않는다.
