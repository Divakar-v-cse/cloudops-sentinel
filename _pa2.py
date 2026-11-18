import json
d = json.load(open("security/reports/pip-audit.json"))
deps = d.get("dependencies", []) if isinstance(d, dict) else d
vulns = [(x["name"], x["version"], [v["id"] for v in x.get("vulns", [])]) for x in deps if x.get("vulns")]
print("packages:", len(deps), "| vulnerable:", len(vulns))
for v in vulns: print(v)
