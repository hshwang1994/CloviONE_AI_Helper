# INVENTORY 06 — Dependency

**정본**: `requirements*.txt` · `frontend/package.json` · 서버 apt 상태
**측정**: 2026-08-20 (Plan Mode) · **갱신**: 2026-08-21 (S1 — 모델 확정)

## 서버 런타임 (실측 10.100.64.71)

| 항목 | 값 |
|---|---|
| OS | Ubuntu 24.04.2 LTS (noble), kernel 6.8.0-138 |
| CPU | Intel Xeon E5-2699 v4 @ 2.20GHz — **8 vCPU** (VMware VM) |
| RAM | **15 GiB** (사용 1.4 GiB) + swap 4 GiB |
| Disk | 1006 GB, **935 GB 여유** |
| **GPU** | **없음** — `VMware SVGA II Adapter` 뿐. `nvidia-smi` 없음 (**U1 의 근거**) |
| Python | 3.12.3 (시스템 = venv) |
| Node | **v22.23.1 설치돼 있음** (`/opt/nodejs`, n8n 용) — `PRODUCT.md:77` 의 "서버에 Node 가 없다"는 **낡은 서술** |
| Network | **외부 인터넷 접근 가능** (archive.ubuntu.com · pypi · npmjs · huggingface 전부 200). 프록시 없음 |
| NFS/NAS | **마운트 0건**, `nfs-common`·`cifs-utils` **미설치** |
| 시간/로케일 | Asia/Seoul (KST), `en_US.UTF-8`, NTP 동기 |

> `PRODUCT.md` 가 말하는 "폐쇄망" 은 **사용자 접근** 기준이다. **아웃바운드는 열려 있다.**

## 설치 가능성 (apt 실측)

| 패키지 | 상태 |
|---|---|
| `postgresql-16` | **설치 가능** — **16.15-0ubuntu0.24.04.1** (noble-**security**/main). 2026-08-20 에 보이던 16.14(noble-updates)보다 최신이다. S4 는 버전을 고정하지 말고 **`postgresql-16` 을 그대로 쓰고 설치된 버전을 manifest 에 기록**한다 |
| `postgresql-16-pgvector` | **설치 가능** — 0.6.0-1 (noble/universe) |
| `postgresql-contrib` | **설치 가능** — 16+257build1.1 |
| PostgreSQL / Redis / Ollama | 시스템에는 여전히 **미설치** (5432/6379/11434 미청취). S1 은 실측을 위해 같은 `.deb` 를 **사용자 홈에 전개**해 띄웠다 — 시스템 설치는 S4 Stage 6·7 |

**S1 실측 확인**: 위 셋을 실제로 전개해 `PostgreSQL 16.15` · `vector 0.6.0` · `pg_trgm 1.6` 이
함께 뜨는 것을 확인했다. `CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;` 둘 다 통과.

## 신규 도입 후보 — 전부 라이선스 확인 완료

| 영역 | 채택 | 라이선스 |
|---|---|---|
| DB / Vector / Keyword | PostgreSQL 16 · pgvector 0.6.0 · pg_trgm · postgresql-contrib | PostgreSQL License |
| Embedding | **`intfloat/multilingual-e5-small` (384차원, ONNX)** — **확정 (D-211)** | MIT |
| Re-rank | **쓰지 않는다. RRF 융합** — **확정 (D-212)** | — |
| ONNX Runtime | `onnxruntime` (CPU) + `tokenizers` — **torch 없음** | MIT |
| Editor | TipTap (**MIT extension 만**. Pro 는 상용이라 쓰지 않는다) | MIT |
| DnD | dnd-kit | MIT |
| Parser | **`pypdf` 하나만 채택 (S9 · D-258)**. DOCX·PPTX·XLSX 는 표준 라이브러리(`zipfile`+`xml.etree`)로 읽는다 — 글자와 앵커만 필요해서 패키지 셋을 늘리지 않았다 | BSD-3 |
| ONNX Runtime | CPU 빌드 | MIT |

## 도입하지 않는 것 — 결정으로 기록한다

| 항목 | 이유 |
|---|---|
| **Docling** | torch 의존이 CPU-only 8 vCPU 에 과하다. 품질 부족이 실측되면 그때 Adapter 로 추가 |
| **별도 Vector DB** | pgvector 로 충분하다. 우리 Corpus 는 chunk 수만 단위다 |
| **Redis (Cache/Queue)** | PG advisory lock + 테이블로 충분하다. **Component 를 필요 없이 늘리지 않는다** |
| **OCR / ClamAV / LibreOffice** | 폐쇄망 사내 도구 + 현재 업로드 파일 4개. 설정 Hook 만 남긴다 |
| **PGDG 저장소 (PG17 + pgvector 0.8.x)** | **지원되는 선택지로 문서화하되 제품 필수 의존이 아니다.** 고객이 PGDG 를 미러링하지 않으면 설치가 막힌다 (D-188) |

## 미확인 항목과 Owner

| 미확인 | Owner | 언제 필요한가 |
|---|---|---|
| ~~Embedding / Re-rank 모델 확정~~ | ~~S1~~ | **완료 (2026-08-21).** `multilingual-e5-small`(384) · 리랭커 미채택 → RRF. 실측 표는 **D-211 · D-212** |
| 긴 본문에서의 모델 재검토 | **S10** | S1 품질 측정은 **제목 부분구간** 질의였다(본문 캐시가 없다). S13 이 Notion 본문을 실어 온 뒤 S10 이 실제 본문으로 다시 잰다 — 필요하면 `bge-m3` 로 올린다(Adapter 뒤라 교체 비용은 재색인뿐이다) |
| `requirements*.txt` · `frontend/package.json` 전량 열거와 충돌 확인 | **S4** | Installer Stage 1·4 를 쓸 때 |
| ~~오프라인 Bundle wheelhouse 에 신규 Python 의존~~ | ~~S4~~ | **S9 이 실측했다 (2026-08-23)** — `requirements.txt` + `requirements-ai.txt` 를 Ubuntu 24.04 / Python 3.12 에 함께 깔아 확인했다(테스트 서버). AI 의존은 별도 파일이고 **Stage 12 가 깐다**(D-258) |
| ~~임베딩 모델 파일의 오프라인 캐시 배치 경로~~ | ~~S4 · S9~~ | **확정 (2026-08-23)** — `<data_dir>/ai/models/<모델 디렉터리>`. `storage_providers` 와 **별개**다(재생성 가능한 자산이라 백업 대상이 아니다 — D-203·D-204). 배치는 `ai_cli install-model --from`, 판정은 `ai_cli status` 의 종료코드 (D-259) |
