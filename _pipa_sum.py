import json, pathlib
p = pathlib.Path("security/reports/pip-audit.json")
if not p.exists() or not p.read_text().strip():
    print("no output file")
else:
    d = json.loads(p.read_text())
    deps = d.get("dependencies", []) if isinstance(d, dict) else d
    vulns = [(x["name"], x["version"], [v["id"] for v in x.get("vulns", [])]) for x in deps if x.get("vulns")]
    print("packages:", len(deps), "vulnerable:", len(vulns))
    for row in vulns: print(row)
