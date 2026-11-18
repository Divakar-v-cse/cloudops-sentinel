# Bandit: use the default test profile (explicit short IDs like "B5" are invalid)
from pathlib import Path
p = Path("security/.bandit")
t = p.read_text(encoding="utf-8")
start = t.index("tests:")
end = t.index("# B105")
p.write_text(t[:start] + t[end:], encoding="utf-8")
print(p.read_text(encoding="utf-8"))
