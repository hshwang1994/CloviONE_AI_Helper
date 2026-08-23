# EVIDENCE — S12 (Backup / Restore 운영)

> 이 폴더의 파일이 정본이다. 아래 글은 **그 파일을 어떻게 읽는가**만 적는다.

## [`restore_rehearsal.txt`](restore_rehearsal.txt) — 복구 리허설 실측

실 PostgreSQL 16.15 + 실 `pg_dump`/`pg_restore` 에서 돌린 원문이다. 개발 머신(Windows)에는
`pg_dump` 가 없어 테스트 서버(10.100.64.71)의 사용자 공간 PG(`~/s1pg`)를 썼다 — S2 가
`pg_backup_roundtrip.txt` 를 잰 곳과 같다.

**이 파일이 S12 의 Exit 조건 둘을 함께 진다.**

| Exit 조건 | 어디서 보이나 |
|---|---|
| 복원 후 **앱 기동 + 읽기 경로 호출** 통과 | 정상 회차의 `read_paths_ok: 13` |
| **파일 생성만으로 SUCCESS 안 됨** 확인 | 반례 A |

### 정상 회차

8단계 전부 통과. 표 94 · 행 173 · `alembic_head` 가 코드와 복원본에서 같고, 복원본을 물고
띄운 앱이 **13개 읽기 경로를 전부 200 으로** 돌려줬다(인증 11개 포함).

세트 안에 무엇이 있는지도 그대로 찍었다 — `database.dump` · `manifest.json` · `SHA256SUMS`.
`sha256sum -c` 가 **우리 도구 없이** 둘 다 확인한다.

그 뒤 코드를 몇 군데 더 다듬어서 **실제로 커밋되는 코드로 한 번 더** 돌렸다(같은 파일의
「커밋될 코드로 다시 한 번」 절, 파일 지문을 함께 찍었다). 증거가 나온 코드와 배포되는
코드가 다르면 그 증거는 다른 물건의 증거다. 그 회차도 `read_paths_ok: 13` 이고, 마지막 줄의
`0` 은 **리허설이 만든 복원본 데이터베이스를 스스로 다 치웠다**는 뜻이다.

### 반례 셋 — 판정이 틀린 쪽으로도 움직이는가

통과만 있는 하네스는 아무것도 증명하지 않는다. 셋 다 실 도구 위에서 만들었다.

| 반례 | 무엇을 깨뜨렸나 | 어디서 걸렸나 |
|---|---|---|
| **A** | `pg_dump` 자리에 «rc=0 으로 끝나고 아카이브가 아닌 파일을 쓰는» 껍데기 | 2단계 — 백업 행이 `failed` 다. **파일은 생겼다** |
| **B** | 세션 쿠키가 안 실리는 상태(`http://`) | 7단계 — 인증 경로 11개가 401. `read_paths_ok: 2` |
| **C** | `pg_dump` 자리에 «`--exclude-table-data` 를 떨어뜨리는» 껍데기 | 5단계 — 제외 대상 표 셋에 행이 남아 있다 |

### 배포 스냅숏 보존 (D-271)

같은 파일 끝에 `deploy/install.sh::prune_snapshots` 를 실 리눅스에서 돌린 결과가 있다.
**알려진 좋음**(30일 지난 스냅숏 둘은 지운다, 이름 구분자 두 가지 다) 과 **알려진 나쁨**
(오늘 것은 남기고, 60일이 지나도 **사람이 손으로 둔 디렉터리는 안 지운다**)을 함께 본다.

### 🔴 반례 B 는 **이 세션이 실제로 밟은 함정**이다

첫 회차는 `RESTORE_REHEARSAL_OK` 를 찍었는데, 그 안에서 인증 읽기 경로 **11개가 전부
401** 이었다. 판정이 `5xx` 만 실패로 봤기 때문이다 — 「앱이 떴다」는 확인했고 「앱을 쓸 수
있다」는 아무것도 확인하지 못한 상태에서 초록이 났다.

S12 가 막으려는 실패가 정확히 그 모양이라, 그 회차를 지우지 않고 반례로 남겼다. 판정은
**「200 이 아니면 실패」** 로 바꿨다.

## 재현

```bash
# 테스트 서버에서 (~/s1pg 를 띄운 뒤)
. ~/s1pg/env.sh
cd ~/s12rehearsal
export DATABASE_URL="postgresql:///s12src"
export DATA_DIR="$HOME/s12rehearsal/var"
export PG_BIN_DIR="/home/cloviradmin/s1pg/root/usr/lib/postgresql/16/bin"
~/s9verify/venv/bin/python scripts/restore_rehearsal.py --record
```

`--record` 는 결과 한 줄을 `restore_rehearsals` 에 남긴다. 관리 콘솔의 「복구 리허설」
화면이 그 표를 읽는다.

## 여기 없는 것

- **실 NAS 에서의 백업 저장소 사본.** 시험 Storage 는 S8 이 세운 같은 서버의 NFS/SMB 이고
  (R11 은 살아 있다), 이 리허설은 저장소 없이 돌았다 — 매니페스트의 `warnings` 가 그
  사실을 그대로 적는다. 사본 경로 자체는
  `tests/integration/test_backup_destination_and_warnings.py` 가 못박는다.
- **운영 데이터에서의 리허설.** 운영 데이터는 아직 SQLite 에 있다(S13·S14).
