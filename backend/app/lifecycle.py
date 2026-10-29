"""The lifecycle monitor: where each deposit stands, who must act, and when to escalate.

Runs daily (cron / RQ scheduler in production; the "Run monitor" button in the demo). It
  1. sends reminders 90, 60, 30 and 7 days before maturity,
  2. flags matured deposits with no renewal or release request, and escalates them
     to the Regional Officer after 15 days and to the Regulation Bureau after 30,
  3. re-confirms every active deposit with the bank every 90 days, so a deposit closed
     early is caught within a quarter instead of at maturity,
  4. escalates bank confirmations that are past the bank's SLA.
"""
from datetime import date, datetime, timedelta, timezone

from . import audit, banks, config, db, pipeline


def today():
    return date.today()


def maturity(row):
    return date.fromisoformat(row["maturity_date"]) if row.get("maturity_date") else None


def state(row, release=None, on=None):
    on = on or today()
    if row.get("released"):
        return config.RELEASED
    if release and release["state"] != "Discharged":
        return config.RELEASING
    if row.get("replaced_by"):
        return config.RENEWED
    if row.get("verification") == config.DECLARED:
        return config.PENDING
    m = maturity(row)
    if not m:
        return config.PENDING
    days = (m - on).days
    return config.MATURED if days < 0 else config.EXPIRING if days <= 90 else config.ACTIVE


def raise_alert(c, row, kind, level, title, detail, due, key, recipients):
    hit = c.execute("SELECT id FROM alerts WHERE key=?", (key,)).fetchone()
    if hit:
        return 0
    ts = pipeline.now()
    c.execute("INSERT INTO alerts(instrument_id,kind,level,title,detail,due,state,created_at,key) VALUES(?,?,?,?,?,?,?,?,?)",
              (row["id"], kind, level, title, detail, due, "open", ts, key))
    aid = c.execute("SELECT id FROM alerts WHERE key=?", (key,)).fetchone()[0]
    for channel, who in recipients:
        c.execute("INSERT INTO notifications(alert_id,instrument_id,channel,recipient,subject,sent_at) VALUES(?,?,?,?,?,?)",
                  (aid, row["id"], channel, who, title, ts))
    return 1


def run(on=None, actor="monitor", reconfirm_all=False):
    on = on or today()
    rows = db.q("SELECT i.*, n.name AS inst_name, n.email AS inst_email, n.region FROM instruments i "
                "JOIN institutions n ON n.id=i.institution_id WHERE i.selfcheck=0 AND i.released=0 AND i.replaced_by IS NULL")
    rel = {r["instrument_id"]: r for r in db.q("SELECT * FROM releases")}
    made = {"reminders": 0, "matured": 0, "escalations": 0, "reconfirmed": 0, "caught": 0}
    for row in rows:
        if row["id"] in rel:
            continue
        m = maturity(row)
        inst = [("Email", row["inst_email"]), ("SMS", "registered mobile")]
        ro = [("Email", f"ro.{row['region'].lower().replace(' ', '-')}@aicte.sandbox")]
        rb = [("Email", "regulation.bureau@aicte.sandbox")]
        with db.tx() as c:
            if m and row["verification"] != config.DECLARED:
                days = (m - on).days
                due_offsets = [d for d in config.REMIND_BEFORE if 0 <= days <= d]
                if due_offsets:
                    d = min(due_offsets)
                    made["reminders"] += raise_alert(
                        c, row, "maturity", "Reminder", f"FDR matures in {days} days",
                        f"{row['inst_name']}: {row['fdr_no']} ({banks.inr(row['amount'])}) matures on {m}. "
                        "Upload the renewed FDR or apply for release before the due date.",
                        (m + timedelta(days=config.GRACE_DAYS)).isoformat(), f"{row['id']}:remind:{d}", inst)
                if days < 0:
                    made["matured"] += raise_alert(
                        c, row, "matured", "Action due", "Matured: renewal or release not received",
                        f"Matured on {m}. Grace period ends {m + timedelta(days=config.GRACE_DAYS)}.",
                        (m + timedelta(days=config.GRACE_DAYS)).isoformat(), f"{row['id']}:matured", inst)
                if days <= -config.ESCALATE_RO_AFTER:
                    made["escalations"] += raise_alert(
                        c, row, "overdue", "Escalated to Regional Officer", f"Overdue {-days} days: no renewal",
                        f"{row['inst_name']} has not renewed or replaced {row['fdr_no']} since {m}.",
                        on.isoformat(), f"{row['id']}:esc:ro", ro + inst)
                if days <= -config.ESCALATE_RB_AFTER:
                    made["escalations"] += raise_alert(
                        c, row, "overdue", "Escalated to Regulation Bureau", f"Overdue {-days} days: security not in force",
                        f"No valid security deposit for {row['inst_name']} for {-days} days.",
                        on.isoformat(), f"{row['id']}:esc:rb", rb + ro)
            if row["verification"] == config.DISCREPANCY:
                top = c.execute("SELECT title, detail FROM checks WHERE instrument_id=? AND outcome=? AND severity='hard' "
                                "ORDER BY id LIMIT 1", (row["id"], config.DISCREPANCY)).fetchone()
                if top:
                    made["escalations"] += raise_alert(c, row, "discrepancy", "Escalated to Regulation Bureau", top[0],
                                                       top[1], on.isoformat(), f"{row['id']}:disc:{top[0][:40]}", rb + ro)
        # bank confirmation outstanding past the SLA
        pend = db.q("SELECT * FROM confirmations WHERE instrument_id=? AND state='sent'", (row["id"],))
        for p in pend:
            bank = banks.BANKS.get(p["bank_code"], {})
            age = (on - date.fromisoformat(p["created_at"][:10])).days
            if age > bank.get("sla_days", 3):
                with db.tx() as c:
                    made["escalations"] += raise_alert(
                        c, row, "bank_sla", "Escalated to Regional Officer", f"Bank has not confirmed in {age} days",
                        f"{bank.get('name')} was asked on {p['created_at'][:10]} (SLA {bank.get('sla_days')} days).",
                        on.isoformat(), f"{row['id']}:sla:{p['token']}", ro)
        # periodic re-confirmation with the bank (Tier 2 banks)
        bank = banks.bank_for(row["ifsc"])
        last = row["last_confirmed"]
        stale = not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days >= config.RECONFIRM_EVERY
        if row["verification"] == config.CONFIRMED and bank and bank["api"] and (stale or reconfirm_all):
            rec, err = banks.bank_lookup(row["ifsc"], row["fdr_no"])
            if err:
                continue
            made["reconfirmed"] += 1
            doc = db.q1("SELECT id, fields FROM documents WHERE instrument_id=? ORDER BY created_at DESC LIMIT 1", (row["id"],))
            fields = db.unj(doc["fields"], {}) if doc else {}
            diffs = [banks.res("bank_not_found", "Bank no longer has this deposit", config.DISCREPANCY,
                               f"{bank['name']} now finds no deposit {row['fdr_no']}.", 2)] if rec is None else \
                banks.compare(fields, rec, bank["name"])[0]
            stamp = pipeline.now()
            if diffs:
                made["caught"] += 1
                pipeline.save_checks(row["id"], doc["id"] if doc else None, diffs, replace=False)
                with db.tx() as c:
                    c.execute("UPDATE instruments SET verification=?, risk=100, last_confirmed=? WHERE id=?",
                              (config.DISCREPANCY, stamp, row["id"]))
                    raise_alert(c, row, "discrepancy", "Escalated to Regulation Bureau", diffs[0]["title"],
                                diffs[0]["detail"], on.isoformat(), f"{row['id']}:recheck:{diffs[0]['code']}", rb + ro)
                pipeline.event(row["id"], "reconfirm", f"Quarterly bank re-check: {diffs[0]['title'][0].lower()}{diffs[0]['title'][1:]}", actor)
                audit.log(actor, "instrument.reconfirm_failed", row["id"], {"finding": diffs[0]["code"]})
            else:
                with db.tx() as c:
                    c.execute("UPDATE instruments SET last_confirmed=? WHERE id=?", (stamp, row["id"]))
                pipeline.event(row["id"], "reconfirm", f"Quarterly bank re-check: {bank['name']} confirms status "
                                                       f"{rec['status'].lower()}", actor)
    audit.log(actor, "monitor.run", on.isoformat(), made)
    return made
