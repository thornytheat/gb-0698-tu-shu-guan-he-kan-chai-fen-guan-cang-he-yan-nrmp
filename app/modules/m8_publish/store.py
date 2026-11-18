import json, hashlib
from datetime import datetime, timezone
from app.store import connect
from app.errors import BusinessError

def _ensure(db):
    db.execute("CREATE TABLE IF NOT EXISTS catalog_versions (version INTEGER PRIMARY KEY, digest TEXT NOT NULL UNIQUE, entries TEXT NOT NULL, created TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS catalog_current (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS loan_slips (id TEXT PRIMARY KEY, version INTEGER NOT NULL, issn TEXT NOT NULL, title TEXT NOT NULL, year TEXT NOT NULL, issue TEXT NOT NULL, copy TEXT NOT NULL, binding TEXT NOT NULL, partner TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL, returned TEXT)")

def _now():
    return datetime.now(timezone.utc).isoformat()

def _switch(db, version):
    db.execute("INSERT INTO catalog_current(id,version) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version", (version,))

def publish(items, digest):
    """新批次写入新版本并在同一事务内原子切换为当前来源；同摘要批次复用旧版本不新增；
    写入或切换任一失败整体回滚，当前来源保留上一版。"""
    with connect() as db:
        _ensure(db)
        row = db.execute("SELECT version,created FROM catalog_versions WHERE digest=?", (digest,)).fetchone()
        if row is not None:
            return {"version": row["version"], "reused": True, "created": row["created"]}
        version = db.execute("SELECT COALESCE(MAX(version),0)+1 AS v FROM catalog_versions").fetchone()["v"]
        created = _now()
        db.execute("INSERT INTO catalog_versions(version,digest,entries,created) VALUES(?,?,?,?)", (version, digest, json.dumps(items, ensure_ascii=False), created))
        _switch(db, version)
    return {"version": version, "reused": False, "created": created}

def current():
    with connect() as db:
        _ensure(db)
        row = db.execute("SELECT v.version,v.digest,v.entries,v.created FROM catalog_current c JOIN catalog_versions v ON v.version=c.version WHERE c.id=1").fetchone()
    if row is None:
        return None
    return {"version": row["version"], "digest": row["digest"], "entries": json.loads(row["entries"]), "created": row["created"]}

def versions():
    with connect() as db:
        _ensure(db)
        marker = db.execute("SELECT version FROM catalog_current WHERE id=1").fetchone()
        active = marker["version"] if marker else None
        rows = db.execute("SELECT version,digest,entries,created FROM catalog_versions ORDER BY version DESC").fetchall()
    return [{"version": r["version"], "digest": r["digest"], "entries": len(json.loads(r["entries"])), "created": r["created"], "current": r["version"] == active} for r in rows]

def lend(issn, year, issue, copy, partner):
    """出借：以当前版本为准校验期次册次可借，借阅单固定该版本与出借时装订快照。"""
    with connect() as db:
        _ensure(db)
        row = db.execute("SELECT v.version,v.entries FROM catalog_current c JOIN catalog_versions v ON v.version=c.version WHERE c.id=1").fetchone()
        if row is None:
            raise BusinessError("NO_CATALOG", "尚未发布可借目录", 409)
        items = json.loads(row["entries"])
        entry = next((e for e in items if e["issn"] == issn and e["year"] == year and e["issue"] == issue and e["copy"] == copy), None)
        if entry is None:
            raise BusinessError("NOT_LENDABLE", "该期次册次在当前目录不可借", 409)
        dup = db.execute("SELECT 1 FROM loan_slips WHERE issn=? AND year=? AND issue=? AND copy=? AND status='出借中'", (issn, year, issue, copy)).fetchone()
        if dup:
            raise BusinessError("ON_LOAN", "该册已在借，请先归还", 409)
        created = _now()
        ident = hashlib.sha256("|".join([str(row["version"]), issn, year, issue, copy, partner, created]).encode()).hexdigest()[:16]
        db.execute("INSERT INTO loan_slips(id,version,issn,title,year,issue,copy,binding,partner,status,created) VALUES(?,?,?,?,?,?,?,?,?,'出借中',?)",
                   (ident, row["version"], issn, entry["title"], year, issue, copy, entry["binding"], partner, created))
    return {"id": ident, "version": row["version"], "created": created}

def loans():
    with connect() as db:
        _ensure(db)
        rows = db.execute("SELECT * FROM loan_slips ORDER BY created DESC, id DESC").fetchall()
    return [dict(r) for r in rows]

def return_loan(ident):
    with connect() as db:
        _ensure(db)
        row = db.execute("SELECT status FROM loan_slips WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise BusinessError("NOT_FOUND", "借阅单不存在", 404)
        if row["status"] != "出借中":
            raise BusinessError("LOAN_STATE", "借阅单已归还", 409)
        db.execute("UPDATE loan_slips SET status='已归还', returned=? WHERE id=?", (_now(), ident))
    return {"id": ident, "status": "已归还"}
