"""Deterministic QMO calculations. Do not let the LLM invent R/Y/G thresholds."""
def metric_facts(evidence):
    findings = []
    for e in evidence:
        if e["kind"] != "metric":
            continue
        row = e["payload"]
        value, metric = row["value"], row["metric"]
        status = "No Data" if value is None else row["status"]
        if value == 0 and metric in ("Current Release Defects", "Functional Automation Failure Rate"):
            status = "Green"
        findings.append({"type": "metric", "metric": metric, "period": row["period"],
            "value": value, "unit": row["unit"], "status": status,
            "refreshed_at": row["refreshed_at"], "evidence_ids": [e["id"]]})
    return findings

def compare_periods(evidence, scope):
    previous = scope.get("previous_period")
    if not previous:
        return [], ["No previous period supplied; decline or improvement cannot be established."]
    current_rows, old_rows = {}, {}
    for e in evidence:
        if e["kind"] != "metric":
            continue
        r = e["payload"]
        if r["period"] == scope["period"]:
            current_rows[r["metric"]] = e
        elif r["period"] == previous:
            old_rows[r["metric"]] = e
    findings, limitations = [], []
    for name, current in current_rows.items():
        old = old_rows.get(name)
        c = current["payload"]
        if not old or c["value"] is None or old["payload"]["value"] is None:
            limitations.append(f"No comparable non-null baseline for {name}.")
            continue
        b = old["payload"]
        if b["unit"] != c["unit"]:
            limitations.append(f"Incompatible units for {name}.")
            continue
        findings.append({"type": "trend", "metric": name,
            "period": c["period"], "previous_period": b["period"],
            "value": c["value"], "previous_value": b["value"],
            "delta": c["value"] - b["value"],
            "delta_unit": "percentage points" if c["unit"] == "percent" else c["unit"],
            "evidence_ids": [old["id"], current["id"]]})
    if not current_rows:
        limitations.append("No current metrics available for a comparison.")
    return findings, limitations

def validation_errors(report, evidence):
    ids = {e["id"] for e in evidence}
    errors = []
    for claim in report.observations + report.recommendations:
        if not claim.evidence_ids or not set(claim.evidence_ids) <= ids:
            errors.append("Claim lacks retrieved evidence references.")
        # Keep all metric numbers in the deterministic findings field.
        if any(char.isdigit() for char in claim.text):
            errors.append("Numeric claim in generated prose; use authoritative findings.")
    return errors
