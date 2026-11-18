import json
d = json.load(open("security/reports/bandit.json"))
print("metrics:", json.dumps(d.get("metrics", {}).get("_totals", {})))
for r in d.get("results", []):
    print(f'{r["issue_severity"]:8} {r["test_id"]:6} {r["filename"]}:{r["line_number"]} {r["issue_text"][:90]}')
