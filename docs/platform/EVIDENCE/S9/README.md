# EVIDENCE / S9 — AI Platform 1 (Gateway · Pipeline)

> S9 의 Exit 조건은 **「생성 Adapter 비활성 상태에서 색인·임베딩 정상 · injection 회귀」**다
> (`MASTER_PLAN.md` §9.1 · `BACKLOG.md` P-18). 이 디렉터리는 그중 **가짜 Adapter 로는
> 증명할 수 없는 절반**의 원장이다.

## 왜 실검증이 따로 있는가

`tests/` 의 임베딩은 전부 가짜 Adapter 로 돈다. 실제 모델을 전 스위트의 전제로 만들지
않는 이유는 S8 이 실 NFS 를 전제로 만들지 않은 것과 같다 — 465MB 짜리 파일과 8 vCPU 가
필요하고, 그것이 없는 기계에서 전 스위트가 멈추면 안 된다.

그런데 **가짜로는 안 나오는 결함이 있다.** 넷을 겨눴다:

| 무엇 | 가짜로 안 나오는 이유 |
|---|---|
| ONNX 세션의 입력 이름이 export 마다 다르다 (`token_type_ids` 유무) | 세션이 없으면 그 계약도 없다 |
| 패딩을 안 켜면 길이가 다른 배치가 죽는다 | 가짜는 길이를 안 본다 |
| 자르기를 안 걸면 512 토큰 초과에서 죽는다 | 가짜는 토큰을 안 센다 |
| **접두사를 안 붙이면 오류가 하나도 안 나고 품질만 떨어진다** | 가짜에는 품질이 없다 |

앞 셋은 죽어서 드러나고 넷째는 안 드러난다. 그래서 넷째를 **수치로** 본다.

## 실행

```bash
# 서버(10.100.64.71)에서. 모델은 S1 이 받아 둔 것을 그대로 쓴다.
cd ~/s9verify
./venv/bin/python scripts/verify_ai_pipeline.py \
    --model-root ~/s1bench/models --workdir /tmp/s9fix --out /tmp/s9_report.json
```

하네스 정본은 `scripts/verify_ai_pipeline.py` 다. 숫자만 남기고 재는 방법을 버리면
다음 사람은 그 숫자를 **믿거나 처음부터 다시 재는 것** 둘 중 하나만 할 수 있다.

## 결과 — **17/17 통과** (2026-08-23)

원장: [`real_embed_pipeline.json`](real_embed_pipeline.json)

| 축 | 값 |
|---|---|
| 모델 | `intfloat/multilingual-e5-small` (384차원 · D-211) |
| 생성 Adapter | **비활성** (`unconfigured`) — 그 상태에서 아래가 전부 돌았다 |
| 첫 호출(세션 로드 포함) | 3.91초 |
| 처리량 | 256건 3.19초 = **80.2 docs/s** |
| 질의 지연 | p50 **5.31ms** · max 5.99ms |
| 최대 RSS | **1,001.7 MB** |
| 의미 | 질의↔맞는 본문 **0.8849** > 질의↔상관없는 본문 **0.8016** |
| 접두사 격차 | `query:` 와 `passage:` 벡터의 코사인 거리 **0.060378** |

### 형식마다 자기 앵커가 나온다

| 파일 | 상태 | 단위 | chunk | 앵커 | 예시 |
|---|---|---|---|---|---|
| `회의록.docx` | ok | 2 | 2 | `section` | `s1` |
| `발표.pptx` | ok | 2 | 2 | `slide` | `1` |
| `예산.xlsx` | ok | 1 | 1 | `sheet` | `예산!A1:B5` |
| `규격서.pdf` | ok | 2 | 2 | `page` | `1` |

### 반례도 함께 돌았다

「검사가 위반을 못 찾았다」와 「검사가 아무것도 안 봤다」는 다르다(D-213). 그래서
통과 사례만 보지 않는다:

- **모델이 없는 뿌리는 거절한다** — `model_missing` (「있다」로 안 읽는다)
- **정규화 안 된 벡터는 길이 검사가 잡는다** — 그 검사가 항상 참이면 위 「길이 1」이
  아무것도 확인하지 않는다
- **질의 지연이 상수가 아니다** — 전 표본이 같으면 측정이 아니라 상수를 읽는 것이다
  (S1 이 그 함정을 한 번 밟았다)

## S1 실측과의 대조 (D-211)

| | S1 (`scripts/bench/embed.py`) | S9 (제품 Gateway) |
|---|---|---|
| 색인 처리량 | 120 docs/s (batch32) | **80.2 docs/s** |
| 질의 p50 | 5.95ms | **5.31ms** |
| 최대 RSS | 1,500.6 MB | **1,001.7 MB** |

질의 지연과 RSS 는 S1 보다 낫고 처리량은 낮다. **낮은 것이 결함이 아니다** — S1 의
코퍼스는 제목 줄이었고 S9 는 chunk(문단 12벌)라 문서당 토큰 수가 다르다. 같은 축으로
비교하려면 같은 입력으로 다시 재야 하고, 그것은 S10 이 실 본문으로 모델을 재검토할 때
할 일이다(D-211 상향 경로).

## 설치 경로 — LXD Clean 설치 **35/35 통과** (2026-08-23)

원장: [`lxd_rehearsal.txt`](lxd_rehearsal.txt) · [`install_ai_status.json`](install_ai_status.json)

```bash
sudo bash scripts/lxd_rehearsal.sh <source.tar.gz> s9-rehearsal
```

Clean 설치 → verify → 재실행(idempotent) → 실패 주입 → rollback → upgrade → 컨테이너
재시작 복구 → uninstall → 재설치 → 옛 slug 이전 → purge. **`[FAIL]` 0건 · `LXD_REHEARSAL_OK (35항)`.**

| Stage | 결과 |
|---|---|
| 9 · MIGRATION | `revision <없음> → 0007_ai_index · public 표 98개` |
| 11 · STORAGE | `OK 저장소 준비 완료 · 마운트 유닛 0개 · drop-in 6유닛` (**아래 결함을 고친 뒤**) |
| 12 · AI | `OK AI 를 끄고 설치했습니다(--with-ai 로 켭니다) · 모델 캐시 자리만 만들었습니다` |
| 13 · UNITS | `OK 유닛 6종 설치` |
| 14 · ENABLE | `OK postgresql · nginx · 제품 유닛 6종이 enabled` |
| 17 · START | `OK 유닛 5종 active · /healthz · /readyz 200` |

### 🔴 이 실행이 **S8 의 Stage 11 결함**을 잡았다

첫 회차는 Stage 11 에서 설치가 통째로 섰다:

```
PermissionError: [Errno 13] Permission denied: '/tmp/tmp.lzRklX1IW3/10-storage-mounts.conf'
STAGE_11_STORAGE: FAIL 마운트 유닛을 만들지 못했습니다
```

`mktemp -d` 는 **root 소유 0700** 인데 그 안에 파일을 쓰는 것은 `run_as_app` 으로 띄운
**서비스 계정**이다. S8 은 Storage 를 **호스트에서 root 로** 검증했고 Clean 설치 경로는
한 번도 안 지났다. 소유를 넘기고, 「서비스 계정에 넘기는 디렉터리는 그 계정 소유여야
한다」를 `tests/unit/test_deploy_wiring.py` 가 계약으로 지킨다.

같은 실행에서 리허설의 단언 둘도 낡아 있었다(Stage 11·12 를 여전히 `SKIP` 으로 기대했다).
**늘 실패하는 검사는 없는 검사보다 나쁘다** — 함께 고쳤다.

## `--with-ai` 설치 — **실 모델로 Stage 12 통과** (2026-08-23)

같은 방식으로 컨테이너 하나를 더 세우고 모델 465MB 를 밀어 넣은 뒤:

```bash
deploy/install.sh install --source local --dns-name clovirassist.ai.invalid \
    --bind-ip 127.0.0.1 --ai-model-dir /tmp/aimodels
```

```
STAGE_12_AI: OK AI 런타임 + 모델 로드 검증 통과
INSTALL_OK dns=clovirassist.ai.invalid
```

설치 직후의 `ai_cli status`(원장 파일) — 🔴 **`generate` 가 비활성인 채로 `embed` 가
`ok`** 다. 그것이 S9 의 Exit 조건 문구 그대로다.

| 능력 | 상태 |
|---|---|
| `embed` | **available · `intfloat/multilingual-e5-small`** |
| `rerank` | `unsupported` — 「RRF 융합으로 대신합니다(D-212)」 |
| `generate` | `unconfigured` — 모델 이름을 안 정했다(D-254 의 fail-closed) |

`ai_cli selftest` → `{"ok": true, "dim": 384, "count": 2, "problems": []}` (종료코드 0).
`clovirassist-index.service` 는 **active · enabled**, `/readyz` 는 `{"status":"ready"}`.

> `ai_cli status` 를 env 파일 없이 부르면 `index` 칸이 `{"error": "OperationalError"}` 로
> 나온다. **그것이 의도다** — 「못 셌다」를 0 으로 적으면 「없다」와 구별되지 않는다.

## 이 원장이 **증명하지 않는 것**

- **실 모델로 문서를 색인해 DB 에 넣어 본 것은 아니다.** 위 둘은 각각 절반이다 —
  실 모델 파이프라인은 DB 없이(테스트 서버 호스트), DB 왕복은 가짜 Adapter 로(개발 머신의
  **실 PostgreSQL 16 + pgvector 0.8.6**). 둘을 한 번에 잇는 것은 실 데이터가 들어온 뒤,
  즉 S13 적재 이후에 의미가 있다.
- **진짜 커널 재부팅은 여기 없다.** `lxc restart` 는 컨테이너 init 을 다시 돌릴 뿐이다
  (R15). 색인 유닛은 다른 다섯과 같은 모양(`enable` + `WantedBy=multi-user.target`)이고,
  실 재부팅 축은 S4 가 닫았다(D-229).
- **실 NAS 위의 첨부는 여기 없다.** 파일 저장소 축은 S8 원장이 든다.
- **생성 품질은 여기 없다.** 생성 Adapter 를 일부러 끈 채로 잰 값이다.
