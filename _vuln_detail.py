import json
d = json.load(open("security/reports/pip-audit.json"))
deps = d.get("dependencies", []) if isinstance(d, dict) else d
for dep in deps:
    if dep.get("vulns"):
        fixes = sorted({fv for v in dep["vulns"] for fv in (v.get("fix_versions") or [])})
        print(dep["name"], dep["version"], "-> fixes:", fixes[:6])
        for v in dep["vulns"][:3]:
            print("   ", v["id"], "|", (v.get("description") or "")[:100].replace("\n"," "))
