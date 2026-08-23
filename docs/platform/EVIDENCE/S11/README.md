# EVIDENCE / S11 — n8n · 외부 Runner 제거

> INVENTORY 09 가 적은 순서는 하나였다: **워크플로 Export 보관 → 로직 이관 → 자체 경로
> 검증 → n8n 정지 → 제거.** 「끄고 나서 옮기지 않는다」가 그 순서의 이유다.
> 이 디렉터리가 그 순서를 지켰다는 원장이다.

## 이 디렉터리에 있는 것

| 파일 | 무엇 |
|---|---|
| [`n8n-workflows-s11.tar.gz`](n8n-workflows-s11.tar.gz) | 워크플로 **22개 전량**의 정의(134 KB). 지우기 **전에** 뽑았다 |
| [`INDEX.json`](INDEX.json) | 그 22개의 목록(압축을 안 풀고 읽는다) |
| [`service_removal.txt`](service_removal.txt) | 서버에서 그대로 받아 적은 제거 후 상태. 손으로 안 고쳤다 |

## 1. 무엇을 보관했나

n8n 2.29.9 의 `export:workflow --all --separate --pretty` 로 22개를 전부 뽑았다.
활성은 둘이었다.

| | 워크플로 | 노드 |
|---|---|---|
| **활성** | `ClovirONE AI 업무 도우미` | 34 |
| **활성** | `notion-user-mapping` | 8 |
| 비활성 20 | 티켓 생성/조회 API 계열 · 요구사항 검토 v4 계열 · Teams 이벤트 진단 · 옛 도우미 판들 | 2~35 |

`INDEX.json` 이 id·이름·활성 여부·노드 수·노드 타입·수정 시각을 들고 있다 — 압축 안에도 있고
이 디렉터리에도 풀어 두었다.

### 두 가지를 일부러 뺐다

`staticData`(4.0 MB) 와 `pinData`. 둘 다 **로직이 아니라 실행 상태**다 — 러너 dedupe 캐시와
고정해 둔 시험 입력이고, Notion page id 가 섞여 있다. 빼고 나니 8.6 MB → 134 KB 다.
남긴 것은 노드와 연결, 즉 **이 자동화가 실제로 하던 일**이다.

### 비밀은 안 들어갔다 — 구조로 확인했다

n8n 의 워크플로 export 는 credential 을 **참조로만** 싣는다. 그 성질을 믿지 않고 직접 셌다:
22개 파일의 credential 참조 **97건**이 전부 `('id', 'name')` 두 키뿐이다. 값을 가진 항목은
0건이다. 실제 credential 둘(`Header Auth account` · `Notion account`)은 n8n DB 안에 암호화된
채로 남았고, 그 DB 스냅숏은 서버 백업에만 있다.

## 2. 서버에서 무엇이 사라졌나

`10.100.64.71` — 넷 다 `n8n` 계정으로 돌고 있었다.

| 서비스 | 포트 | 제거 전 | 제거 후 |
|---|---|---|---|
| `n8n.service` | 5678 · 5679 | active | **unit 자체가 없다** |
| `claude-work-assistant.service` | 8789 | active | **unit 자체가 없다** |
| `claude-ticket-runner.service` | 8788 | active | **unit 자체가 없다** |
| `claude-request-interpreter.service` | 8787 | active | **unit 자체가 없다** |

`systemctl list-unit-files` 와 `list-units --all` 이 둘 다 **0건**이다. 이것이 중요한 이유는
하나다 — **정지만 시키면 재부팅에 돌아온다.** 유닛 파일이 없어야 안 돌아온다.

함께 걷어낸 것: `/opt/{n8n,claude-*}` 실행 코드 · `/etc/{n8n,claude-*}` 설정 ·
`/usr/local/bin/n8n` · `/var/lib/n8n` 데이터(738 MB).

## 3. 되돌릴 수 있게 해 뒀다 — **지우지 않고 옮겼다**

`/var/backups/n8n-s11/` (2.7 GB, `0700 root`):

| | |
|---|---|
| `database.sqlite` | n8n DB 온라인 스냅숏(sqlite Backup API — WAL 안전). 152 MB |
| `units-and-runners.tar.gz` | 유닛 파일 · `/etc` 설정 · `/opt` 러너 소스 |
| `n8n-workflows-s11.tar.gz` | 위 export 와 같은 파일(sha256 일치) |
| `removed-units/` · `removed-opt/` · `removed-etc/` | 시스템에서 옮겨 온 원본 그대로 |
| `SHA256SUMS` | 위 셋의 체크섬 |

데이터 디렉터리는 738 MB 라 복사본을 하나 더 만들지 않고 `/var/lib/n8n.removed-s11` 로
이름만 바꿔 두었다. 디스크 회수(`rm -rf`)는 **사람이 확인한 뒤** 할 일로 남긴다 —
이 세션이 되돌릴 수 없게 만들 이유가 없다.

## 4. 제품은 그대로 산다

`clovirone-web-assistant` · `clovirone-web-worker` · `clovirone-web-worker-conversational` ·
`clovirone-privhelper` · `nginx` 전부 `active`. failed unit **0건**.

⚠️ 이 서버에 도는 것은 **아직 S2 이전 빌드**다(WORK_STATE). 그 빌드의 채팅은 n8n 을 부르므로
지금부터 답을 못 한다 — 의도한 결과다. 새 빌드의 채팅은 n8n 을 안 부른다(아래).

## 5. 「자체 경로 검증」은 어디에 있나

INVENTORY 09 가 요구한 순서 중 셋째 단계다. 서버 로그가 아니라 **시험**이 그 자리를 든다:

| 무엇 | 어디 |
|---|---|
| 채팅이 제품 안에서 답하고, 권한이 먼저 걸리고, **아무 데도 HTTP 를 안 보낸다** | `tests/integration/test_chat_answers_from_retrieval.py` (7건) |
| 지운 것이 돌아오지 않는다 — import·라우트·허용 목록·표·컬럼·배포 산출물 | `tests/regression/test_external_automation_removed.py` (9건) |
| 권한이 `LIMIT` 앞에 걸린다(그 계약 자체) | `tests/security/test_ai_retrieval_permission.py` (S10) |

특히 권한 시험은 「답변에 안 나왔다」가 아니라 **모델에게 실제로 넘어간 문자열**을 본다
(D-202). 옛 경로가 지키지 않던 것이 정확히 그것이다: n8n 이 `returnAll: true` 로 Notion
작업 DB 전량을 가져와 러너에 넘겼고, 러너는 `tickets[:800]` 을 그대로 프롬프트에 실었다.
요청자는 대명사 해석에만 쓰였지 필터가 아니었다.
