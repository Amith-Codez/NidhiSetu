import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Download, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, inr, post } from "../api";
import { Days, Pill, Section } from "../ui";

const LIFE = [
  { k: "Active", c: "var(--ok)" }, { k: "Expiring", c: "var(--exp)" }, { k: "Matured", c: "var(--bad)" },
  { k: "Pending verification", c: "var(--p-600)" }, { k: "Release in progress", c: "#8C7BD9" },
];

function useGuide(): [boolean, () => void] {
  const [open, setOpen] = useState(() => { try { return localStorage.getItem("ns-guide") !== "closed"; } catch { return true; } });
  const close = () => { setOpen(false); try { localStorage.setItem("ns-guide", "closed"); } catch { /* ignore */ } };
  return [open, close];
}

export default function Overview() {
  const qc = useQueryClient();
  const { data: o } = useQuery({ queryKey: ["overview"], queryFn: () => api("/api/overview") });
  const [guide, closeGuide] = useGuide();
  const [busy, setBusy] = useState(false);
  const [ran, setRan] = useState<any>(null);
  if (!o) return <div className="page"><div className="empty">Loading the deposit register…</div></div>;
  const live = LIFE.reduce((a, l) => a + (o.counts[l.k] || 0), 0) || 1;
  const maxM = Math.max(1, ...o.months.map((m: any) => m.count));
  const conf = o.verification["Confirmed by bank"], disc = o.verification["Discrepancy found"];

  async function runMonitor() {
    setBusy(true);
    setRan(await post("/api/monitor/run", { reconfirm_all: true }));
    setBusy(false);
    qc.invalidateQueries();
  }

  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Security deposits</h1>
          <p>Regulation Bureau · {o.institutions} institutions · {o.in_force} deposits in force worth {inr(o.value, true)}</p></div>
        <div className="actions">
          <a className="btn" href="/api/reports/all.csv"><Download size={14} />Export register</a>
          <button className="btn primary" disabled={busy} onClick={runMonitor}><RefreshCw size={14} />{busy ? "Checking with banks…" : "Run monitor now"}</button>
        </div>
      </div>
      {ran && (
        <div className="next" role="status">
          <span className="ic" style={{ color: "var(--ok)" }}><RefreshCw size={16} /></span>
          <div><b>Monitor finished: {ran.reconfirmed} deposits re-checked with their banks</b>
            <p>{ran.caught ? `${ran.caught} new discrepancy found and escalated. ` : "No new discrepancy. "}
              {ran.reminders + ran.matured + ran.escalations} new alert(s) raised. It also runs every day on its own.</p></div><span />
        </div>
      )}
      {guide && (
        <div className="guide" role="note" aria-label="How NidhiSetu works">
          <div className="step"><span className="n">1</span><div><b>Institution uploads the FDR</b>Receipt or e-FDR, with the bank and IFSC.</div></div>
          <div className="step"><span className="n">2</span><div><b>The bank confirms it</b>Amount, dates and AICTE's lien, from the bank itself.</div></div>
          <div className="step"><span className="n">3</span><div><b>Tracked until release</b>Reminders, quarterly re-checks, renewal and release.</div></div>
          <button className="x" onClick={closeGuide}>Got it</button>
        </div>
      )}
      <div className="stats">
        <div className="stat"><span className="label">Deposits in force</span><span className="value">{o.in_force}</span><span className="foot">{inr(o.value, true)} held as security</span></div>
        <div className="stat"><span className="label">Confirmed by the bank</span><span className="value">{Math.round(100 * conf / Math.max(1, o.in_force))}<small>%</small></span><span className="foot">{conf} deposits · {inr(o.confirmed_value, true)}</span></div>
        <div className="stat"><span className="label">Maturing in 90 days</span><span className="value">{o.counts["Expiring"]}</span><span className="foot">institutions reminded at 90, 60, 30, 7 days</span></div>
        <div className="stat alert"><span className="label">Need action</span><span className="value">{disc + o.counts["Matured"]}</span><span className="foot">{disc} discrepancies · {o.counts["Matured"]} overdue</span></div>
      </div>
      <div className="grid g-main">
        <Section title="Needs your action" sub="discrepancies first, then by due date" right={<Link to="/deposits">Open register</Link>}>
          <div className="list">
            <div className="list-h"><span>Institution</span><span>What to do</span><span>Status</span><span className="r">Due</span><span /></div>
            {o.attention.map((r: any) => (
              <Link key={r.id} className="row" to={`/deposit/${r.id}`}>
                <span className="who"><b>{r.institution}</b><span className="mono">{r.id}</span> <span>· {r.bank}</span></span>
                <span className="what">{r.next}<div className="small muted">{inr(r.amount)} · FDR {r.fdr_no}</div></span>
                <Pill s={r.verification === "Discrepancy found" ? r.verification : r.state} />
                <span className="risk">{r.verification === "Discrepancy found" ? <span style={{ color: "var(--bad)" }}>Now</span> : <Days d={r.days} />}</span>
                <ChevronRight size={16} className="chev" />
              </Link>
            ))}
          </div>
        </Section>
        <div className="grid" style={{ gap: 28 }}>
          <Section title="Where every deposit stands" sub="the PS's six stages">
            <div className="bar" role="img" aria-label="Deposits by lifecycle stage">
              {LIFE.map((l) => <i key={l.k} style={{ width: `${100 * (o.counts[l.k] || 0) / live}%`, background: l.c }} />)}
            </div>
            <div className="legend">
              {LIFE.map((l) => <div key={l.k}><i style={{ background: l.c }} /><span>{l.k}</span><b>{o.counts[l.k] || 0}</b></div>)}
              <div><i style={{ background: "var(--n-300)" }} /><span>Renewed · Released</span><b>{o.counts["Renewed"]} · {o.counts["Released"]}</b></div>
            </div>
          </Section>
          <Section title="Maturities, next 12 months" right={<Link to="/calendar">Calendar</Link>}>
            <div className="cal">
              {o.months.map((m: any, k: number) => (
                <div key={m.month} className={`m ${k < 3 ? "near" : ""}`} title={`${m.count} deposit(s), ${inr(m.value)}`}>
                  <b>{m.count || ""}</b><i style={{ height: `${(m.count / maxM) * 92}px` }} />
                  <span>{new Date(m.month + "-01T00:00:00").toLocaleDateString("en-IN", { month: "short" })}</span>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </div>
      <Section title="Recent activity" right={<Link to="/ledger">Audit ledger</Link>}>
        <div className="feed">
          {o.recent.map((e: any) => (
            <div key={e.id} className="ev"><span><b style={{ fontWeight: 500 }}>{e.inst_name}</b> · {e.text}</span><span className="h">{fmtDate(e.ts)}</span></div>
          ))}
        </div>
      </Section>
    </div>
  );
}
