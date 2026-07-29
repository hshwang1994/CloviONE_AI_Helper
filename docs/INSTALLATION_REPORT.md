# INSTALLATION REPORT — ClovirONE Web Assistant

설치 최종 보고 (spec §36.4). Secret·Password Hash·Session Secret·TLS Private Key·Token은 포함하지 않는다.

## 설치 정보

- 설치 일시: 2026-07-14 16:36 KST
- 서버: `ai-n8n-svr` (10.100.64.71), Ubuntu 24.04 (noble), Python 3.12.3
- 사용자 URL: `https://clovirone-ai.gooddi.lab`
- 내부 바인딩: 웹 `127.0.0.1:8080`, Nginx `10.100.64.71:80/443`
- 전용 시스템 사용자: `clovirone-web` (nologin)

## 인증서

- 유형: **자체 서명(PoC)** ECDSA P-256, CN=`clovirone-ai.gooddi.lab`, SAN=DNS+IP(10.100.64.71)
- 만료: **2027-07-14** (365일)
- 자체 서명이므로 HSTS 비활성 (spec §27.1). 공개 인증서 사본: `/home/cloviradmin/clovirone-ai.gooddi.lab.crt`
- Private Key는 복사하지 않음 (`/etc/clovirone-web-assistant/tls/`, 0600 root:root)

## 최초 관리자 계정

- Email: `hshwang@goodmit.co.kr` / Name: `황형섭` / Role: `system_admin`
- 임시 비밀번호는 설치 시 콘솔에 **한 번만** 표시됨 (로그·이 보고서 미포함)
- **첫 로그인 시 비밀번호 변경 강제**

## 발견된 Integration / Runner / Workflow

- Integration(자동 discovery): n8n, clovirone-work-assistant, claude-ticket-runner, claude-request-interpreter
- Workflow(초기 등록): `ClovirONE AI 업무 도우미`
- 기존 서비스(무접촉·정상): n8n(:5678), claude-ticket-runner(:8787), claude-request-interpreter(:8788), claude-work-assistant(:8789)

## 검증 결과

- ✅ `systemctl status` 3종(web/worker/nginx) active, 기존 n8n·runner 3종 active 유지
- ✅ 포트: web `127.0.0.1:8080`, nginx `:80`(→301 https)·`10.100.64.71:443`(ssl), 기존 8787/8788/8789/5678 loopback 유지
- ✅ `https://.../healthz` `readyz` 200 (nginx 경유)
- ✅ SQLite WAL 모드 활성, 23개 테이블
- ✅ 로그인 흐름(스모크): login 200 → `/api/me`가 세션 기반 이메일·이름 반환(Requester 위조 불가 확인)
- ✅ 백업 + 무결성(`PRAGMA integrity_check=ok`) + 체크섬 전부 OK, temp restore 검증
- ⚠️ **브라우저 실화면 렌더는 미검증**: Claude-in-Chrome 확장 미연결. HTTP/API/자산/CSP는 실서버로
  전수 확인됨. 사용자가 브라우저로 30초 확인 권장(로그인→비밀번호 변경→관리자 콘솔).

## 품질 (검수 루프)

- 7관점 적대 검수 5회 반복: 확정 Critical **0**, High **0** (7→1→1→1→0으로 수렴, 각 High 수정+회귀 테스트)
- 자동 테스트 389개 전부 통과, 정적 검사 클린
- Medium/Low는 `docs/KNOWN_LIMITATIONS.md`에 영향·우회 문서화

## 백업 / 롤백

- 마지막 백업: `/var/backups/clovirone-web-assistant/20260714_164223/`
- 롤백 명령: `sudo /opt/clovirone-web-assistant/scripts/rollback-clovirone-web-assistant.sh <BACKUP_DIR>`
  (첫 설치 되돌리기: `... --uninstall`)

## 산출물

- 설치 Package: `/home/cloviradmin/ClovirONE_Web_Assistant_Final.zip` (source+docs, secret 미포함, SHA256SUMS.txt)
- 공개 인증서: `/home/cloviradmin/clovirone-ai.gooddi.lab.crt`

## 알려진 제한 / 향후 확장

- `docs/KNOWN_LIMITATIONS.md`: SQLite 단일 writer, 단일 worker, 인앱 알림 전용, 자체서명(HSTS 미적용),
  Notion 매핑은 예약 워크플로 필요, 서비스 재시작 API 미제공(안내만), 브라우저 E2E 미검증 등
- Postgres 전환 기준: `docs/EXTENSION_GUIDE.md` §7 (spec §7.4 — 동시 사용자 30↑, worker 2↑ 등)
- nginx: apt 설치 시 기본 사이트(`0.0.0.0:80` 웰컴 페이지)가 함께 활성됨. 우리 vhost는 server_name
  라우팅으로 `clovirone-ai.gooddi.lab`을 처리하며 443은 우리 ssl 블록 전용. 기존 vhost 무접촉 원칙 유지.

## 조치 필요 (사용자)

1. **첫 로그인** 후 임시 비밀번호를 즉시 변경 (강제됨)
2. **SSH 비밀번호 변경** — 배포 과정에서 대화에 노출됐으므로 운영 전 변경 (spec §1)
3. 배포용 임시 NOPASSWD(`/etc/sudoers.d/90-clovirone-deploy-temp`)는 **제거 완료** (비밀번호 sudo로 복귀)
