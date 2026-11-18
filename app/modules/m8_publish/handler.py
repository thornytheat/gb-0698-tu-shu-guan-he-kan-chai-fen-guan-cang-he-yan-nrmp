from pathlib import Path
from fastapi import APIRouter, Body
from fastapi.responses import Response
from app.errors import object_payload, BusinessError
from app.modules.m8_publish import service, exporter, store

router = APIRouter()

def _text(payload):
    payload = object_payload(payload)
    from app.pipeline import sample_text
    text = payload.get("text", sample_text())
    if not isinstance(text, str):
        raise BusinessError("TEXT", "输入须为文本")
    return text

@router.post("/api/8")
def preview(payload: object = Body(default=None)):
    return service.preview(_text(payload))

@router.get("/api/8")
def preview_sample():
    from app.pipeline import sample_text
    return service.preview(sample_text())

@router.post("/api/8/publish")
def publish(payload: object = Body(...)):
    return service.publish(_text(payload))

@router.get("/api/8/catalog")
def catalog():
    active = store.current()
    return active if active else {"version": None, "digest": None, "entries": [], "created": None}

@router.get("/api/8/versions")
def version_list():
    return store.versions()

@router.post("/api/8/loans")
def lend(payload: object = Body(...)):
    payload = object_payload(payload)
    fields = {k: payload.get(k) for k in ("issn", "year", "issue", "copy", "partner")}
    if not all(isinstance(v, str) and v.strip() for v in fields.values()):
        raise BusinessError("LOAN", "刊号、年度、期次、册次、借阅馆均须为文本")
    return store.lend(**{k: v.strip() for k, v in fields.items()})

@router.get("/api/8/loans")
def loan_list():
    return service.track()

@router.post("/api/8/loans/{ident}/return")
def give_back(ident: str):
    return store.return_loan(ident)

@router.get("/api/8/export")
def export():
    return Response(exporter.evidence_csv(store.current(), store.versions(), service.track()),
                    media_type="text/csv", headers={"Content-Disposition": "attachment; filename=publish-evidence.csv"})

@router.get("/api/8/sample")
def samples():
    base = Path(__file__).parent.parent.parent.parent / "sample_data"
    return {"base": (base / "publishable.csv").read_text(encoding="utf-8-sig"),
            "update": (base / "annual-update.csv").read_text(encoding="utf-8-sig")}
