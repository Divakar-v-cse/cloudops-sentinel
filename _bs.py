import json
d = json.load(open("security/reports/bandit.json"))
tot = d.get("metrics", {}).get("_totals", {})
print("totals:", {k: tot.get(k) for k in ("loc","SEVERITY.HIGH","SEVERITY.MEDIUM","SEVERITY.LOW")})
for r in d.get("results", []):
    print(f'{r["issue_severity"]:8} {r["test_id"]:6} {r["filename"].split("backend")[-1]}:{r["line_number"]} {r["issue_text"][:80]}')
