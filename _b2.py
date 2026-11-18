import json
d = json.load(open("security/reports/bandit.json"))
tot = d.get("metrics", {}).get("_totals", {})
print("bandit after fix:", {k: tot.get(k) for k in ("loc","SEVERITY.HIGH","SEVERITY.MEDIUM","SEVERITY.LOW")}, "results:", len(d["results"]))
