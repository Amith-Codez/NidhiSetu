import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock, ExternalLink, RefreshCw, Undo2, Zap } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, Check, fmtDate, inr, post } from "../api";
import { Days, ENGINE, OUTCOME_ICON, Pill, Section } from "../ui";

const ORDER = ["CONFIRM", "CHECK", "DETECT", "READ"];
const BAD = "Discrepancy found";

function nextStep(d: any) {
  const hard = d.checks.find((c: Check) => c.outcome === BAD && c.severity === "hard");
  if (d.verification === BAD) return { tone: "bad", icon: <AlertTriangle size={17} />, t: "The bank's record and the receipt disagree",
    p: `${hard ? hard.title + ". " : ""}Do not treat this deposit as security. Ask the institution to explain and inform the bank's branch.` };
  if (d.state === "Pending verification") return { tone: "", icon: <Clock size={17} color="var(--p-600)" />, t: "Waiting for the bank",
    p: "Only the institution's word so far. The branch has been sent a signed confirmation link; no answer by the due date escalates." };
  if (d.state === "Matured") return { tone: "bad", icon: <AlertTriangle size={17} />, t: "Matured: renewal or release overdue",
    p: "The security is no longer in force. Ask for a renewed FDR, or process a release if the conditions are met." };
  if (d.state === "Expiring") return { tone: "", icon: <Clock size={17} color="var(--exp)" />, t: "Renewal due soon",
    p: `Matures in ${d.days} days. The institution has been reminded; the renewed FDR will be confirmed with the bank on upload.` };
  if (d.state === "Release in progress") return { tone: "", icon: <Undo2 size={17} color="var(--p-600)" />, t: `Release: ${d.release.state.toLowerCase()}`,
    p: "Follow the request in Release requests. Each step needs a different official." };
  if (d.state === "Renewed") return { tone: "", icon: <CheckCircle2 size={17} color="var(--ok)" />, t: `Replaced by ${d.replaced_by}`, p: "Kept for the record; the replacement is the live security." };
  if (d.state === "Released") return { tone: "", icon: <CheckCircle2 size={17} color="var(--ok)" />, t: "Released", p: "Approved, and the bank was asked to remove AICTE's lien." };
  return { tone: "", icon: <CheckCircle2 size={17} color="var(--ok)" />, t: "In force and confirmed by the bank",
    p: `Last confirmed ${fmtDate(d.last_confirmed)} via ${d.channel || "the bank"}. Re-checked automatically every 90 days.` };
}

function Compare({ d }: { d: any }) {
  const p = d.declared || {}, b = d.bank_view;
  const differs = (k: string) => d.checks.some((c: Check) => c.code === `bank_differs_${k}`);
  const rows: [string, string, any, any, boolean][] = [
    ["amount_inr", "Amount", inr(p.amount_inr), b ? inr(b.amount_inr) : null, differs("amount_inr")],
    ["deposit_date", "Date of deposit", fmtDate(p.deposit_date), b ? fmtDate(b.deposit_date) : null, differs("deposit_date")],
    ["maturity_date", "Maturity date", fmtDate(p.maturity_date), b ? fmtDate(b.maturity_date) : null, differs("maturity_date")],
    ["depositor", "Depositor", p.depositor, b?.depositor, differs("depositor")],
    ["lien", "Lien for AICTE", p.lien ? "Marked" : "Not shown", b ? (b.lien ? "Marked" : "None") : null, !!b && !b.lien],
    ["status", "Status", "Looks valid on paper", b ? (b.status === "CLOSED" ? "Closed early" : b.status?.toLowerCase()) : null, b?.status === "CLOSED"],
  ];
  const notFound = d.checks.some((c: Check) => c.code === "bank_not_found");
  return (
    <table className="compare">
      <thead><tr><th>Field</th><th>Institution says (receipt)</th><th>Bank confirms</th></tr></thead>
      <tbody>
        {rows.map(([k, label, paper, bank, bad]) => (
          <tr key={k} className={bad ? "bad" : ""}>
            <td className="k">{label}</td><td>{paper ?? "–"}</td>
            <td className="b">{bank ?? <span className="muted">{notFound ? "No record at the bank" : d.verification === "Declared, awaiting bank" ? "Awaiting the branch" : "–"}</span>}</td>
          </tr>
        ))}
        {b && <tr><td className="k">Source</td><td colSpan={2} className="small">{b.source} · {fmtDate(b.ts)}<span className="src">{d.channel}</span></td></tr>}
      </tbody>
    </table>
  );
}

export default function Deposit() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { data: d } = useQuery({ queryKey: ["deposit", id], queryFn: () => api(`/api/instruments/${id}`) });
  const [hot, setHot] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  if (!d) return <div className="page"><div className="empty">Loading deposit…</div></div>;
  const m = d.maturity_date ? Math.round((new Date(d.maturity_date + "T00:00:00").getTime() - Date.now()) / 864e5) : null;
  const ns = nextStep({ ...d, days: m });
  const findings: Check[] = [...d.checks].sort((a: Check, b: Check) => ORDER.indexOf(a.engine) - ORDER.indexOf(b.engine)).filter((c: Check) => c.outcome === BAD || c.outcome === "flag" || c.severity === "info"
    || ["bank_confirmed", "sig_valid", "qr_trusted", "t3_yes"].includes(c.code));
  const passed = d.checks.length - findings.length;
  // One box per region: findings about the same line share a number instead of stacking badges
  const boxes: { bbox: number[]; ids: number[]; soft: boolean }[] = [];
  findings.filter((c) => c.evidence?.bbox && (c.evidence.page ?? 0) === 0).forEach((c) => {
    const b = c.evidence.bbox as number[];
    const g = boxes.find((x) => Math.min(x.bbox[3], b[3]) - Math.max(x.bbox[1], b[1]) > 0.5 * Math.min(x.bbox[3] - x.bbox[1], b[3] - b[1])
      && Math.min(x.bbox[2], b[2]) > Math.max(x.bbox[0], b[0]));
    if (g) { g.ids.push(c.id); g.soft = g.soft && c.severity === "soft"; g.bbox = [Math.min(g.bbox[0], b[0]), g.bbox[1], Math.max(g.bbox[2], b[2]), g.bbox[3]]; }
    else boxes.push({ bbox: [...b], ids: [c.id], soft: c.severity === "soft" });
  });
  const numOf = (id: number) => boxes.findIndex((g) => g.ids.includes(id));
  const hotBox = hot == null ? -1 : numOf(hot);
  const W = d.document?.size?.[0] || 595, H = d.document?.size?.[1] || 842;
  const isDemo = (d.story || "").includes("live demo");

  async function act(kind: string) {
    setBusy(kind); setMsg("");
    try {
      if (kind === "recheck") { const r = await post(`/api/instruments/${id}/reverify`); setMsg(`Re-checked: ${r.verification.toLowerCase()} in ${r.ms} ms.`); }
      if (kind === "release") { await post(`/api/instruments/${id}/release`, { grounds: "term_completed" }); setMsg("Release request opened; see Release requests."); }
      if (kind === "close") { await post(`/api/demo/bank-closes/${id}`); setMsg("The sandbox bank now shows this deposit closed. Run the monitor (Overview) or re-check to catch it."); }
    } catch (e: any) { setMsg(e.message); }
    setBusy("");
    qc.invalidateQueries();
  }

  return (
    <div className="page">
      <Link className="back" to="/deposits"><ArrowLeft size={14} />Deposit register</Link>
      <div className="app-head">
        <div>
          <span className="mono muted">{d.id} · FDR {d.fdr_no || "–"} · {d.bank.name} · {d.ifsc} {d.bank.branch ? `(${d.bank.branch})` : ""}</span>
          <h1>{d.institution?.name}</h1>
          <div className="meta"><span>{inr(d.amount)} {d.required_amount ? `of ${inr(d.required_amount)} required` : ""}</span>
            <span>Deposited {fmtDate(d.deposit_date)}</span><span>Matures {fmtDate(d.maturity_date)} (<Days d={m} />)</span>
            <span>{d.institution?.region} region</span></div>
        </div>
        <div className="side-r" style={{ flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
          <Pill s={d.state} lg /><Pill s={d.verification} lg />
        </div>
      </div>

      <div className={`next ${ns.tone}`} role="status">
        <span className="ic">{ns.icon}</span>
        <div><b>{ns.t}</b><p>{ns.p}{d.story ? ` Case: ${d.story}.` : ""}</p></div>
        <div className="acts">
          {isDemo && <button className="btn" disabled={!!busy} onClick={() => act("close")}><Zap size={14} />Demo: bank closes it</button>}
          {d.bank.api && <button className={`btn ${d.verification === BAD ? "" : ""}`} disabled={!!busy} onClick={() => act("recheck")}>
            <RefreshCw size={14} />{busy === "recheck" ? "Asking the bank…" : "Re-check with bank"}</button>}
          {(d.state === "Matured" || d.state === "Active") && d.verification === "Confirmed by bank" && !d.release &&
            <button className={`btn ${d.state === "Matured" ? "primary" : ""}`} disabled={!!busy} onClick={() => act("release")}><Undo2 size={14} />Start release</button>}
          {d.confirmations?.some((c: any) => c.state === "sent") &&
            <Link className="btn" to={`/confirm/${d.confirmations.find((c: any) => c.state === "sent").token}`}><ExternalLink size={14} />Branch's link</Link>}
        </div>
      </div>
      {msg && <p className="small" role="status" style={{ margin: 0 }}>{msg}</p>}

      <div className="workbench" style={{ gridTemplateColumns: "minmax(0,1fr) 440px" }}>
        <div>
          {d.document?.renders?.[0] ? (
            <div className="viewer" aria-label="Receipt with evidence marked">
              <img src={`/api/renders/${d.document.renders[0].name}`} alt="Fixed deposit receipt as submitted" />
              {boxes.map((g, k) => {
                const [x0, y0, x1, y1] = g.bbox;
                return <span key={k} className={`mark ${g.soft ? "soft" : ""} ${hotBox === k ? "hot" : ""}`}
                  style={{ left: `${(x0 / W) * 100}%`, top: `${(y0 / H) * 100}%`, width: `${((x1 - x0) / W) * 100}%`, height: `${((y1 - y0) / H) * 100}%` }}
                  onMouseEnter={() => setHot(g.ids[0])} onMouseLeave={() => setHot(null)}><span className="n">{k + 1}</span></span>;
              })}
            </div>
          ) : <div className="empty">No receipt on file.</div>}
          {d.document && <div className="doc-meta"><span className="mono">SHA-256 {d.document.sha256.slice(0, 16)}…</span>
            <span>Uploaded {fmtDate(d.document.created_at)}</span><a href={`/api/documents/${d.document.id}/file`} target="_blank" rel="noreferrer">Original file</a></div>}
        </div>
        <div className="evi">
          <div className="evi-h"><h2>Institution says, bank confirms</h2></div>
          <Compare d={d} />
          <div className="grp">Findings</div>
          {ORDER.map((eng) => {
            const list = findings.filter((c) => c.engine === eng);
            if (!list.length) return null;
            return (
              <div key={eng}>
                <div className="grp">{ENGINE[eng]?.icon} {ENGINE[eng]?.label} · {ENGINE[eng]?.blurb}</div>
                {list.map((c) => {
                  const n = numOf(c.id);
                  return (
                    <div key={c.id} className={`check ${n >= 0 && n === hotBox ? "hot" : ""}`} onMouseEnter={() => setHot(c.id)} onMouseLeave={() => setHot(null)}>
                      <span className={`i ${OUTCOME_ICON(c.outcome, c.severity)}`}>{n >= 0 ? n + 1 : c.outcome === "Confirmed by bank" ? "✓" : "!"}</span>
                      <div><div className="t">{c.title}</div><div className="d">{c.detail}</div>
                        <div className="m">{c.evidence?.tier ? <span className="tag">Tier {c.evidence.tier}</span> : null}
                          <span className="tag">{c.severity === "hard" ? "Hard fact" : c.severity === "soft" ? `Warning sign, +${c.weight} risk` : "Information"}</span>
                          {c.rule_ref && <span className="tag">{c.rule_ref}</span>}</div></div>
                    </div>
                  );
                })}
              </div>
            );
          })}
          <p className="small muted" style={{ margin: "8px 0 0" }}>{passed} other checks passed. Risk {d.risk ?? 0} of 100.</p>
        </div>
      </div>

      <div className="grid g2">
        <Section title="History" sub="every action, newest first">
          <div className="timeline">
            {d.events.map((e: any) => (
              <div key={e.id} className={`t ${/discrep|closed|denied|no longer/i.test(e.text) ? "bad" : /confirm|renewed|released/i.test(e.text) ? "ok" : ""}`}>
                <i /><span>{e.text}<span className="small muted"> · {e.actor}</span></span><span className="w">{fmtDate(e.ts)}</span>
              </div>
            ))}
          </div>
          {d.history?.length > 0 && <p className="small muted">Replaces {d.history.map((h: any) => <Link key={h.id} to={`/deposit/${h.id}`}>{h.id} </Link>)}</p>}
          {d.replaced_by && <p className="small">Replaced by <Link to={`/deposit/${d.replaced_by}`}>{d.replaced_by}</Link></p>}
        </Section>
        <Section title="Alerts on this deposit" sub={d.alerts.length ? `${d.alerts.length} raised` : "none raised"}>
          <div className="feed">
            {d.alerts.map((a: any) => (
              <div key={a.id} className="ev"><span><span className={`lvl ${a.level.includes("Bureau") ? "rb" : a.level.includes("Regional") ? "ro" : "due"}`}>{a.level}</span> {a.title}
                <div className="small muted">{a.detail}</div></span><span className="h">{a.state}</span></div>
            ))}
            {!d.alerts.length && <div className="empty" style={{ padding: 16 }}>No reminders or escalations yet.</div>}
          </div>
          {d.release && <p className="small">Release request <Link to="/releases">{d.release.id}</Link>: {d.release.state.toLowerCase()}.</p>}
        </Section>
      </div>
    </div>
  );
}
