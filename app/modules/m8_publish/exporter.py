import csv, io, json

def evidence_csv(current, versions, loans):
    """证据导出：当前馆藏目录与旧借阅单引用同表核对，可按出借版本追查。"""
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["kind", "version", "digest", "key", "state", "evidence"])
    w.writerow(["manifest", current["version"] if current else "", current["digest"] if current else "", "", "",
                json.dumps({"版本数": len(versions), "借阅单": len(loans)}, ensure_ascii=False)])
    for v in versions:
        w.writerow(["version", v["version"], v["digest"], "", "当前" if v["current"] else "历史",
                    json.dumps({"条目": v["entries"], "created": v["created"]}, ensure_ascii=False)])
    if current:
        for e in current["entries"]:
            w.writerow(["catalog", current["version"], current["digest"], "|".join([e["issn"], e["year"], e["issue"], e["copy"]]), "可借", json.dumps(e, ensure_ascii=False)])
    for s in loans:
        w.writerow(["loan", s["version"], "", s["id"], s["check"],
                    json.dumps({"刊名": s["title"], "issn": s["issn"], "年": s["year"], "期": s["issue"], "册": s["copy"],
                                "出借时装订": s["binding"], "当前装订": s["current_binding"], "当前版本": s["current_version"],
                                "借阅馆": s["partner"], "状态": s["status"]}, ensure_ascii=False)])
    return "﻿" + out.getvalue()
