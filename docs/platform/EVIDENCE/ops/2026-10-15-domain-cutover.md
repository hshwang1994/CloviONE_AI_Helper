# 대표 서비스 주소 전환 — `clovirassist.gooddi.lab` → `clovirassist.goodmit.co.kr` (2026-10-15, D-573)

## 전환 전 실측 (읽기만)

| 항목 | 값 |
|---|---|
| 공개 DNS | `clovirassist.goodmit.co.kr` → A 221.147.80.210(이미 있음). 그 주소의 443 은 회사 에지 nginx 1.27.5 가 Let's Encrypt 인증서(CN = 새 이름)로 받아 랩으로 넘긴다. 에지가 랩에 닿는 내부 주소는 10.100.64.96(HTTP/1.0) |
| 사내 DNS | 같은 이름 → 10.100.64.71(분리 DNS — 사내 사용자는 에지를 거치지 않고 랩 자가 서명 인증서를 본다) |
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

## 되돌리기

- 이번 전환만: 서비스 주소 판 › 주소 바꾸기에서 대표를 `clovirassist.gooddi.lab` 로 다시 적용(같은 도우미 경로, 실패하면 자동 복원).
- 배포 전체: `sudo clovirassist rollback`(스냅샷 `20261015-130128`).

## 남은 바깥 일 (완료로 표시하지 않는다)

- 사내 사용자는 분리 DNS 때문에 랩의 자가 서명 인증서를 본다 — (1) 사내 DNS 를 에지(221.147.80.210 또는 그 내부 주소)로 돌리거나, (2) 에지의
  인증서와 키를 랩에 설치(`cert.install`, 90일 갱신 절차 필요), (3) 사내 CA 중 하나를 에지 · 네트워크 담당이 정한다(권장 1).
- 에지가 `X-Forwarded-For` 를 보내는지 확인한 뒤 `sudo clovirassist upgrade --upstream-proxy 10.100.64.96` 로 바깥 사용자의 속도 제한 ·
  감사 IP 를 사용자별로 만든다(D-499). 지금은 바깥 사용자가 모두 10.100.64.96 으로 보인다.
