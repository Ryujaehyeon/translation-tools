# Stellaris Korean Translation Tools

Maintenance tools for building Korean localisation add-ons for Stellaris mods.

The main entry point is `run.ps1`.

```powershell
.\run.ps1 status <workshop_id>
.\run.ps1 extract <workshop_id>
.\run.ps1 validate <workshop_id>
.\run.ps1 review <workshop_id> --mark-errors
.\run.ps1 export <workshop_id> --dry-run
```

Shared defaults live in `maintenance/tooling.ini`.

Secrets such as `tools/openai_api_key.txt` and generated reports/backups are intentionally ignored.

