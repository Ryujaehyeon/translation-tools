# Stellaris Korean Translation Tools

Stellaris 모드 한국어 번역 애드온 제작용 유지보수 도구 모음입니다.

## 시작

`translation-tools/` 디렉토리에서 실행합니다.

```powershell
.\run.ps1 extract <workshop_id>   # 키 추출
.\run.ps1 export <workshop_id>    # 번역 파일 생성
.\run.ps1 validate <workshop_id>  # 검증
```

자세한 사용법 → [매뉴얼](maintenance/docs/manual.md)
협업 가이드 → [COLLABORATION.md](maintenance/docs/COLLABORATION.md)

## 주의

`tools/api_key.txt`, 리포트, 백업, CSV는 `.gitignore`로 제외됩니다.
