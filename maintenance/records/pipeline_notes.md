# 자동 처리 최적화 메모

최종 갱신: 2026-05-16

## 적용된 개선

- `extract_localisation_keys.py`는 기존 CSV를 다시 만들 때 `korean_value` 열을 보존한다.
- 키 CSV는 `key,english_value,korean_value` 구조를 유지한다.
- `run_pipeline.py`는 실행 시작 전에 전체 모드 수, 처리 대상 수, 스킵 사유별 개수를 출력한다.
- 모드 분류는 `english`, `korean_only`, `replace_only`, `no_localisation`, `localisation_without_english`, `missing_mod_folder`로 기록한다.
- `--mode scan`, `--mode plan`, `--mode report`, `--mode apply` 프리셋을 지원한다.
- `--workers auto`가 기본값이며, dry-run/report 계열은 최대 4개 병렬 처리하고 실제 적용 모드는 기본 1개로 둔다.
- `--use-cache`를 켜면 원본 `localisation/english` 파일 수, 최신 수정 시간, 전체 크기가 같고 기존 CSV가 있으면 키 추출을 건너뛴다.
- `--force`를 쓰면 캐시를 무시하고 다시 실행한다.
- 리포트는 `maintenance/reports/<도구명>/` 하위 폴더에 분리 저장한다.
- 최신 리포트를 빠르게 찾을 수 있도록 `maintenance/reports/index.json`과 `maintenance/reports/index.md`를 만든다.

## 권장 실행

처리 대상만 확인:

```powershell
python tools/run_pipeline.py --mode scan
```

작업량만 확인:

```powershell
python tools/run_pipeline.py --mode plan --use-cache
```

리포트 생성 중심으로 전체 dry-run:

```powershell
python tools/run_pipeline.py --mode report --use-cache
```

실제 번역 파일 반영:

```powershell
python tools/run_pipeline.py --mode apply --use-cache
```

원본 변경 여부와 관계없이 다시 추출:

```powershell
python tools/run_pipeline.py --mode report --force
```
