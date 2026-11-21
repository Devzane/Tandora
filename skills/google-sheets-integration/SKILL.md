---
name: google-sheets-integration
description: Google Sheets API v4 bidirectional synchronization for Tandora — authentication, conflict detection, idempotency, and recovery.
risk: low
source: project
date_added: '2026-11-21'
---

# Google Sheets Integration Skill — Tandora

## Purpose

This skill covers the Tandora Google Sheets integration: authenticating with the Google Sheets API, reading and writing spreadsheet data, detecting sync conflicts, and ensuring idempotency.

## When to Use

Read this skill before implementing `integrations/google_sheets.py` or the sync service.

## Required Engineering Practices

### Authentication

Authentication uses a Google service account credentials file. The path is provided via `GOOGLE_CREDENTIALS_PATH` environment variable.

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_sheets_service():
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_credentials_path,
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials)
```

The service account must be granted Editor access to the target spreadsheet.

### Spreadsheet Structure

Each entity type has its own sheet tab in the spreadsheet:

| Tab Name | Entity | Key Column |
|----------|--------|------------|
| Companies | companies | external_id |
| Contacts | contacts | external_id |
| Opportunities | opportunities | external_id |
| Outreach | outreach_threads | external_id |

The first row of each tab is a header row. Never overwrite or delete the header row.

### Reading Data

```python
def read_sheet(service, spreadsheet_id: str, sheet_name: str) -> list[dict]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:Z"
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]
```

### Writing Data

```python
def append_rows(service, spreadsheet_id: str, sheet_name: str, rows: list[list]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows}
    ).execute()

def update_row(service, spreadsheet_id: str, range_: str, values: list) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_,
        valueInputOption="USER_ENTERED",
        body={"values": [values]}
    ).execute()
```

### Sync Algorithm

The sync algorithm uses `external_id` as the stable key for matching records across sources:

```
For each entity type:
  1. Load all rows from Sheets tab → index by external_id
  2. Load all records from SQLite → index by external_id

  For each external_id in the union of both sets:
    - In Sheets only → INSERT into SQLite
    - In SQLite only → APPEND to Sheets
    - In both, Sheets updated after last_sync → UPDATE SQLite
    - In both, SQLite updated after last_sync → UPDATE Sheets
    - In both, both updated after last_sync → CONFLICT (record, do not auto-resolve)
    - In both, neither updated → NO-OP
```

### Conflict Handling

Conflicts are stored in a `sync_conflicts` table (or as a list returned in the sync response). They are not auto-resolved.

```python
def record_conflict(db: Session, entity_type: str, external_id: str, 
                    sheets_value: dict, db_value: dict) -> None:
    # Store the conflict for user resolution
    conflict = SyncConflict(
        entity_type=entity_type,
        external_id=external_id,
        sheets_snapshot=json.dumps(sheets_value),
        db_snapshot=json.dumps(db_value),
        detected_at=datetime.utcnow()
    )
    db.add(conflict)
```

### Idempotency

Idempotency is enforced by:
1. Using `external_id` as the unique key (not the Sheets row number).
2. Checking for existing records before inserting.
3. Only updating `last_sync_at` when the sync completes successfully.
4. Using the `last_sync_at` timestamp to determine what has changed since the last sync.

## Implementation Guidelines

1. The sync function must return a report: `{created: int, updated: int, conflicts: list}`.
2. The sync must be atomic per entity type. If Companies sync fails, do not proceed to Contacts.
3. The sync endpoint is `POST /api/v1/sync/sheets`. It is user-triggered, not scheduled.
4. The conflict resolution endpoint is `POST /api/v1/sync/resolve-conflict`.
5. Write an audit log entry for the sync completion and for each conflict detected.

## Common Mistakes

- Using Sheets row index as the identifier (rows can move). → Always use `external_id`.
- Not handling the case where a tab is empty (no rows or header only). → Handle empty `values` in API response.
- Auto-resolving conflicts. → Never. Surface them to the user.
- Running sync automatically on a timer. → Sync is manual only.
- Not wrapping Sheets API calls in try/except. → Google API throws `HttpError` on failures.

## Security Considerations

- The credentials JSON file must be stored outside the repository directory.
- File system permissions must restrict the credentials file to the current user.
- The path to the credentials file comes from an environment variable, not from source code.
- Do not log spreadsheet IDs, sheet names, or row content at DEBUG level.

## Testing Requirements

- Mock the Google Sheets API client in all tests (do not make real API calls in tests).
- Test each sync scenario independently:
  - New in Sheets only → inserted in DB.
  - New in DB only → appended to Sheets.
  - Changed in Sheets only → updated in DB.
  - Changed in DB only → updated in Sheets.
  - Changed in both → conflict recorded.
  - No changes → zero operations.
- Test idempotency: run sync twice, verify no duplicates.

## Project-Specific Constraints

- Sync is manually triggered only. No automatic sync schedule.
- The spreadsheet ID comes from `GOOGLE_SHEETS_ID` environment variable.
- Outreach status (sent, replied, bounced) is exported to Sheets but only importable from Sheets for read-only display (the system owns outreach state).
- Contacts marked as `suppressed` must have suppression reflected in the Sheets export.
