# S8 EVIDENCE — File Storage 16항 매트릭스 (실 NFS · 실 SMB)

> 원본 로그: [`matrix_nfs.json`](matrix_nfs.json) · [`matrix_smb.json`](matrix_smb.json)
> 하네스: [`scripts/storage_matrix.py`](../../../../scripts/storage_matrix.py)
> 실행: **2026-08-23** · 호스트 `clovirassist`(10.100.64.71, Ubuntu 24.04.2, 커널 6.8.0-138)

## 결과

| | NFS | SMB |
|---|---|---|
| 16항 | **16 PASS · 0 FAIL** | **16 PASS · 0 FAIL** |
| 파일시스템 | `nfs4` (127.0.0.1:/srv/clv-nfs-export) | `cifs` (//127.0.0.1/clvtest) |
| 마운트 유닛 | `mnt-clv\x2dnfs.mount` | `mnt-clv\x2dsmb.mount` |

## ⚠️ 이 증거가 **아닌** 것 (U9 · D-199)

**시험 Storage 이지 실 NAS 장비가 아니다.** 같은 서버 위에 NFS export 와 Samba share 를
세워 붙였다. 실 장비에서 나오는 결함(펌웨어 · 네트워크 경로 · 인증 통합 · 성능)은 여기서
안 나온다. 실 장비 정보를 받으면 **Configuration 만** 바꾼다 — 그것이 Provider 를 장비
이름이 아니라 접근 Protocol 로 나눈 이유다(D-199).

`caveat` 문장은 두 JSON 파일에도 그대로 들어 있다.

## 항목별 — 무엇으로 증명했나

`by` 는 증거의 출처다. 앱과 DB 가 있어야 볼 수 있는 사실(HTTP 지위 · `files` 행)은 실
마운트에서 볼 수 없으므로 **pytest 가 실제 앱으로** 든다. 두 곳을 합쳐야 한 항목이 닫힌다.

| # | 항목 | by | 무엇을 봤나 |
|---|---|---|---|
| 1 | Mount | real-mount | `fstype=nfs4`/`cifs` · 유닛 active · `st_dev`·mountinfo 일치 |
| 2 | Read/Write | real-mount | 2,091바이트를 쓰고 그대로 읽었다 |
| 3 | Permission | real-mount | **서비스 계정으로** 쓴다(`clvsvc`, uid 1003, mode 0750) · 권한 없는 자리는 `PermissionError` |
| 4 | Create/Delete | real-mount | 만들고 지웠다 · 없는 것을 다시 지우는 것은 오류가 아니다 |
| 5 | Checksum | real-mount | 쓰기·읽기·기대값 sha256 3자가 일치 |
| 6 | Capacity | real-mount | 1,005.6 GiB 중 928.0 GiB 여유 |
| 7 | Storage unavailable | real-mount + pytest | 없는 마운트에 쓰기 거부 + **HTTP 503(500 아님)** 은 `tests/regression/test_storage_write_refusal.py` |
| 8 | Reconnect | real-mount | 공유 서버를 내렸다 올린 뒤 **앱 재시작 없이** 다시 썼다 |
| 9 | 부분 파일 미커밋 | real-mount + pytest | 커밋(`os.replace`) 실패 뒤 최종 이름 없음 · 임시 파일 없음 · **DB 행 미생성**은 pytest |
| 10 | Reboot | reboot-phase | `boot_id` 가 바뀌었다 — 실제로 재부팅했다 |
| 11 | Reboot 후 자동 Mount | reboot-phase | **수동 명령 0회**로 마운트가 돌아왔고 재부팅 전 파일의 체크섬이 그대로다 |
| 12 | RequiresMountsFor | real-mount | `systemctl show` 로 **systemd 에게 직접 물었다** — 앱 유닛 4종이 두 마운트를 기다린다 |
| 13 | `st_dev` 가드 | real-mount | 마운트를 실제로 떼고 써 봤다 — 거부했고 **로컬에 아무것도 안 남았다** |
| 14 | Backup | real-mount + pytest | 3/3건을 백업 저장소로 옮기고 **다시 읽어** 체크섬을 맞췄다 · 행 기준 이관은 pytest |
| 15 | Restore | real-mount + pytest | 3/3건을 되돌리고 원본 체크섬과 맞췄다 |
| 16 | 운영/백업 동일 저장소 | real-mount | 장치 비교가 살아 있다(자기 자신=True) · 두 저장소는 다른 장치 |

재부팅은 **두 조각**이다(`pre-reboot` → `sudo reboot` → `post-reboot`). 한 스크립트가
재부팅을 걸고 그대로 이어서 확인하면 그 사이에 사람이 무엇을 했는지 구분할 수 없다.
`scripts/reboot_check.sh` 가 같은 이유로 같은 모양이다.

## 이 검증이 **찾아낸** 제품 결함 셋 — 전부 고쳤다

셋 다 시험이 없으면 안 잡힌다. 셋 다 마운트는 멀쩡하고 `st_dev` 가드도 통과한다.

### 1. NFS 기본값에서 서버가 죽으면 **쓰기가 안 돌아온다**

`Options=defaults` 로 붙인 NFS 는 `hard,timeo=600` 이다. `systemctl stop nfs-kernel-server`
뒤의 쓰기 한 번이 **5분이 지나도 안 끝났다.** 그 상태에서는 D-199 7번(「Storage
unavailable 은 503 이지 500 이 아니다」)이 **성립할 수가 없다** — 503 도 500 도 안 나가고
요청이 영영 안 끝난다. `--workers 4` 짜리 웹이 NAS 장애 하나로 통째로 멈춘다.

`soft` 가 보통 위험한 이유(쓰다 만 파일이 조용히 잘린다)는 **이 제품에 없다**: 임시
이름에 쓰고 `fsync` 한 뒤 `os.replace` 로 올리므로, 시간 초과로 실패하면 최종 이름이
안 생기고 DB 행도 안 생긴다. 그래서 기본값을 `soft,timeo=50,retrans=2` 로 바꿨다
(`app/storage/units.py::_timeout_defaults`). 운영자가 `hard` 를 적었다면 덮지 않는다.

**장애 중 쓰기가 돌아오기까지 걸린 시간은 회차마다 달랐다** — 단독 측정은 세 번 모두
30.1초, 매트릭스 안에서는 21초(SMB)와 180초 초과(NFS)였다. 30초에서 3분 사이로 읽는
것이 정직하다. NFSv4 는 세션 복구가 겹치면 `soft` 상한만으로 안 끝난다.
**「몇 초 만에 503 이 나간다」고 쓰면 그것은 거짓이다.**

### 2. SMB 공유에서 서비스 계정이 **아무것도 못 쓴다**

`uid=0,gid=0` 으로 붙인 cifs 공유는 모든 파일의 주인이 root 로 고정되고, cifs 는
`chown` 을 안 받으므로 고칠 방법도 없다. 그런데 **마운트는 멀쩡하다** — `st_dev` 가드도
fstype 검사도 전부 통과한다. 증상은 「올릴 때마다 503」뿐이고 원인은 옵션 한 줄에 있다.

기본값에 `uid=<서비스계정>,gid=<서비스계정>,file_mode=0640,dir_mode=0750` 을 넣었다
(`app/storage/units.py::_ownership_defaults`). 운영자가 적은 값은 덮지 않는다.

### 3. `.mount` 유닛 이름의 역슬래시가 셸에서 먹힌다

유닛 이름은 경로에서 기계적으로 나오고(`/mnt/clv-nfs` → `mnt-clv\x2dnfs.mount`)
**역슬래시가 들어간다.** 문자열에 그대로 이어 붙이면 bash 가 `\x` 를 `x` 로 먹어
**다른 유닛 이름**이 되고, `systemctl start` 가 조용히 「그런 유닛 없음」으로 끝난다.
하네스가 `shlex.quote` 를 지나게 고쳤다(`scripts/storage_matrix.py::q`).

## 하네스 자신의 결함 하나 — 함께 고쳤다

item 3 의 반례(「권한 없는 자리는 거절된다」)를 **공유 안에** 만들었더니 cifs 에서
`chmod 0700` 이 아무 효력이 없어 반례가 통과해 버렸다. cifs 는 공유 안의 모드 비트를
강제하지 않고 마운트 옵션이 전부를 정한다. 반례를 **마운트 밖**(로컬 경로)으로 옮겼다 —
거기서 확인하려는 것은 「탐지기가 거절을 알아보는가」이지 그 파일시스템의 권한 모델이
아니다.

## 테스트 서버에 남겨 둔 것 (S22 재실행용)

| 무엇 | 어디 |
|---|---|
| NFS export | `/srv/clv-nfs-export` (`127.0.0.1(rw,sync,no_subtree_check)`) |
| Samba share | `/srv/clv-smb-share` (`[clvtest]`, 계정 `clvsmb`) |
| 마운트포인트 | `/mnt/clv-nfs` · `/mnt/clv-smb` (유닛 enabled, 재부팅 뒤 자동 복귀 확인됨) |
| 자격증명 | `/etc/clovirassist/secrets/smb_matrix` (0600, root) — **값은 저장소에 없다** |
| 하네스 사본 | `/opt/clv-matrix-src` |
| 시험 서비스 계정 | `clvsvc` (uid 1003) |

**앱 유닛 파일은 걷어냈다.** item 12 확인이 끝난 뒤 지웠다 — 제품이 설치돼 있지 않은
호스트에 유닛 파일만 남기면 나중에 보는 사람이 「설치돼 있다」로 읽는다.

## 다시 돌리는 법

```bash
# 16항 (재부팅 두 항목은 아래 단계의 결과를 읽어 온다)
sudo python3 scripts/storage_matrix.py run --kind NFS \
    --mount-point /mnt/clv-nfs --base-path /mnt/clv-nfs/files \
    --backup-path /var/backups/clv-storage-test \
    --service nfs-kernel-server --as-user clvsvc \
    --state /var/lib/clv-matrix-nfs.json --out matrix_nfs.json

# 재부팅 두 항목 — 그 사이에 사람은 아무것도 하지 않는다
sudo python3 scripts/storage_matrix.py pre-reboot --state /var/lib/clv-matrix-nfs.json \
    --mount-point /mnt/clv-nfs --base-path /mnt/clv-nfs/files --kind NFS
sudo reboot
sudo python3 scripts/storage_matrix.py post-reboot --state /var/lib/clv-matrix-nfs.json
```
