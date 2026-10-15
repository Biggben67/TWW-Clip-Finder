"""One-shot Dolphin-side bridge for bounded, reversible native diagnostics."""
import json
from pathlib import Path

import dolphin_dtm as dtm


def apply(request, backup):
    saved = []
    for entry in request["rows"]:
        row, controller = entry["row"], request["controller"]
        original = dtm.get_gc(row, controller)
        if original is None:
            raise RuntimeError(f"runtime DTM row {row} is unavailable")
        saved.append(dict(row=row, state=original))
    backup.write_text(json.dumps(dict(controller=request["controller"], rows=saved)))
    try:
        for entry in request["rows"]:
            if not dtm.set_gc(entry["row"], request["controller"], entry["state"]):
                raise RuntimeError(f"cannot edit runtime DTM row {entry['row']}")
            actual = dtm.get_gc(entry["row"], request["controller"])
            if any(actual[key] != value for key, value in entry["state"].items()):
                raise RuntimeError(f"runtime DTM readback differs at row {entry['row']}")
    except Exception:
        restore(backup)
        raise


def restore(backup):
    saved = json.loads(backup.read_text())
    for entry in saved["rows"]:
        if not dtm.set_gc(entry["row"], saved["controller"], entry["state"]):
            raise RuntimeError(f"cannot restore runtime DTM row {entry['row']}")
        if dtm.get_gc(entry["row"], saved["controller"]) != entry["state"]:
            raise RuntimeError(f"runtime DTM restoration differs at row {entry['row']}")


base = Path(__file__).with_suffix("")
request = json.loads(base.with_suffix(".json").read_text())
backup = base.with_suffix(".backup.json")
try:
    if request["action"] == "apply":
        apply(request, backup)
    elif request["action"] == "restore":
        restore(backup)
    elif request["action"] == "probe":
        result = dict(ok=True, metadata=dtm.get_metadata(), ports={
            str(port): dtm.get_gc(request["row"], port) for port in range(4)})
    else:
        raise RuntimeError("unknown diagnostic action")
    if request["action"] != "probe":
        result = dict(ok=True)
except Exception as error:
    result = dict(ok=False, error=str(error))
base.with_suffix(".result.json").write_text(json.dumps(result))
