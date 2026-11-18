import hashlib, json
from app.config import RULE_VERSION

def _issue_key(issue):
    return (0, int(issue)) if str(issue).isdigit() else (1, str(issue))

def entries(result):
    """从流水线结果展开当前可借目录：仅在馆(held)记录可借，一期一册一条。"""
    out = []
    for row in result["held"]:
        for issue in row["issues"]:
            out.append({"issn": row["journal_key"], "title": row["canonical"], "year": row["year"],
                        "volume": row["volume"], "issue": issue, "copy": row["copy"], "binding": row["binding"]})
    out.sort(key=lambda e: (e["issn"], e["year"], _issue_key(e["issue"]), e["copy"]))
    return out

def digest(items):
    """目录内容摘要：同一批次内容得到同一摘要，重跑不新增版本。"""
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256((RULE_VERSION + "\n" + payload).encode()).hexdigest()
