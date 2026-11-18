from app.pipeline import run
from app.errors import BusinessError
from app.modules.m8_publish import rules, store

def preview(text):
    """独立计算：展开可借目录并给出内容摘要，只演算不落库。"""
    result = run(text)
    items = rules.entries(result)
    conflicts = len(result["binding_conflicts"]) + len(result["identity_conflicts"])
    return {"module": 8, "blocked": result["blocked"], "digest": rules.digest(items),
            "report": {"rows": items, "metrics": {"可借条目": len(items), "隔离": len(result["quarantine"]), "冲突": conflicts}},
            "quarantine": result["quarantine"], "balance": result["balance"]}

def publish(text):
    """发布：阻断批次与空目录拒绝写入；新批次生成新版本并原子切换；同批次复用旧版本。"""
    result = run(text)
    if result["blocked"]:
        raise BusinessError("BLOCKED", "存在阻断项，请先修正数据", 409)
    items = rules.entries(result)
    if not items:
        raise BusinessError("EMPTY_CATALOG", "批次无可借条目，不予发布")
    outcome = store.publish(items, rules.digest(items))
    active = store.current()
    return {**outcome, "entries": len(items), "digest": rules.digest(items), "current": active["version"]}

def track():
    """追查视图：旧借阅单固定出借时版本与册次快照，与当前目录逐单核对。"""
    active = store.current()
    index = {(e["issn"], e["year"], e["issue"], e["copy"]): e for e in active["entries"]} if active else {}
    out = []
    for slip in store.loans():
        now = index.get((slip["issn"], slip["year"], slip["issue"], slip["copy"]))
        if active is None:
            state = "无当前版本"
        elif now is None:
            state = "已撤架"
        elif now["binding"] != slip["binding"]:
            state = "装订变更"
        else:
            state = "在架一致"
        out.append({**slip, "current_version": active["version"] if active else None,
                    "current_binding": now["binding"] if now else None, "check": state,
                    "drift": bool(active) and slip["version"] != active["version"]})
    return out
