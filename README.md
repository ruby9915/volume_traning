# 운동 볼륨 트래킹 앱

웨이트 트레이닝 볼륨(중량×횟수×세트)을 기록·분석하는 1인용 반응형 웹앱.
React(Vite) + FastAPI + SQLite. 연구실 PC(24시간 구동)에서 서버를 돌리고 **Tailscale Funnel**로 외부(헬스장 LTE)에서 접속한다.

설계의 단일 기준은 [`SETTING.MD`](./SETTING.MD)이다. 이 문서는 설치·개발·운영·백업 절차 요약본이다.

## 저장소 구조

```
backend/    FastAPI + SQLite (uv, pyproject.toml)
frontend/   React SPA (Vite)
scripts/    운영 스크립트 (start-server / register-startup / backup)
```

## 요구 사항

- Windows 11 (운영 서버 기준), PowerShell 5.1+
- Python 3.13 + [uv](https://docs.astral.sh/uv/)
- Node 24 + npm
- [Tailscale](https://tailscale.com/download/windows) (외부 공개용, 무료)

## 환경변수 (최초 1회)

secret은 `backend/.env` 한 곳에만 둔다 (git 커밋 금지, `.gitignore` 처리됨).

```powershell
Copy-Item backend\.env.example backend\.env
# backend\.env 를 열어 값 채우기:
#   APP_PASSWORD = 로그인 비밀번호
#   JWT_SECRET   = 긴 랜덤 문자열 (예: python -c "import secrets; print(secrets.token_hex(32))")
#   DB_PATH      = 기본값 사용 (backend/data/app.db)
```

- **비밀번호 변경**: 앱에는 변경 UI가 없다. `backend\.env`의 `APP_PASSWORD`를 수정한 뒤 서버를 재시작한다.
- 프론트엔드에는 비밀값을 두지 않는다 (`VITE_*`는 번들에 노출됨).

## 개발 (핫리로드)

```powershell
# 터미널 1 - 백엔드
cd backend; uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 터미널 2 - 프론트 (vite proxy가 /api -> :8000 전달)
cd frontend; npm install
npm run dev -- --host
```

**폰 테스트**: 같은 Wi-Fi에서 `ipconfig`로 PC IPv4 확인 → 폰 브라우저에서 `http://<PC_IP>:5173`.
안 열리면 관리자 PowerShell에서 1회:

```powershell
New-NetFirewallRule -DisplayName "vite-dev" -Direction Inbound -Protocol TCP -LocalPort 5173,8000 -Action Allow -Profile Private
```

네트워크 프로필이 "공용"이면 규칙이 적용되지 않으므로 해당 Wi-Fi를 "개인"으로 변경한다.
(이 방화벽 규칙은 로컬 dev 전용 — Funnel 운영에는 인바운드 개방이 필요 없다.)

## 운영 (상시 서버)

### 수동 기동

```powershell
.\scripts\start-server.ps1
```

frontend 빌드(`npm run build`) → `backend`에서 `uv run uvicorn ... --port 8000` (reload 없음) 순으로 실행한다.
코드 수정 반영 = 이 스크립트 재실행 (빌드 + 서버 재시작).

### 자동 시작 등록 (관리자 PowerShell 필수)

```powershell
# 시스템 시작 시 서버 자동 기동
.\scripts\register-startup.ps1

# 일일 백업(매일 04:00)까지 같이 등록하려면:
.\scripts\register-startup.ps1 -BackupDir "C:\Users\<me>\OneDrive\volume-app-backup"
```

- 등록 확인: `Get-ScheduledTask -TaskName "VolumeApp-*"`
- 즉시 테스트: `Start-ScheduledTask -TaskName "VolumeApp-StartServer"`
- 해제: `Unregister-ScheduledTask -TaskName "VolumeApp-StartServer" -Confirm:$false`
- 서버 로그: `scripts\logs\start-server.log`

### 전원 옵션 점검 (1회)

24시간 구동을 위해 시스템 절전이 꺼져 있는지 확인: `powercfg /a` 또는 설정 > 전원 (절전 모드 "안 함").

## Tailscale Funnel 설정 (외부 공개, 최초 1회)

1. Tailscale 설치 후 로그인 (무료 플랜이면 충분).
2. PowerShell에서:

   ```powershell
   tailscale funnel --bg 8000
   ```

3. 첫 실행 시 브라우저 승인 1회 (MagicDNS·HTTPS 활성화 프롬프트 포함).
4. 발급된 고정 주소로 접속: `https://<pc이름>.<tailnet>.ts.net` — 헬스장 LTE에서 이 주소를 쓴다.
5. 상태 확인: `tailscale funnel status`

- `--bg`는 보통 재부팅 후에도 유지된다. **PC를 한 번 재부팅해서 funnel이 살아있는지 확인**하고, 유지되지 않으면 `scripts\start-server.ps1`의 `tailscale funnel --bg 8000` 주석을 해제한다.
- 아웃바운드 터널이므로 공유기 포트포워딩·인바운드 방화벽 개방이 필요 없다.
- **기관 네트워크에서 터널이 막히면**: 폰에 Tailscale 앱을 설치해 tailnet 내부 접속으로 전환하거나, SETTING.MD §7.5의 유료 클라우드(Fly.io) 경로로 이동한다.

## 백업

| 층 | 수단 | 주기 |
|---|---|---|
| 1 | **서버 내장 자동 백업** — `backend\.env`의 `BACKUP_DIR`에 클라우드 동기화 폴더를 지정하면, 기록이 변경되고 5분 조용해졌을 때(=운동 종료) 자동으로 스냅샷 생성 (기록이 이어지면 30분마다 강제 1회) | 데이터 변경 시 자동 |
| 2 | `scripts\backup.ps1` → 클라우드 동기화 폴더 (Task Scheduler) — 서버가 죽어 있어도 도는 보조 안전망 | 매일 |
| 3 | 앱 설정 화면 또는 `GET /api/export/db` 다운로드 | 수시 |

- 1층은 `BACKUP_DIR`이 비어 있으면 꺼진다. 파일명·보존 규칙은 2층과 동일 (`app-YYYYMMDD.db`, 30개).

```powershell
# 수동 실행 (서버 실행 중에도 안전 - VACUUM INTO 스냅샷)
.\scripts\backup.ps1 -DestinationDir "C:\Users\<me>\OneDrive\volume-app-backup"
```

- 스냅샷 파일명 `app-YYYYMMDD.db`, 대상 폴더에 **최근 30개만 보존** (이전 것 자동 삭제, `-Keep`으로 조정).
- 대상 폴더는 OneDrive/Google Drive 동기화 폴더로 지정해 오프사이트 1겹을 확보한다.
- 자동 등록은 위 `register-startup.ps1 -BackupDir ...` 참조.

## 복구 절차

백업에서 DB를 되살리는 절차. **Phase 2 완료 시 이 절차를 1회 실제 리허설한다** (해보지 않은 백업은 백업이 아니다).

1. 서버 중지: `Stop-ScheduledTask -TaskName "VolumeApp-StartServer"` 후 남은 `uvicorn`(python) 프로세스가 있으면 종료. 수동 실행 중이면 해당 창에서 Ctrl+C.
2. 현재 DB 보전(원인 조사용): `backend\data\app.db`(있다면 `app.db-wal`, `app.db-shm` 포함)를 다른 이름으로 이동.
3. 백업 폴더에서 원하는 스냅샷을 복사: 

   ```powershell
   Copy-Item "C:\Users\<me>\OneDrive\volume-app-backup\app-YYYYMMDD.db" "backend\data\app.db"
   ```

   (스냅샷은 VACUUM INTO 산출물이라 -wal/-shm 없이 단일 파일로 완결.)
4. 서버 재기동: `.\scripts\start-server.ps1` (또는 `Start-ScheduledTask -TaskName "VolumeApp-StartServer"`).
5. 확인: 앱 접속 → 이력 화면에서 스냅샷 날짜까지의 기록이 보이는지 확인. 스냅샷 이후의 기록은 유실분이다.

## 트러블슈팅

- **Task Scheduler에서 `npm`/`uv`를 못 찾음**: 스케줄러 실행 환경의 PATH에 없기 때문. 시스템 환경변수 PATH에 Node·uv 경로를 추가하거나, `start-server.ps1` 상단에서 전체 경로를 쓰도록 수정.
- **재부팅 직후 앱이 안 열림**: 정상 범위 — 부팅 + 빌드 몇 분의 다운타임은 설계상 수용 (SETTING.MD §9). 그 순간의 기록은 폰 메모 후 나중 입력.
- **Funnel URL이 안 열림**: PC에서 `tailscale status`·`tailscale funnel status` 확인. 기관 방화벽이 원인이면 위 "Tailscale Funnel 설정"의 대안 참조.
