# EVIDENCE — S22 (Final Product Audit · Final Acceptance · Release)

> 이 폴더의 파일이 정본이다. 아래 글은 **그 파일을 어떻게 읽는가**만 적는다.
> 실행일 **2026-08-26** · 호스트 `clovirassist`(10.100.64.71, Ubuntu 24.04.2)
> 판정 근거는 전부 실행 원문이고, 요약이 원문과 어긋나면 원문이 맞다.

---

## 1. 설치 · 업그레이드 — [`lxd_rehearsal.txt`](lxd_rehearsal.txt)

Clean Ubuntu 24.04 컨테이너에서 `deploy/install.sh` 의 전 경로를 한 번씩 돌린 원문이다:
Clean 설치 → verify → 재실행(idempotent) → 실패 주입 → **rollback** → **upgrade** →
컨테이너 재시작 복구 → uninstall → 재설치 → 옛 slug 이전 → purge.

**`LXD_REHEARSAL_OK` · 35항 전부 통과.** Stage 0~18 이 전부 `OK` 이고 수동 mkdir/cp 는 0회다.

이 리허설이 **증명하지 않는 것**은 스크립트 머리말에 그대로 적혀 있다(R15): 진짜 커널
재부팅(§4 가 따로 잰다) · NFS/CIFS 마운트(§3 이 따로 잰다) · 실 장비 성능 · git clone 그 자체.

### 🔴 이 회차가 잡은 것 — [`rollback_before_fix.txt`](rollback_before_fix.txt)

첫 실행은 **네 항목이 실패했다.** 원인은 하나였다(**D-326**).

되돌리기가 유닛을 전부 멈추고(리스 파일이 지워진다) → 스냅샷을 풀고(**리스가 되살아난다**)
→ 4초 뒤 유닛을 띄운다. 새 워커는 그 리스를 읽고 「다른 워커가 이미 돌고 있다
(owner=6631@s22-repro)」 며 종료코드 1 로 물러난다. 그 6631 은 스냅샷을 뜨던 순간의
프로세스이고 이미 없다. `Restart=on-failure` · `RestartSec=10` · `StartLimitBurst=10` 이라
재시도는 **100초 남짓에 끝나고 리스는 120초를 산다** — systemd 가 먼저 포기해서 배치·
스케줄러·색인 세 레인이 **영영 안 돌아왔다**(**D-327**).

그 동안 `/healthz` 와 `/readyz` 는 **200 이었다.** 잡·스케줄·색인이 전부 죽은 채로.

| 파일 | 무엇을 보이나 |
|---|---|
| [`rollback_before_fix.txt`](rollback_before_fix.txt) | 고치기 전. `ROLLBACK_DEGRADED` · 워커 journal 의 «다른 워커가 이미 돌고 있다» · `systemctl status` 의 `activating (auto-restart)` |
| [`rollback_after_fix.txt`](rollback_after_fix.txt) | 고친 뒤. `SNAPSHOT_HAS_NO_LOCKS` · `ROLLBACK_OK` · 네 레인 `active` · `StartLimitBurst=20` |
| [`rollback_from_old_snapshot.txt`](rollback_from_old_snapshot.txt) | **반례** — 리스를 담고 있는 **옛** 스냅샷(`20260825-164254`, locks=3)으로 되돌려도 `ROLLBACK_OK` 다. 스냅샷 쪽만 고쳤으면 이미 떠 있는 백업으로는 여전히 못 돌아온다 |
| [`lxd_rehearsal_before_fix.txt`](lxd_rehearsal_before_fix.txt) | 첫 실행 원문(`LXD_REHEARSAL_FAILED`, 4항 실패) |

---

## 2. Backup / Restore — [`restore_rehearsal.txt`](restore_rehearsal.txt)

**운영 데이터로** 돌렸다. 제품 자신의 백업 기능(`app/backups/service.py::run_backup`)이 뜬
세트를 새 데이터베이스로 되돌리고, **그 복원본을 물고 앱을 띄워 읽기 경로를 실제로 호출**한다.

```
RESTORE_REHEARSAL_OK
tables 93 · rows 8,958 · read_paths_ok 13/13 · attachments_missing 0
alembic_head = restored_alembic_head = code_alembic_head = 0016_document_axis_to_documents
shape: 부분 유니크 15 · trgm GIN 3 · jsonb 30 · identity 4 · FK 108 · check 46
excluded_tables: ai_index_state · document_chunks · rate_limit_buckets · search_documents
```

`read_paths_ok: 13` 은 **로그인을 실제로 지난** 13개 경로다 — 세션을 손으로 만들어 넣으면
인증 경로가 검증에서 빠진다. `attachments_missing: 0` 이 DB 가 가리키는 바이트가 디스크에
있다는 뜻이다(BKP-02). 운영 DB 는 **백업 행 하나가 늘어난 것 말고는** 안 건드렸다.

---

## 3. Storage — [`matrix_nfs.json`](matrix_nfs.json) · [`matrix_smb.json`](matrix_smb.json)

실 NFS(`nfs4`)와 실 SMB(`cifs`) 위에서 **제품 코드로** 16항을 다시 돌렸다.

| | NFS | SMB |
|---|---|---|
| 1~9 · 13~16 | **14 PASS** | **14 PASS** |
| 10 · 11 (재부팅) | **PASS** — §4 가 잰 `POST_REBOOT_PASS` | **PASS** |
| 12 (`RequiresMountsFor=`) | 이 설치의 사실 — 아래 | 같음 |

**12번(`RequiresMountsFor=`)은 이 설치의 사실이지 결함이 아니다.** 이 설치의 운영 저장소는
`LOCAL`(`/var/lib/clovirassist/files`) 하나이고 켜진 NFS/SMB Provider 가 **없다**. 그래서
`install.sh` Stage 11 이 만든 drop-in 은 (옳게) 빈 지시자이고, 앱 유닛은 시험 마운트를 안
기다린다. 매트릭스 12번은 「시험 대상 마운트를 기다리는가」를 묻는데 그 마운트는 제품이
모르는 자리다.

기계는 따로 증명했다:

* [`dropin_units.txt`](dropin_units.txt) — NFS(OPERATIONAL)와 SMB(BACKUP) Provider 를 실제로
  등록하고 제품 CLI(`app.cli.storage_cli units`)를 돌린 원문. 유닛 이름이
  `mnt-clv\x2dnfs.mount` · `mnt-clv\x2dsmb.mount` 로 나오고 — **호스트에서 지금 `active` 인
  유닛 이름과 한 글자도 다르지 않다** — drop-in 은
  `RequiresMountsFor=/mnt/clv-nfs /mnt/clv-smb` 다.
* [`dropin_probe.log`](dropin_probe.log) — 그 drop-in 을 **버리는 유닛**에 얹고 systemd 에게
  직접 물었다. `RequiresMountsFor` 가 두 경로로 잡히고 `After` 가
  `mnt-clv\x2dnfs.mount` · `mnt-clv\x2dsmb.mount` 로 **풀린다.** 확인 뒤 지웠다(`not-found`).

⚠️ **시험 Storage 이지 실 NAS 장비가 아니다**(U9 · D-199). 같은 caveat 문장이 두 JSON 에도
들어 있다.

---

## 4. Reboot 복구 — [`reboot_pre.txt`](reboot_pre.txt) · [`reboot.txt`](reboot.txt)

최종 배포 뒤에 **설치처를 실제로 재부팅**하고 잰 원문이다. 「사람이 아무 명령도 안 쳐도
돌아온다」를 보려면 두 조각이어야 한다 — 재부팅 전 상태를 적고(`reboot_pre.txt`), 재부팅하고,
그 사이에 아무것도 안 한 채 지금과 비교한다(`reboot.txt`).

`boot_id` 가 `8de9720b…` → `929b2eee…` 로 바뀌었다. **진짜 커널 재부팅이다.**

| | |
|---|---|
| 유닛 8종 | 전부 `active / enabled` — **수동 start 0회**. `systemctl --failed` 비어 있다 |
| 마운트 | `mnt-clv\x2dnfs.mount` · `mnt-clv\x2dsmb.mount` 둘 다 `active`, 실제 `nfs4`·`cifs` 로 붙어 있다 |
| health · ready · TLS | `{"status":"ok"}` · `{"status":"ready"}` · `ssl_verify_result=0` · `/login` 200(12,332바이트) |
| 데이터 | 티켓 1,145 · 사용자 26 · 파일 58 — **재부팅 전과 같다** |
| Storage | `operational_ok: true` · `file_count 58` |
| 매트릭스 10·11 | `POST_REBOOT_PASS` (NFS · SMB 둘 다) — 재부팅 전 파일의 체크섬이 그대로다 |
| `install.sh verify` | `VERIFY_OK` |

## 4.1 최종 배포 스모크 — [`deploy_smoke.txt`](deploy_smoke.txt)

배포 커밋 `2f4fc587` · 스냅샷 `/var/backups/clovirassist/20260826-043036` ·
`UPGRADE_OK` · Stage 0~18 전부 OK.

로그에 **D-328 이 실제로 도는 것**이 찍혀 있다 —
`걷어낸 런타임의 죽은 설정 줄을 지웠습니다: N8N_WORK_ASSISTANT_URL / N8N_TIMEOUT_SECONDS`.
배포 뒤 그 파일에 `^N8N` 은 **0줄**이다.

대표 API 다섯(`/api/me` · `/api/tickets/mine` · `/api/admin/users` · `/api/admin/audit` ·
`/api/storage/providers`)이 **404 가 아니라 401** 이다 — 라우터가 실려 있고 인증벽만 막는다.

🔴 **운영에서 브라우저 전수를 다시 안 돌렸다.** 그것은 로컬 PostgreSQL 위에서 만들고 지우는
실행이고, 운영 데이터를 인수 편의로 건드리지 않는다(S21 과 같은 규칙). 대신 **운영이 실제로
내보내는 번들이 캡처가 잰 번들과 같은 바이트인지**를 확인했다:

```
served  /static/react/index.html                    sha256 57956ba3ea73d674…
local   app/static/react/index.html                 sha256 57956ba3ea73d674…   (= build_index_sha256)
served  /static/react/assets/index.DjLYTf33.js      sha256 6d949d74f7937825…
local   app/static/react/assets/index.DjLYTf33.js   sha256 6d949d74f7937825…
```

그래서 §8 의 1,440페이지는 **운영이 지금 내보내는 화면**에 대한 증거다.

---

## 5. Security — [`security_suite.txt`](security_suite.txt)

`tests/security` 전량(81 파일 · 757건) **0 실패**. 인증/세션 · CSRF · Secret 노출 ·
RBAC · Ownership/Visibility · 관리자 API 음성 · 목록/상세/검색/딥링크 일관성 ·
AI Retrieval 권한 · Prompt Injection 경계 · Upload 안전 · SSRF 허용목록이 이 안에 있다.

전량 회귀가 처음 잡은 실패 7건은 **전부 걷어낸 화면(`/api/admin/notion-mapping`)을 겨누던
QA 부채**였다 — S20 이 그 콘솔을 내려 지금 그 주소는 404 다. 없는 문 앞에서 「막혔다」를
세면 문이 다시 열려도 시험은 초록이므로, 그 축을 내리고 사유를 각 파일 머리에
`qa-contract-change:` 로 적었다. 규칙 자체는 살아 있는 시험이 그대로 지킨다(범위 밖 단건
404 는 `test_scope_idor_matrix.py` 가 전수로).

[`permission.json`](permission.json) — 역할 다섯 × 관리자 엔드포인트 18 + 목록·상세 일관성을
**서버에 직접 물어** 다시 잰 것이다.

---

## 6. 데이터 · 채번 · 이관 — [`data_integrity.txt`](data_integrity.txt)

운영 DB 실측(읽기만).

| | |
|---|---|
| 티켓 1,145 · 번호 있는 것 1,130 | **중복 0** · 고유 1,130 · 범위 27~1542 |
| 번호 없는 15건 | 전부 `source=native` — 컷오버 뒤에 만들어져 `canonical_key` 를 갖는다 |
| `canonical_key` 없는 11건 | `migration_exceptions` 미해결 11건과 **같은 수**다(source_missing 6 · missing 3 · ambiguous 2) |
| 프로젝트 22 | 코드 없는 것 0 · 중복 0 · 전부 6자 대문자 · UNIQUE 인덱스 1개 |
| 첨부 | `files` 58 · 티켓 첨부 237 · 문서 첨부 54 · **바이너리 누락 0**(§2) |
| 소유권 | 조직 없는 사용자 0 / 26 |
| 옛 이름 층 | `tickets.legacy_key` · `ticket_key_aliases` · `project_key_registry` **전부 0** |
| 옛 포트 | 5678 · 5679 · 8787 · 8788 · 8789 **청취 0건** |

---

## 7. Runtime / 운영 — [`runtime_db_down.txt`](runtime_db_down.txt)

`/healthz` 와 `/readyz` 가 **다른 것을 말하는지**를 실제로 끊어서 봤다(컨테이너에서).

| 상태 | `/healthz` | `/readyz` | `/login` |
|---|---|---|---|
| 정상 | 200 `{"status":"ok",…}` | 200 `{"status":"ready"}` | 200 |
| **PostgreSQL 정지** | 200 (살아 있다) | **503 `{"status":"unready"}`** | 200 |
| 되살린 뒤 | 200 | 200 | — |

조용히 정상인 척하지 않는다. 되살린 뒤 다섯 유닛이 전부 `active` 로 돌아왔다 —
`wait-for-postgres.sh` 와 재시도가 그 일을 한다.

---

## 8. Final Capture / UI·UX — [`capture_summary.txt`](capture_summary.txt)

라벨 `s22-final` · 번들 지문 `57956ba3ea73d674` · **81 라우트 × 2 테마 × 9 뷰포트 =
1,440 페이지** · 30분 39초.

**승격 검사 열 종 실패 0** — `[OK] 치명 검사 실패 없음`. 첫 회차에서는 넷이 115페이지에서
빨갰고(`brand_role_coverage` 13 · `control_baseline_mismatch` 46 · `equal_column_split` 14 ·
`numeric_alignment` 42), 원인 다섯을 뿌리에서 고친 뒤 **같은 라벨로 전량을 다시 찍어** 그 0 을
만들었다(D-329~D-334).

남은 것은 전부 **승격 안 된 자문 검사**이고 요약표가 그 수를 그대로 적는다:
`brand_presence` 482(절대 정족수 — 모듈 자신이 도달 불가 구간을 적어 뒀다) ·
`dead_blank_region` 200 · `oversized_empty_surface` 146 · `rail_wider_than_prose` 24 ·
`console_errors` 17(일부러 없는 id 로 여는 「못 찾음」 화면) · `surface_repetition` 2.
소유는 **P-54 · P-55** 다.

리포트가 스스로 적는 **미실행** 도 그대로 남긴다: 모달 검사 일곱은 `--modals` 를 켜야 돌고
이번 실행에서 **0회 실행**이다 — 통과가 아니다(**P-56**).

### 8.1 배율 — [`capture_zoom_summary.txt`](capture_zoom_summary.txt)

라벨 `s22-zoom` · 촘촘한 화면 14개 × **125%·150%**(FHD·QHD 환산 CSS 뷰포트 + DPR) × 두 테마
= 112페이지. `horizontal_overflow` · `content_clipped` · `page_errors` · 승격 검사 전부 **0** —
**배율을 올려도 구조가 안 무너진다.**

배율을 「CSS 뷰포트 ÷ 배율 + DPR × 배율」로 환산한 것은 브라우저가 실제로 하는 일과 같다.
새 하네스를 만들지 않았다 — `--viewports 1536x864@1.25x` 처럼 **이미 있는 표기**를 쓴다.

산출물 원본은 `dist/`(gitignore)이고 커밋되는 것은 `docs/ui-renewal/captures/after/` 의
썸네일 1,440장과 `ROUTE_COVERAGE.json` 의 포인터다. 판정 요약은
[`../../../ui-renewal/WORK_STATE.md`](../../../ui-renewal/WORK_STATE.md).
