# MAINTENANCE PLAYBOOK — ClovirONE Web Assistant

향후 유지보수·수정 작업의 **단계별 레시피**. 각 작업은 로컬에서 검증 → 배포 순서다.
먼저 `CLAUDE.md` §2(불변 규칙)·§7(보안 체크리스트)를 확인한다.

공통 전제:
- 로컬 저장소: `C:\Users\hshwa\clovirone-web-assistant` (git).
- 서버: `cloviradmin@10.100.64.71` — SSH **키 인증**(비번 없음), **sudo는 비밀번호 필요**.
- 앱 경로: `/opt/clovirone-web-assistant` (root:root). 정적: `.../app/static/`.
- 검증 3종 세트(무엇을 바꾸든): `pytest` green · `bash scripts/static_checks.sh` = `STATIC_CHECKS_OK` · 프런트를 바꿨으면 React는 `cd frontend && npm test`(vitest), 남은 바닐라 JS(login/change_password/theme.js)는 `node --check`.

---

## §1. 프런트엔드만 수정 → 프로덕션 핫 업데이트

메인 앱(콘솔/채팅/문서/팀공간)은 **React**다 — 소스는 `frontend/`, 배포 산출물은 Vite 빌드
결과인 `app/static/react/`(index.html + assets). React를 고쳤으면 **소스를 고친 뒤 빌드해서
`app/static/react/`를 통째로 교체**해야 반영된다(빌드 없이 `app/static/react/`를 손대지 말 것).
정적 지문 핫배포는 남은 바닐라 JS(`app/static/js/login.js`·`change_password.js`·`theme.js`)와
`app/static/css|img`에만 유효하다.

어느 쪽이든 **서비스 재시작은 불필요**하다. React 셸(`index.html`)은 `admin/router.py`가
`FileResponse`(`Cache-Control: no-store`)로 서빙하고, 나머지 정적은 FastAPI StaticFiles가
디스크에서 매 요청 서빙한다. **사용자에게 Ctrl+Shift+R을 부탁할 필요도 없다** — React assets는
Vite가 파일명에 콘텐츠 해시를 박고, 그 밖의 정적은 `app/core/assets.py`가 파일의 mtime·크기로
지문을 계산해 주소에 붙이므로(`?v=<지문>`), 파일이 바뀌면 주소가 바뀌어 브라우저가 새로 받는다.
한때 그 지문을 프로세스 수명 동안 캐시해서 이 절차가 무효였던 적이 있다. 지금은 매 요청 stat한다.

1. 로컬 수정 후 검증:
   ```bash
   cd frontend && npm test && npm run build && cd ..   # React 변경 시 (build 산출물 → app/static/react/)
   node --check app/static/js/login.js                 # 남은 바닐라 JS를 바꿨으면
   .venv/Scripts/python -m pytest tests/integration/test_admin_console.py -q
   git add -A && git commit -m "feat(ux): ..."
   ```
2. 체크섬 tar로 스테이지한다. **손으로 파일 목록을 적지 말고 스크립트를 쓴다** —
   인자 없이 돌리면 `app/static` 전체(빌드된 `react/` 포함)를 탐색해 하나도 빠뜨리지 않고,
   텍스트만 CRLF를 정규화하고 img/·react/assets의 바이너리는 바이트 그대로 복사한다(한때 여기
   손으로 적힌 목록이 파일을 빠뜨렸고, `sed`를 PNG에 돌려 로고를 깨뜨릴 뻔했다):
   ```bash
   bash scripts/stage-static-update.sh            # 인자 없음 = app/static 전체
   # 일부만 밀려면 경로를 준다: bash scripts/stage-static-update.sh app/static/css/admin.css …
   ```
   스크립트는 `dist/static-update/`에 tar와 SHA256SUMS를 만들고, 아래 3·4단계에 그대로
   붙여넣을 scp·apply·검증 명령을 **출력한다**(경로·해시 포함).
3. 스크립트가 출력한 scp 명령으로 서버 홈에 올린 뒤, **사용자가** sudo 1회로 적용한다
   (대화형 sudo라 스크립트가 대신 실행하지 않는다). 명령은 2단계 출력에 있다.
   (백업까지 하려면 `scripts/`에 apply 래퍼를 두고 실행. 이전 파일은 git 히스토리에 있음.)
4. **검증(sudo 없이 가능)** — 2단계 출력의 `curl … | sha256sum # expect <해시>` 줄로
   서빙되는 파일 해시가 스테이지한 것과 바이트 단위로 같은지 확인한다.
   `⚠️ 하네스 원칙`: "배포했다"가 아니라 **서빙 파일 해시 일치 + 브라우저 렌더 확인**이 완료.

---

## §2. 코드·DB·의존성 수정 → 전체 업그레이드

1. 로컬: TDD로 수정 → `pytest` green → `static_checks.sh` OK → 커밋.
2. 번들 생성(소스 LF 정규화 + wheelhouse 34종 manylinux cp312 + MANIFEST):
   ```bash
   bash scripts/build-bundle.sh          # dist/clovirone-web-assistant-bundle.tar.gz
   ```
3. 서버로 전송·검증·스테이징:
   > ⚠️ 예전 버전은 두 가지가 틀려 있었다(둘 다 실제로 재현해 확인했다).
   > **(a)** `MANIFEST.sha256`(스테이징 안의 파일별 체크섬)을 **압축을 풀기 전에, 그것도
   > 없는 경로(`~/deploy/`)에서** 검증하려 했다 — `build-bundle.sh` 는 그 파일을 `stage/`
   > 안에 만들어 tar에 같이 넣으므로, 압축을 풀기 전에는 애초에 존재하지 않는다.
   > `sha256sum: MANIFEST.sha256: No such file or directory` 로 실패하는데 뒤에 `&&` 로
   > 이어져 있어 있어야 할 스테이징 단계까지 조용히 건너뛰고 **옛 스테이징이 남아 있으면
   > 그걸 그대로 쓰게** 된다 — 무결성 검사가 아무것도 안 걸러 주면서 걸러 준다고 믿게
   > 만드는, 없는 검사보다 나쁜 상태였다.
   > **(b)** `mkdir -p stage && tar -xzf … -C stage` — 번들 tar 안의 경로가 이미
   > `stage/…`(`build-bundle.sh:70` `tar czf … -C "$OUT" stage`)로 시작하는데 그걸 다시
   > `stage/` 라는 디렉터리 **안으로** 풀어서 `~/deploy/stage/stage/app-src/…` 로 **이중
   > 중첩**됐다. §2-4 단계의 `STAGE=~/deploy/stage` 는 그 안에 `app-src` 가 없으므로 즉시
   > `install-clovirone-web-assistant.sh: No such file or directory` 로 죽는다.
   > 아래는 실제로 도는 순서(전송 파일 자체의 체크섬을 먼저 → **`~/deploy` 로** 압축 해제
   > → 압축 안의 파일별 체크섬)로 고친 것이다.
   ```bash
   scp dist/clovirone-web-assistant-bundle.tar.gz dist/bundle.sha256 cloviradmin@10.100.64.71:~/deploy/
   ssh -t cloviradmin@10.100.64.71 'cd ~/deploy && sha256sum -c bundle.sha256 && \
     rm -rf stage && tar -xzf clovirone-web-assistant-bundle.tar.gz && \
     (cd stage && sha256sum -c MANIFEST.sha256)'
   ```
4. **사용자가** 업그레이드 실행(root, 백업→정지→멱등 installer 재실행→검증→실패 시 자동 롤백→기동):
   ```bash
   ssh -t cloviradmin@10.100.64.71 'sudo DNS_NAME=clovirone-ai.gooddi.lab BIND_IP=10.100.64.71 \
     STAGE=~/deploy/stage ~/deploy/stage/app-src/scripts/upgrade-clovirone-web-assistant.sh'
   # 끝에 UPGRADE_OK (실패하면 UPGRADE_ROLLED_BACK <backup-dir> 로 자동 복원됨 - DEPLOY-01/02)
   ```
   `DNS_NAME`/`BIND_IP`는 **이 서버의 값**이다(다른 설치처에 그대로 쓰지 말 것 — installer가
   이 값으로 nginx vhost의 `server_name`/`listen`과 TLS 인증서 SAN을 채운다). 이 서버의 값은
   `grep server_name /etc/nginx/sites-available/clovirone-web-assistant`로 언제든 재확인할 수 있다.
5. 검증: `scripts/validate-clovirone-web-assistant.sh` 또는 §12 헬스체크 → `https://.../readyz` 200.

---

## §3. 관리자 콘솔 섹션 추가/수정

관리자 콘솔은 **React SPA**(소스 `frontend/src`)다. UI 변경은 `frontend/src`를 고친 뒤 빌드해
`app/static/react/`를 교체한다(§1). 대부분의 섹션 구성은 화면 컴포넌트와 그 설정 모듈에 모여 있다.

- **컬럼/필터/액션**: 해당 섹션의 화면 컴포넌트(`frontend/src/screens`)와 설정 정의를 수정.
- **새 섹션**: 라우트/네비 항목 추가 + 화면 컴포넌트 작성 + 백엔드에 대응 API/RBAC.
- **렌더 규칙**: 서버 데이터는 반드시 텍스트로만 표시(React 기본 이스케이프 유지, `dangerouslySetInnerHTML`
  에 서버 데이터 금지). CSP `script-src 'self'` — 인라인 스크립트/`onclick` 금지.
- 검증: `cd frontend && npm test`(vitest) + `npm run build` + `pytest tests/integration/test_admin_console.py`
  → §1로 핫 배포(빌드 산출물 `app/static/react/` 교체).

---

## §4. 설정(Setting) 추가/변경

Settings는 **허용목록 스키마 기반**(임의 키 금지). 각 설정은 키·값·**설명**·**적용 시점**을 가진다.

- 새 설정: settings 레지스트리 스키마에 키·타입·검증·기본값·설명·적용시점(즉시/재시작) 등록 →
  실제 소비자(consumer)에 배선(`SettingsCache`는 시작 시 로드 + 쓰기 시 리로드) → dry-run/auto-rollback
  파이프라인 확인. 상세: 스펙 §14.4-5, `app/settings/`.
- 값 변경만(운영): 관리자 콘솔 Settings에서 `수정`. DB에 반영되고 캐시 리로드됨.
- 검증: 해당 설정을 바꿔 실제 동작(예: `session_policy`는 신규 세션부터, `maintenance_mode`는 일반
  사용자 신규 요청 차단)이 바뀌는지 확인.

---

## §5. DB 마이그레이션 추가 (Alembic)

```bash
# 모델(app/**/models.py) 수정 후:
.venv/Scripts/python -m alembic revision --autogenerate -m "add_<something>"
# 생성된 alembic/versions/*.py 를 반드시 눈으로 검토(autogenerate 불완전할 수 있음)
.venv/Scripts/python -m alembic upgrade head        # 로컬 적용
.venv/Scripts/python -m pytest                        # 마이그레이션 포함 green 확인
```
- 서버 적용은 **§2 전체 업그레이드**를 통해서만(installer가 `cd $APP_DIR` 후 `alembic upgrade head`).
- downgrade 경로도 작성. 데이터 이전이 필요하면 별도 스크립트 + 백업 선행.

---

## §6. API 엔드포인트 추가

- 위치: 해당 `app/<feature>/router.py`(+ service/repository/schemas). 라우터 파일엔
  **`from __future__ import annotations` 금지**.
- **RBAC**: 역할 의존성 부여(user/operator/admin/auditor/system_admin 계층). 상태변경엔
  `require_csrf`. 객체 접근은 **소유권/권한 확인(IDOR 방지)**. lifecycle류는 `ensure_can_manage_target`.
- **입력 검증**(pydantic schema) · 에러는 공통 envelope · secret/PII 응답 노출 금지.
- 외부 호출이 필요하면 `OutboundClient`만 사용(+ allowlist 반영). `import httpx` 직접 금지.
- 테스트: unit(service) + integration(엔드포인트, 역할별) + 필요 시 security(권한/IDOR/secret 노출).

---

## §7. Secret 추가/교체

- DB엔 이름(`secret_ref`)만. 실제 값은 서버 `SECRETS_DIR/<name>` 파일(0600 clovirone-web).
- 추가: 서버에서 (사용자가) 파일 생성 → Integration/Runner의 `secret_ref`에 이름 지정.
  **값은 응답·로그·git·명령행에 절대 안 남게**. `SecretValue`는 repr/str="***".
- 교체: 파일 내용 교체(참조 이름 유지) 또는 새 이름으로 만들고 참조 변경. 노출된 secret은 즉시 rotate.

---

## §8. Integration / Runner allowlist·연결 추가

- 아웃바운드 대상 host는 **allowlist(`config/*.json` → 서버 배포본)**에 있어야 호출됨(미존재=전면 거부).
- Integration/Runner는 콘솔에서 CRUD. 새로 만들면 **비활성**으로 생성 → 헬스체크/연결테스트 후 활성화.
- 헬스 연속 실패가 임계치를 넘으면 자동 degraded/서킷 브레이커. config 변경은 버전 스냅샷(append-only) +
  승인 게이트(운영자가 요청 시 다른 관리자 승인).

---

## §9. 검수 루프(품질 게이트) 실행

큰 변경 후에는 7관점 적대 검수(스펙 §32)를 돌려 Critical/High 0을 확인한다.

- 방법: Claude Code에서 `Workflow` 도구로 병렬 리뷰어(정확성·보안·동시성·경계·회귀·성능·일관성) →
  발견 목록 → **적대 검증**(각 결함을 반증 시도) → 확정 High 전부 수정 + 회귀 테스트 추가 → 재검토.
  Critical/High 0 · 반복 수렴까지. Medium/Low는 `docs/KNOWN_LIMITATIONS.md`에 문서화.
- 과거 이력: iter1~6에서 7→1→1→1→0→0으로 수렴(각 iter 실제 결함 수정). `docs/BUILD_LOG.md` 참조.

---

## §10. 롤백

```bash
# 백업 목록: /var/backups/clovirone-web-assistant/<ts>/
ssh -t cloviradmin@10.100.64.71 'sudo /opt/clovirone-web-assistant/scripts/rollback-clovirone-web-assistant.sh <BACKUP_DIR>'
# 첫 설치 자체를 되돌리려면: 위 명령에 --uninstall
```
- 자사 파일만 복원(공유 서버라 `/etc/nginx` 전체 복원 금지 — 백업 tarball은 수동 재해복구용).
- 정적만 되돌리려면 git에서 이전 파일 꺼내 §1로 재배포.

---

## §11. 백업 / 복원

- 즉시 백업: 콘솔 Backup의 `백업 실행`(sqlite3 backup API + `PRAGMA integrity_check` + 체크섬 자동).
  또는 서버에서 `scripts/backup-clovirone-web-assistant.sh`.
- 복원은 **안전을 위해 서버 스크립트로만**(웹 UI엔 복원 없음). 상세: `docs/BACKUP_RESTORE.md`.

---

## §12. 자주 쓰는 운영 명령 (읽기 전용, sudo 불필요 다수)

```bash
# 서비스 상태 / 로그
ssh cloviradmin@10.100.64.71 'systemctl status clovirone-web-assistant clovirone-web-worker nginx --no-pager | head -40'
ssh cloviradmin@10.100.64.71 'journalctl -u clovirone-web-assistant -n 100 --no-pager'   # sudo 필요할 수 있음
# 헬스 (nginx 경유)
curl -sk https://clovirone-ai.gooddi.lab/healthz     # {"status":"ok"}
curl -sk https://clovirone-ai.gooddi.lab/readyz
# 포트 점유 확인(기존 서비스 무접촉 증명)
ssh cloviradmin@10.100.64.71 'ss -lntp | grep -E ":(80|443|8080|5678|8787|8788|8789)"'
# 로그인 동작 검증(비번은 프롬프트/파일 아님 — 일회성 확인용, 실패는 잠금 유발하니 1회만)
```

> **하네스 원칙(검증·정직)**: 어떤 작업이든 "했다"가 아니라 **사용자가 보는 층에서 결과를 직접 확인**해야
> 완료다. 배포는 서빙 파일 해시 일치 + 화면 렌더, 수정은 pytest green, 버그 수정은 재현 절차로 재확인.
