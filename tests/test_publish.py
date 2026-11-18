from pathlib import Path
import pytest
from app.errors import BusinessError
from app.modules.m8_publish import service, store, exporter, rules

SAMPLES = Path(__file__).parent.parent / "sample_data"

def base_text():
    return (SAMPLES / "publishable.csv").read_text(encoding="utf-8-sig")

def update_text():
    return (SAMPLES / "annual-update.csv").read_text(encoding="utf-8-sig")

HEADER = "record_id,title,issn,year,volume,issue,copy,binding,status,note"
CONFLICT = "\n".join([HEADER,
    "A01,数据工程月刊,1000-0001,2026,001,1,01,B01,held,期刊",
    "A02,数据工程月刊,1000-0001,2026,001,1,01,B02,held,期刊"])
EMPTY = "\n".join([HEADER,
    "S01,数据工程月刊,1000-0001,2026,001,12,01,,suspended,停刊"])

@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr("app.store.DATA_DIR", tmp_path)
    return tmp_path

def test_publish_new_batch_switches_current(isolated):
    first = service.publish(base_text())
    assert first["version"] == 1 and first["reused"] is False and first["current"] == 1
    second = service.publish(update_text())
    assert second["version"] == 2 and second["reused"] is False and second["current"] == 2
    assert [v["version"] for v in store.versions()] == [2, 1]
    assert store.current()["digest"] == second["digest"]

def test_publish_same_batch_reuses_version(isolated):
    a = service.publish(base_text())
    b = service.publish(base_text())
    assert b["reused"] is True and b["version"] == a["version"]
    assert len(store.versions()) == 1 and store.current()["version"] == a["version"]

def test_publish_blocked_batch_keeps_previous(isolated):
    service.publish(base_text())
    with pytest.raises(BusinessError, match="阻断项"):
        service.publish(CONFLICT)
    assert store.current()["version"] == 1 and len(store.versions()) == 1

def test_publish_switch_failure_keeps_previous(isolated, monkeypatch):
    service.publish(base_text())
    def boom(db, version):
        raise RuntimeError("disk full")
    monkeypatch.setattr("app.modules.m8_publish.store._switch", boom)
    with pytest.raises(RuntimeError):
        service.publish(update_text())
    assert store.current()["version"] == 1 and len(store.versions()) == 1

def test_publish_empty_catalog_rejected(isolated):
    with pytest.raises(BusinessError, match="无可借条目"):
        service.publish(EMPTY)
    assert store.current() is None and store.versions() == []

def test_catalog_follows_latest_physical(isolated):
    service.publish(base_text())
    assert any(e["issue"] == "4" for e in store.current()["entries"])
    service.publish(update_text())
    entries = store.current()["entries"]
    assert not any(e["issue"] == "4" and e["year"] == "2026" and e["issn"] == "1000-0001" for e in entries)
    assert any(e["year"] == "2027" for e in entries)

def test_loan_pins_original_version(isolated):
    service.publish(base_text())
    slip = store.lend("1000-0001", "2026", "4", "01", "省馆")
    assert slip["version"] == 1
    service.publish(update_text())
    [view] = [s for s in service.track() if s["id"] == slip["id"]]
    assert view["version"] == 1 and view["current_version"] == 2 and view["drift"] is True
    assert view["binding"] == "B02" and view["check"] == "已撤架"

def test_loan_binding_change_detected(isolated):
    service.publish(base_text())
    slip = store.lend("1000-0001", "2026", "7", "01", "市馆")
    service.publish(update_text())
    [view] = [s for s in service.track() if s["id"] == slip["id"]]
    assert view["check"] == "装订变更" and view["binding"] == "B03" and view["current_binding"] == "B03R"

def test_loan_stable_copy_stays_consistent(isolated):
    service.publish(base_text())
    slip = store.lend("1000-0002", "2026", "3", "01", "市馆")
    service.publish(update_text())
    [view] = [s for s in service.track() if s["id"] == slip["id"]]
    assert view["check"] == "在架一致" and view["current_binding"] == "B11"

def test_loan_requires_current_catalog(isolated):
    service.publish(base_text())
    service.publish(update_text())
    with pytest.raises(BusinessError, match="不可借"):
        store.lend("1000-0001", "2026", "4", "01", "省馆")
    ok = store.lend("1000-0001", "2026", "1", "01", "省馆")
    assert ok["version"] == 2

def test_loan_without_catalog_rejected(isolated):
    with pytest.raises(BusinessError, match="尚未发布"):
        store.lend("1000-0001", "2026", "1", "01", "省馆")

def test_loan_duplicate_active_rejected_then_return(isolated):
    service.publish(base_text())
    first = store.lend("1000-0001", "2026", "1", "01", "省馆")
    with pytest.raises(BusinessError, match="已在借"):
        store.lend("1000-0001", "2026", "1", "01", "市馆")
    store.return_loan(first["id"])
    again = store.lend("1000-0001", "2026", "1", "01", "市馆")
    assert again["id"] != first["id"]

def test_return_unknown_or_returned_loan(isolated):
    with pytest.raises(BusinessError, match="不存在"):
        store.return_loan("nope")
    service.publish(base_text())
    slip = store.lend("1000-0001", "2026", "1", "01", "省馆")
    store.return_loan(slip["id"])
    with pytest.raises(BusinessError, match="已归还"):
        store.return_loan(slip["id"])

def test_export_shows_current_and_pinned(isolated):
    service.publish(base_text())
    store.lend("1000-0001", "2026", "4", "01", "省馆")
    service.publish(update_text())
    text = exporter.evidence_csv(store.current(), store.versions(), service.track())
    assert "catalog" in text and "loan" in text and "已撤架" in text
    assert store.current()["digest"] in text
    assert "B02" in text and "省馆" in text

def test_preview_does_not_persist(isolated):
    out = service.preview(base_text())
    assert out["report"]["metrics"]["可借条目"] == 23
    assert out["blocked"] is False
    assert store.versions() == [] and store.current() is None

def test_rules_digest_stable_across_row_order(isolated):
    shuffled = "\n".join([HEADER,
        "P007,数据工程,1000-0002,2026,001,7-12,01,B12,held,期刊",
        "P001,数据工程月刊,1000-0001,2026,001,1-3,01,B01,held,期刊"])
    from app.pipeline import run
    assert rules.digest(rules.entries(run(shuffled))) == rules.digest(rules.entries(run("\n".join([HEADER,
        "P001,数据工程月刊,1000-0001,2026,001,1-3,01,B01,held,期刊",
        "P007,数据工程,1000-0002,2026,001,7-12,01,B12,held,期刊"]))))

def test_module8_page_and_api(isolated):
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    assert client.post("/api/8/publish", json={"text": base_text()}).status_code == 200
    reply = client.post("/api/8/loans", json={"issn": "1000-0001", "year": "2026", "issue": "4", "copy": "01", "partner": "省馆"})
    assert reply.status_code == 200 and reply.json()["version"] == 1
    assert client.post("/api/8/publish", json={"text": update_text()}).status_code == 200
    loans = client.get("/api/8/loans").json()
    assert loans[0]["check"] == "已撤架" and loans[0]["version"] == 1 and loans[0]["current_version"] == 2
    assert client.get("/api/8/catalog").json()["version"] == 2
    assert len(client.get("/api/8/versions").json()) == 2
    page = client.get("/module/8")
    assert page.status_code == 200 and "跨馆借阅单" in page.text and "当前可借目录" in page.text
    export = client.get("/api/8/export")
    assert export.status_code == 200 and "已撤架" in export.text and "catalog" in export.text
    gone = client.post("/api/8/loans", json={"issn": "1000-0001", "year": "2026", "issue": "4", "copy": "01", "partner": "市馆"})
    assert gone.status_code == 409
