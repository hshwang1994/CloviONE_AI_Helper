# 대표 서비스 주소 전환 — `clovirassist.gooddi.lab` → `clovirassist.goodmit.co.kr` (2026-10-15, D-573)

## 전환 전 실측 (읽기만)

| 항목 | 값 |
|---|---|
| 공개 DNS | `clovirassist.goodmit.co.kr` → A 221.147.80.210(이미 있음). 그 주소의 443 은 회사 에지 nginx 1.27.5 가 Let's Encrypt 인증서(CN = 새 이름)로 받아 랩으로 넘긴다. 에지가 랩에 닿는 내부 주소는 10.100.64.96(HTTP/1.0) |
| 사내 DNS | 같은 이름 → 10.100.64.71(분리 DNS — 사내 사용자는 에지를 거치지 않고 랩 자가 서명 인증서를 본다). 사내 DNS 서버는 10.100.64.251(`gooddi-ad01`)이고, 10-16 에 다시 물어도 같았다 |
| 랩 | nginx `server_name clovirassist.gooddi.lab` 하나, 자가 서명 인증서(SAN: 옛 이름 + IP), `APP_BASE_URL=https://clovirassist.gooddi.lab`, 매니페스트는 VERSION 의 CR 때문에 엄격한 JSON 이 아니었다 |

## 순서와 결과

| 시각(KST) | 단계 | 결과 |
|---|---|---|
| 13:01 | `bash scripts/deploy-upgrade.sh`(깨끗한 작업 트리, `e8c1cbbc`) | 스냅샷 `/var/backups/clovirassist/20261015-130128` · Stage 0 ~ 18 OK · `UPGRADE_OK` · 매니페스트 엄격한 JSON |
| 13:07 | `GET /api/admin/system/domain?host=clovirassist.goodmit.co.kr&aliases=clovirassist.gooddi.lab`(미리 확인) | DNS 경고(옛 이름이 서버의 hosts 기본 줄 때문에 127.0.1.1 — 거짓 경고, `4fd16a13` 이 고침) · HTTPS · 웹 서버 · 서비스 설정 「바꾸면 맞음」 · `can_apply` |
| 13:08 | `POST /api/admin/system/domain.apply` `{host, aliases:[옛 이름], cert:{strategy:self_signed}, restart_web:true}` | 입력 확인 · 인증서(새 자체 서명, SAN = 두 이름 + IP, 2027-10-15 까지) · 웹 서버(이름 넣고 reload) · 설정 파일(env · 매니페스트) · 자체 확인(새 인증서로 `/login`) · 뒷단 유닛 재시작 · 3초 뒤 web 재시작 — 모두 통과. 감사 `system_action/domain.apply`(적용한 계정: 사용자 본인) |
| 13:09 | 확인 | 새 이름(사내 경로) 200 · 옛 이름(별칭) 200 · 공개 에지 200(LE 인증서 검증 통과) · `/login` 의 로그인 폼 · `sudo clovirassist verify` `VERIFY_OK` · 유닛 여섯 active · `scripts/verify_deploy.sh` 두 이름 `DEPLOY_VERIFY_OK`(자산 60/60) |
| 13:12 | 시험 메일 | 본문 링크가 새 대표 주소다(`2026-10-15-lab-relay-e2e-3.md`) |

- 서버 값: `APP_BASE_URL=https://clovirassist.goodmit.co.kr`, `TLS_CERT_PATH=/etc/clovirassist/tls/clovirassist.goodmit.co.kr.crt`,
  매니페스트 `dns_name=clovirassist.goodmit.co.kr` · `alias_names=clovirassist.gooddi.lab`, nginx `server_name clovirassist.goodmit.co.kr clovirassist.gooddi.lab;`.
- 옛 이름은 **리디렉션 없는 별칭**으로 남겼다(배포 스크립트 · QA 하네스 · 즐겨찾기 · 이미 보낸 메일의 링크가 계속 열린다). 세션 쿠키는 이름마다라
  새 이름으로 처음 열면 다시 로그인한다.
- 로컬 운영 값(`dist/ops/server.env` 의 `BASE_URL` · `DNS_NAME`)과 QA 기본 주소(`scripts/ui_qa/capture.py`)를 새 이름으로 바꿨고, 새 인증서를
  `dist/ops/clovirassist.goodmit.co.kr.crt` 로 받았다.

## 앞단 프록시 신뢰 (15:07 KST, P-143)

- `sudo clovirassist upgrade --upstream-proxy 10.100.64.96` — Stage 0 ~ 18 OK · `VERIFY_OK`, 스냅샷 `20261015-150715`. Stage 16 이
  `/etc/clovirassist/nginx/realip.conf` 에 `set_real_ip_from 10.100.64.96` · `real_ip_header X-Forwarded-For` · `real_ip_recursive on` 을
  썼고, 매니페스트 `upstream_proxies` 에 남아 다음 upgrade 도 유지한다.
- 표시를 단 `/healthz` 요청을 보내고 랩 nginx 접근 로그에서 그 요청만 골라 기록된 주소를 봤다.

| 들어온 길 | 보낸 X-Forwarded-For | 랩이 기록한 주소 |
|---|---|---|
| 공개 주소 221.147.80.210(에지) | 198.51.100.7(위조) | 221.147.80.129 — 에지가 본 실제 주소 |
| 공개 주소 221.147.80.210(에지) | 없음 | 221.147.80.129 |
| 에지 안쪽 주소 10.100.64.96 | 없음 | 10.11.20.19 — 이 PC(인증서 검증 통과, 200) |
| 랩 직접 10.100.64.71 | 198.51.100.7(위조) | 10.11.20.19 — 이 PC |

- 에지는 실제 주소를 덧붙이고, 위조한 값은 어느 길에서도 무시된다. 앱의 로그인 감사 IP 도 같다(에지 경유 221.147.80.129, 직접 10.11.20.19).
- 221.147.80.129 는 회사의 바깥 출구 주소다. 사내 PC 가 공개 주소로 에지를 거치면 모두 이 주소 하나로 보인다.

## 되돌리기

- 이번 전환만: 서비스 주소 판 › 주소 바꾸기에서 대표를 `clovirassist.gooddi.lab` 로 다시 적용(같은 도우미 경로, 실패하면 자동 복원).
- 배포 전체: `sudo clovirassist rollback`(스냅샷 `20261015-130128`).

## 사내 DNS 전환 — 끝남 (2026-10-16, 사용자가 바꿨다)

전환 뒤 사내 사용자는 분리 DNS 때문에 랩의 자가 서명 인증서를 봤다. 세 길(사내 DNS 를 에지로 · 에지의 인증서와 키를 랩에 설치 · 사내 CA) 가운데
사내 DNS 를 에지의 **안쪽 주소**로 돌리는 길로 끝냈다. 공개 주소로 돌리지 않은 까닭은 사내 PC 가 회사 출구 주소 하나(221.147.80.129)로 보여 로그인
속도 제한(분당 30)을 회사 전체가 나누기 때문이다.

| 항목 | 값 |
|---|---|
| 바꾼 곳 | 사내 DNS 서버 10.100.64.251(`gooddi-ad01`) › 영역 `goodmit.co.kr`(그 영역의 이름 서버는 이 하나다) › `clovirassist` A 레코드, TTL 3600 |
| 바꾼 값 | 10.100.64.71(랩 직접) → **10.100.64.96**(에지 안쪽 — 공개 주소 221.147.80.210 과 같은 인증서). 별칭 `clovirassist.gooddi.lab` 은 그대로 10.100.64.71 이다 |
| 바꾸기 전에 본 것 | 에지를 거친 본문 3MB · 9MB · 11.5MB 가 앱까지 닿는다(앱의 파일 한도 10MB · 업로드 봉투 12MB). 앱은 WebSocket · SSE 를 쓰지 않는다(폴링). 배포 검증(`install.sh` 의 `--resolve`)과 주소 바꾸기의 자체 확인(`_self_check(bind_ip, …)`)은 랩 주소를 못박아 DNS 와 무관하다 |
| 바꾼 뒤 — 이 PC(Wi-Fi, 사내 DNS) | 이름으로 접속하면 10.100.64.96 이고 `/healthz` · `/readyz` · `/login` 이 200, Windows 인증서 검증을 지난다. 실브라우저(Chromium, 인증서 오류를 무시하지 않음)에서 첫 화면 200 · 인증서 Let's Encrypt `YE1` · 사용자 계정 로그인 200 · AI 도우미 화면이 열리고, 랩이 그 세션의 주소를 10.11.20.19(이 PC 의 실제 주소)로 기록했다. 시험 세션은 로그아웃했다 |
| 바꾼 뒤 — 랩 서버 | 같은 사내 DNS 를 쓴다. 캐시 없이 물으면 10.100.64.96 이고, 캐시가 남은 동안(최대 1시간)은 옛 답이다. 새 답을 보면 관리자 「서비스 주소」의 DNS 점검이 「다른 주소(10.100.64.96)로 풉니다. 앞단 프록시를 거쳐 들어오는 구성이면 정상입니다」라는 주의를 띄운다 — 이 구성에서는 정상이다 |
| 되돌리기 | 같은 레코드를 10.100.64.71 로 돌린다 |

- 이제 사내 접속도 에지를 거친다. 에지가 멈추면 사내에서도 새 이름으로 열리지 않는다 — 그때는 별칭 `clovirassist.gooddi.lab`(랩 직접, 자가 서명
  인증서)으로 열 수 있다.
