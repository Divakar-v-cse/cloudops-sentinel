# Demo assets

| File | Purpose |
| --- | --- |
| `sample-logs.json` | Ready-to-post log batch that produces three distinct error fingerprints (OOM, timeout, DB pool) |
| `../docs/demo-script.md` | Shot-by-shot recording script with narration and recording instructions |
| `seed-demo.sh` | One-shot script: logs in, injects a spike, runs a scan, opens an incident |

## Run the demo data injection

```bash
# with the API running on :8000
bash demo/seed-demo.sh
# or against another port / account
BASE_URL=http://127.0.0.1:8010 EMAIL=engineer@cloudops.local PASSWORD='...' bash demo/seed-demo.sh
```

The script is idempotent in the sense that it always creates a *new* log batch and incident; delete rows from
the UI or reset the database if you want a pristine state.

## Post the logs manually

```bash
curl -X POST http://127.0.0.1:8000/api/v1/logs \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d @demo/sample-logs.json
```
