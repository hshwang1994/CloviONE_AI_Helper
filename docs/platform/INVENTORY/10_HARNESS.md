# INVENTORY 10 — Harness (설치 · 배포 · 검증 Script)

**정본**: `scripts/**` · `deploy/**`
**측정**: 2026-08-20 (Plan Mode)
**소유**: **S4** (설치) · **S1** (프로브) · **S2** (테스트 하네스)

설치 사양 전문은 [`../INSTALLATION.md`](../INSTALLATION.md).

## 있는 것

| 자산 | 상태 |
|---|---|
| `scripts/install-clovirone-web-assistant.sh` (22.6 KB, **12 stage**) | 존재하나 **SQLite·Notion·n8n 결합**. PostgreSQL·AI·Storage 개념 없음 |
| `scripts/upgrade-*.sh` · `rollback-*.sh`(`--uninstall` 포함) · `update-from-git.sh` · `build-bundle.sh` | 존재. **Rollback 모델이 "백업한 DB 파일 되돌리기"** — 단일 파일 전제라 **PG 에서 성립하지 않는다** |
| `deploy/00-precheck.sh` · `deploy/nginx/*.conf`(`__DNS_NAME__` 템플릿) · systemd unit 4종 | **재사용 가능한 뼈대** |
| `scripts/validate-clovirone-web-assistant.sh` | **n8n 활성 단언**(`:23`) → n8n 제거 시 실패 (S11) |
| `scripts/verify_deploy.sh` · `scripts/final_verify.sh` · `scripts/static_checks.sh` | 검증 진입점 |
| `scripts/run_full_regression.sh` | backend 4청크 (unit·regression·security·integration) |
| **`scripts/restore_rehearsal.py`** | **저장소에서 가장 정직한 검증 자산.** 8단계 중 7단계가 **복원된 DB 로 앱을 실제 기동해 읽기 경로를 호출**한다 → PG 기준으로 이식 (S12) |
| `scripts/check_ui_renewal_coverage.py` (66.8 KB) | UI Coverage Gate. **P-01 의 1순위 수정 대상** |
| `scripts/ui_qa/**` · `scripts/apply-static-update.sh` | 브라우저 QA · 무인 배포 |
| `scripts/check_git_secrets.py` · `check_bundle_fresh.py` · `check_bundle_size.sh` · `check_test_strength.py` | 위생 게이트 |

## 없는 것

| 없는 것 |
|---|
| GitLab 기준 Source 경로 |
| PostgreSQL 설치/초기화 · Extension 생성 |
| Storage 준비 (마운트 유닛 · `st_dev` 검증) |
| AI Component 배치 (모델 파일 · ONNX Runtime) |
| Scheduler 를 별도 유닛으로 인식하는 자리 |
| **전 제품 Reboot 검증** |
| **Clean OS 재현 설치 검증** |

## 알려진 실패 모드 둘

**하나 — 현행 installer 가 "새 코드 + 옛 스키마" 를 남긴다.**
Stage 4 `rsync --delete` 와 Stage 5 venv 재생성 **뒤에** 테넌트 값 가드가 `exit 21` 을 한다
(`install:221-235`). 새 설계는 **검증을 전부 Preflight 로 끌어올려** 이 상태를 만들지 않는다.

**둘 — `final_verify.sh:38-39` 는 절대 실패할 수 없다.**
`check_bundle_fresh --write` 직후 같은 검사를 돌린다. `--write` 를 빌드 직후로 옮기고 검사는
plain 으로 돌린다 (`12_PROBE.md` 우선순위 6).

## nginx 하드 블로커

`client_max_body_size` 기본 **256k**. 대화 메시지(8m)·게시판 첨부(12m) location 만 올려 놨다.
**파일 업로드 제품화의 하드 블로커다** — S8 에서 Storage 와 함께 푼다.

## Installer 계약 (D-205)

**Runtime Component 를 추가하는 Session 은 그 Session 안에서** ① installer Stage ② systemd unit +
enable + 의존 순서 ③ health probe ④ uninstall 경로 ⑤ reboot 후 복구 를 **함께** 완성한다.
**"나중에 설치 붙이기" 를 허용하지 않는다** (R14).

## 완성도 — S1 이 마저 할 것

- `scripts/**` 를 실제로 열거해 **폐기 / 이식 / 유지** 셋으로 분류한다. 지금 위 표는 대표 자산만 담고
  있다
- `12_PROBE.md` 의 8건 수정이 여기 포함된다 (P-01)
