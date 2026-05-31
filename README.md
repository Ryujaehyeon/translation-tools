# Stellaris Korean Translation Tools

Stellaris 모드 한국어 번역 애드온 제작용 유지보수 도구 모음입니다.

자세한 사용법은 **[매뉴얼](maintenance/manual.md)** 을 참고하세요.

## 빠른 시작

진입점은 `run.ps1`입니다. `translation-tools/` 디렉토리에서 실행합니다.

```powershell
.\run.ps1 status <workshop_id>
.\run.ps1 extract <workshop_id>
.\run.ps1 validate <workshop_id>
.\run.ps1 review <workshop_id> --mark-errors
.\run.ps1 export <workshop_id> --dry-run
```

파이프라인 전체 자동 실행:

```powershell
# 스캔 → 계획 → 리포트 → 적용
python tools/run_pipeline.py --mode scan
python tools/run_pipeline.py --mode plan --use-cache
python tools/run_pipeline.py --mode report --use-cache
python tools/run_pipeline.py --mode auto --use-cache
```

## 구조

```text
run.ps1                        # 진입점
tools/                         # 핵심 Python 스크립트
maintenance/
  tooling.ini                  # 공유 기본 설정
  manual.md                    # 상세 사용 매뉴얼
  COLLABORATION.md             # 협업 가이드 (Codex 포함)
  translation_keys/            # 모드별 키 CSV
  reports/                     # 자동 생성 리포트
  backups/                     # 적용 전 백업
```

공유 기본값은 `maintenance/tooling.ini`에 있습니다.

`tools/openai_api_key.txt`, 리포트, 백업 파일은 `.gitignore`로 제외됩니다.
