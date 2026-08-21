# INVENTORY 06 — Dependency

**정본**: `requirements*.txt` · `frontend/package.json` · 서버 apt 상태
**측정**: 2026-08-20 (Plan Mode) — **전량 열거는 S1 이 채운다**

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
| `postgresql-16` | **설치 가능** — 16.14-0ubuntu0.24.04.1 (noble-updates/main) |
| `postgresql-16-pgvector` | **설치 가능** — 0.6.0-1 (noble/universe) |
| PostgreSQL / Redis / Ollama | 현재 **전부 미설치** (5432/6379/11434 미청취) |

## 신규 도입 후보 — 전부 라이선스 확인 완료

| 영역 | 채택 | 라이선스 |
|---|---|---|
| DB / Vector / Keyword | PostgreSQL 16 · pgvector 0.6.0 · pg_trgm · postgresql-contrib | PostgreSQL License |
| Embedding | bge-m3 또는 multilingual-e5-base (CPU/ONNX) | MIT — **S1 실측 후 확정** |
| Re-rank | bge-reranker-v2-m3 (CPU) 또는 RRF 융합 | Apache-2.0 — **S1 실측 후 확정** |
| Editor | TipTap (**MIT extension 만**. Pro 는 상용이라 쓰지 않는다) | MIT |
| DnD | dnd-kit | MIT |
| Parser | pypdf/pdfplumber · python-docx · python-pptx · openpyxl | BSD/MIT |
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

**S1 것은 모델 선택뿐이고 그것은 P-03 벤치의 산출물이다** — 별도 조사 작업이 아니다.

| 미확인 | Owner | 언제 필요한가 |
|---|---|---|
| Embedding / Re-rank 모델 확정 | **S1** (P-03) | CPU 벤치 결과가 곧 답이다. 리랭커가 느리면 RRF 융합으로 대체한다 |
| `requirements*.txt` · `frontend/package.json` 전량 열거와 충돌 확인 | **S4** | Installer Stage 1·4 를 쓸 때 |
| 오프라인 Bundle **wheelhouse** 에 신규 Python 의존이 전부 들어가는지 | **S4** | 폐쇄망 설치가 여기서 깨진다 (`INSTALLATION.md` §3.1) |
| 임베딩/리랭킹 모델 파일의 오프라인 캐시 배치 경로 | **S4 · S9** | Installer Stage 12 |
