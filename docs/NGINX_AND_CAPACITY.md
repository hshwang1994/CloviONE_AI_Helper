# nginx 튜닝과 동시 사용자 한계

`deploy/nginx/clovirone-web-assistant.conf` 에 넣은 값의 근거와, 이 서버가 실제로 몇 명을
동시에 받을 수 있는지 아는 것/모르는 것을 나눠 적는다.

> **잰 것과 안 잰 것**
>
> - **쟀다**: gzip 절감량(저장소의 실제 번들 파일을 압축), 프런트 폴링 주기(소스에서 셈),
>   스레드풀 한계 40, DB 커넥션 한계 15, 커넥션 대기 30초, SQLite busy_timeout 5초.
> - **안 쟀다**: 요청 하나가 걸리는 시간, 그리고 그로부터 나오는 **동시 사용자 수**.
>   부하 시험을 돌린 적이 없다. 4절에 산수와 재는 방법만 적어 둔다. 숫자를 지어내지 않는다.

---

## 1. gzip

초기 진입 JS 가 무압축으로 나가고 있었다. 실제 번들 파일을 gzip level 5 로 압축해 쟀다.

| | 원본 | gzip -5 | 절감 |
|---|---|---|---|
| `mui.BsuNCYyi.js` | 344,369 B | 101,888 B | 70.4% |
| `vendor.CQ3mkMrG.js` | 147,927 B | 51,178 B | 65.4% |
| `react.DC90WV7q.js` | 143,363 B | 46,369 B | 67.7% |
| `index.DExmfBY1.js` | 80,831 B | 28,424 B | 64.8% |
| `query.KXpqYlkq.js` | 41,347 B | 12,450 B | 69.9% |
| **JS 5개 합계** | **757,837 B (740 KiB)** | **240,309 B (235 KiB)** | **68.3%** |
| `style.BBogVpEo.css` | 54,873 B | 10,735 B | 80.4% |
| **첫 화면 합계** | **812,710 B (794 KiB)** | **251,044 B (245 KiB)** | **69.1%** |

사내 1Gbps LAN 에서는 시간 차이가 크지 않지만, VPN 과 원격지에서는 그대로 체감된다.

### 빠뜨리면 안 되는 것

**`gzip_proxied any;`** 가 없으면 아무것도 압축되지 않는다. 이 vhost 의 본문은 전부
`proxy_pass` 로 오는데 nginx 의 `gzip_proxied` 기본값이 `off` 이기 때문이다. `gzip on;` 만
켜 두면 오류도 경고도 없이 그냥 안 듣는다. 확인하는 법:

```bash
curl -ksI -H 'Accept-Encoding: gzip' https://<호스트>/static/react/assets/mui.*.js | grep -i content-encoding
# Content-Encoding: gzip  이 나와야 한다
```

`text/html` 은 `gzip_types` 에 적으면 안 된다. nginx 가 항상 포함하므로 적으면 경고가 뜬다.

### BREACH 는 왜 걱정하지 않는가

압축 + TLS 조합의 알려진 공격이다. 성립하려면 **공격자가 넣은 문자열과 비밀이 같은 응답
본문에** 함께 담겨야 한다. 여기 비밀은 두 가지다.

- 세션 쿠키: HTTP 헤더라 gzip 대상이 아니다. `httponly` 이기도 하다.
- CSRF 토큰: 인증된 응답에 담긴다. 그런데 세션 쿠키가 `SameSite=Strict` 라 다른 사이트에서
  띄운 요청에는 아예 붙지 않는다. 즉 공격자가 인증된 응답 자체를 만들어 낼 수 없다.

---

## 2. 요청 속도 제한 (limit_req)

⚠️ **잘못 걸면 정상 사용자가 429 를 받는다.** 그래서 값을 추측으로 정하지 않고 이 앱이
실제로 보내는 폴링 주기에서 계산했다.

### 이 앱이 보내는 요청 (frontend/src 의 refetchInterval 에서 셈)

로그인 후 **어느 화면에나 늘 도는** 폴링:

| 무엇 | 주기 | 분당 | 어디 |
|---|---|---|---|
| 팀 채팅방 목록 | 30초 | 2.0 | `app/AppShell.jsx` |
| 알림 안 읽음 수 | 60초 | 1.0 | `app/NotificationBell.jsx` (사이드바 배지와 키를 공유해 하나로 합쳐진다) |
| 대리 로그인 상태 | 60초 | 1.0 | `app/Banners.jsx` |
| 시스템 상태 | 120초 | 0.5 | `app/Banners.jsx` (서버가 `poll_seconds` 로 주기를 바꿀 수 있다) |
| 공지 | 300초 | 0.2 | `app/Banners.jsx` |
| | | **4.7회/분** = 0.078회/초 | |

가장 무거운 화면인 **게임 방**은 여기에 1.2초 폴링(50회/분)이 더 붙는다.

> **한 사용자의 최악 지속 속도 = 54.7회/분 = 0.91회/초**

### 정한 값

```nginx
limit_req_zone $binary_remote_addr zone=clv_api:10m   rate=20r/s;
limit_req_zone $binary_remote_addr zone=clv_login:10m rate=30r/m;
limit_req_status 429;
```

| 어디 | 걸린 것 | 왜 |
|---|---|---|
| `location /` | `clv_api burst=40 nodelay` | 20r/s 는 위 최악값(0.91r/s)의 **22배**다. 탭을 여러 개 열어도, 화면을 빠르게 오가도 안 걸린다. burst=40 은 화면 이동 한 번에 API 를 여덟 개 안팎 동시에 부르는 것을 흡수한다. `nodelay` 라 버스트는 지연 없이 통과하고 지속 속도만 묶인다 |
| `= /login`, `= /change-password` | `clv_login burst=10 nodelay` | 실패 한 번마다 Argon2id 해시가 돌아 CPU 와 스레드 슬롯을 먹는다 |
| `/static/` | **없음 (일부러)** | 첫 화면 한 번에 자산 열 개 남짓이 동시에 나간다. 제한하면 새로고침 한 번에 몇 개가 429 로 떨어지고, 화면은 깨져 보이는데 서버 로그에는 오류가 없다. 정적 자산은 앱 로직을 태우지도 않으니 제한해서 얻는 것도 없다 |
| 첨부 업로드 경로 4개 | **없음 (일부러)** | 별도 `location` 이라 `/` 의 제한을 물려받지 않는다. 10MB 업로드가 속도 제한에 걸려 중간에 끊기면 원인을 찾기 어렵다 |

### 로그인 제한을 왜 앱보다 느슨하게 잡았나

앱에도 리미터가 있다(`app/main.py` `login_ratelimiter`, **분당 10회**). nginx 를 그보다
빡빡하게 잡으면 사용자가 앱의 한국어 안내 대신 nginx 의 맨 429 를 받게 되고, 무엇이
잘못됐는지 화면에서 알 수 없다. **앱이 먼저 말하고, nginx 가 그 뒤를 받친다.**
`tests/unit/test_update_script_contract.py::test_nginx_login_limit_is_looser_than_the_app_limit`
가 이 관계를 고정한다.

### 이것은 DDoS 방어가 아니다

한 클라이언트의 폭주가 워커 1개짜리 앱을 통째로 막는 것을 늦추는 장치다. 진짜 분산 공격에는
아무 도움이 안 된다. 사내 LAN 이라 그 정도가 적당하다고 판단했다.

### 정상 사용자가 429 를 받았는지 확인하는 법

```bash
sudo grep 'limiting requests' /var/log/nginx/clovirone-web-assistant.error.log | tail -20
```

`zone "clv_api"` 가 자주 뜨면 값이 너무 빡빡한 것이다. 다음을 확인하고 올려라.

1. 여러 사람이 **한 IP 뒤에** 있는가? (프록시, NAT, 점프 호스트). `$binary_remote_addr`
   기준이라 그런 배치에서는 사람 수만큼 곱해서 봐야 한다. 100명이 한 IP 를 쓰면
   0.91 x 100 = 91r/s 로 20r/s 를 넘는다. **이 경우 반드시 올려야 한다.**
2. 새 화면이 짧은 주기 폴링을 추가했는가?

바꾸는 곳은 `deploy/nginx/clovirone-web-assistant.conf` 의 `limit_req_zone` 한 줄이다.
고친 뒤 `sudo nginx -t && sudo systemctl reload nginx`.
급하면 `limit_req` 줄만 주석 처리하면 제한이 사라진다.

---

## 3. 로그와 회전

vhost 가 전용 로그를 쓴다. 기본값(`/var/log/nginx/access.log`)에 두면 같은 서버의 n8n
요청과 한 파일에 섞여서, 장애를 볼 때 우리 요청만 골라낼 수 없다.

```
/var/log/nginx/clovirone-web-assistant.access.log
/var/log/nginx/clovirone-web-assistant.error.log
```

회전은 **배포판 nginx 의 logrotate 설정**(`/etc/logrotate.d/nginx`)이 `/var/log/nginx/*.log`
로 이미 가져간다. 그래서 설치 스크립트는 그 설정이 있으면 우리 것을 **넣지 않는다.**
같은 파일을 두 설정이 회전시키면 logrotate 가 `duplicate log entry` 를 내고 **그 실행 전체가
실패한다** (nginx 로그뿐 아니라 같이 묶인 다른 로그까지 안 돈다).

배포판 설정이 없는 시스템에서는 `deploy/nginx/logrotate-clovirone-web-assistant` 를
`/etc/logrotate.d/clovirone-web-assistant` 로 넣는다(일 단위, 14개 보관, 압축).

확인:

```bash
sudo logrotate -d /etc/logrotate.d/nginx 2>&1 | grep clovirone
```

---

## 4. 동시 사용자 한계

### 4.1 구조적 한계 (전부 측정값)

요청 하나가 지나가는 길에 있는 상한들이다. 낮은 것이 먼저 걸린다.

| 순서 | 무엇 | 값 | 어디서 나왔나 |
|---|---|---|---|
| 1 | uvicorn 워커 프로세스 | **1** (고정) | `deploy/systemd/clovirone-web-assistant.service` |
| 2 | 동시 실행 가능한 요청 핸들러 | **40** | anyio 4.14.2 기본 스레드 리미터. 실행해서 확인(`current_default_thread_limiter().total_tokens` = 40) |
| 3 | 동시 DB 커넥션 | **15** (pool 5 + overflow 10) | `app/core/db.py` 의 SQLAlchemy 기본값. `make_engine()` 을 실제로 만들어 확인 |
| 4 | 16번째 요청의 커넥션 대기 | **30초** 뒤 오류 | 같은 곳(QueuePool timeout) |
| 5 | SQLite 쓰기 | 한 번에 **하나**, 대기 **5초** | `app/core/db.py` `DEFAULT_BUSY_TIMEOUT_MS = 5000` |

**실질 병목은 3번, 즉 15다.** 이 앱의 요청은 거의 전부 DB 를 건드리므로, 동시에
"진행 중"일 수 있는 요청은 사실상 15개다. 40개 스레드가 있어도 25개는 커넥션을 기다린다.

`--workers 1` 이 왜 고정인지는 유닛 파일 주석에 있다. 요약하면 로그인 무차별 대입 제한,
채팅 전송 제한, AI 퀴즈 제한이 전부 **프로세스 안 메모리**에 카운터를 들고 있어서, 워커를
N개로 올리면 그 제한들이 조용히 N배 약해진다. 올리려면 공유 rate-limit 저장소를 **먼저**
만들어야 한다.

### 4.2 동시 사용자 수: 재지 않았다

부하 시험을 돌린 적이 없다. 요청 하나가 걸리는 시간(T)을 모르면 사용자 수는 나오지 않는다.

산수만 적어 둔다. **이 표는 측정이 아니라 산수다.** T 를 재서 대입해야 뜻이 생긴다.

```
처리량        = 15 (동시 커넥션) / T (요청당 초)
가만히 있는 사용자 1명 = 0.078 요청/초   (2절에서 센 값)
받을 수 있는 사용자 수 = 처리량 / 0.078 = 192 / T
```

| 요청당 걸리는 시간 T | 산술적 상한 (화면을 열어 두고 가만히 있는 사용자) |
|---|---|
| 10 ms | 19,200명 |
| 50 ms | 3,840명 |
| 200 ms | 960명 |
| 1 s | 192명 |

주의할 점:

- 게임 방에 있는 사람은 0.91 요청/초로 **12배**를 쓴다. 게임 방에 60명이 동시에 있으면
  그것만으로 55 요청/초다.
- 이 산수는 **평균**이다. 실제로는 몰리는 순간에 15개 커넥션이 차고 나머지가 대기한다.
  30초를 넘겨 기다리면 오류가 난다.
- 목표 규모는 `docs/PRODUCTIZATION_ARCHITECTURE.md` 기준 약 1000명이다. 위 표에서
  T 가 200ms 를 넘으면 그 목표에 못 미친다. **T 를 재기 전에는 "된다/안 된다"를 말할 수 없다.**

### 4.3 재는 법

운영 서버에서 30초면 된다. 부하를 주지 않는 방법부터.

```bash
# 1) 요청 하나가 실제로 얼마나 걸리는지 (T)
sudo tail -n 2000 /var/log/nginx/clovirone-web-assistant.access.log | \
  awk '{print $NF}' | sort -n | awk '{a[NR]=$1} END {print "p50=" a[int(NR*0.5)], "p95=" a[int(NR*0.95)]}'
```

> 위 명령이 쓸모 있으려면 `log_format` 에 `$request_time` 이 있어야 한다. 지금 쓰는
> `combined` 에는 **없다.** 재기로 했다면 `log_format` 을 하나 더 정의해서 붙여야 한다.
> 지금 안 붙인 이유: 로그 형식을 바꾸면 기존 로그 파서와 어긋나고, 아직 파서가 있는지
> 확인하지 못했다.

부하를 주는 방법(운영 시간 밖에서):

```bash
# 동시 15, 총 300 요청. hey 또는 ab 로 잰다.
hey -n 300 -c 15 -H "Cookie: <세션쿠키>" https://<호스트>/api/home/today
```

그 결과의 평균 응답 시간을 T 에 넣으면 위 표의 한 줄이 실제 숫자가 된다.

---

## 관련 문서

- **[INSTALL_FROM_GIT.md](INSTALL_FROM_GIT.md)** - 설치와 업데이트
- **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)** - 다른 설계상 제약
- **[PRODUCTIZATION_ARCHITECTURE.md](PRODUCTIZATION_ARCHITECTURE.md)** - 1000명 규모로 가는 계획
- **[RUNBOOK.md](RUNBOOK.md)** - 느려졌을 때 대응
