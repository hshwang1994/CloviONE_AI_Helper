# 사전조사 결과 (D1, 2026-07-14) — 배포 스크립트 입력

서버: `ai-n8n-svr` (cloviradmin@10.100.64.71). 판정: **진행 가능 (STOP 0, WARN 0)**.

## 확정 사실
- OS: Ubuntu 24.04 (noble), kernel 6.8.0-134, x86_64, 4 CPU, MemAvailable ~6.8GB
- Python: **3.12.3** (wheelhouse cp312 타깃 일치)
- DNS: `clovirone-ai.gooddi.lab` → 10.100.64.71 (서버 측 확인)
- 인터넷: PyPI 도달 O, apt O (python3.12-venv/nginx/openssl/sqlite3/zip 설치 시뮬 성공)
- **nginx: 미설치** → 10-system-prep에서 apt 설치. 80/443 기존 vhost 없음
- **포트 80/443/8080 전부 비어있음** → nginx vhost는 spec §27.2 그대로(IP-literal listen) 사용 가능,
  기존 wildcard vhost 가로채기 위험 없음. `70-nginx.sh`의 listen 결정 규칙 = 리터럴 경로
- clovirone-web 사용자/디렉터리 없음 → 신규 클린 설치
- 기존 서비스(무접촉): n8n(:5678, user=n8n, /usr/local/bin/n8n, env /etc/n8n/n8n.env),
  claude-work-assistant / claude-ticket-runner / claude-request-interpreter
  (:8787/8788/8789 추정, 전부 user=n8n, python3, env /etc/claude-ticket-runner/runner.env) — 전부 active
  ⚠️ discovery 시드 기본 URL(8789=work-assistant, 8787=ticket-runner, 8788=request-interpreter)은
  포트 리스닝만 확인됨. 실제 어느 포트가 어느 서비스인지는 설치 후 health check로 재확인.

## 배포 시 반영
- 방화벽 무변경(spec §30). ufw/nft 요약은 보고서 참조
- SESSION_SECRET는 서버에서 openssl로 생성(30-configure-env)
- 온라인이지만 wheelhouse는 항상 번들(결정론) — `pip install --no-index --find-links` 우선, 실패 시 온라인 fallback
