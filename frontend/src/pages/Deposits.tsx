import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Download, HelpCircle } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, inr, Row } from "../api";
import { Days, HELP, Pill } from "../ui";

const FILTERS = ["", "Active", "Expiring", "Matured", "Pending verification", "Discrepancy found", "Release in progress", "Renewed", "Released"];

export default function Deposits() {
  const [params, setParams] = useSearchParams();
  const state = params.get("state") || "";
  const [q, setQ] = useState("");
  const [help, setHelp] = useState(false);
  const { data: all } = useQuery({ queryKey: ["deposits", "", ""], queryFn: () => api<Row[]>("/api/instruments") });
  const URGENCY = ["Discrepancy found", "Matured", "Pending verification", "Expiring", "Release in progress", "Active", "Renewed", "Released"];
  const rank = (r: Row) => URGENCY.indexOf(r.verification === "Discrepancy found" ? r.verification : r.state);
  const rows = [...(all || [])].sort((a, b) => rank(a) - rank(b) || (a.days ?? 0) - (b.days ?? 0)).filter((r) => (!state || r.state === state || r.verification === state) &&
    (!q || `${r.institution} ${r.id} ${r.fdr_no} ${r.bank} ${r.region}`.toLowerCase().includes(q.toLowerCase())));
  const count = (s: string) => (all || []).filter((r) => !s || r.state === s || r.verification === s).length;
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Deposit register</h1><p>Every security deposit and FDR, institution-wise and instrument-wise, with what the bank has confirmed.</p></div>
        <div className="actions">
          <button className="btn ghost" onClick={() => setHelp((h) => !h)} aria-expanded={help}><HelpCircle size={14} />What the stages mean</button>
          <a className="btn" href={`/api/reports/${state === "Discrepancy found" ? "discrepancies" : state === "Matured" ? "overdue" : state === "Pending verification" ? "pending-verification" : state === "Expiring" ? "upcoming-maturity" : "all"}.csv`}>
            <Download size={14} />Export CSV</a>
        </div>
      </div>
      {help && <div className="help">{Object.entries(HELP).map(([k, v]) => <div key={k}><Pill s={k} /><span>{v}</span></div>)}</div>}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <input className="input" placeholder="Search institution, FDR number, bank or region" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search deposits" />
        <div className="seg" role="tablist" aria-label="Filter by stage">
          {FILTERS.map((f) => (
            <button key={f} role="tab" aria-selected={state === f} className={state === f ? "on" : ""}
              onClick={() => setParams(f ? { state: f } : {})}>{f || "All"} <span className="muted">{count(f)}</span></button>
          ))}
        </div>
      </div>
      <div className="list">
        <div className="list-h" style={{ gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr) 120px 150px 170px 16px" }}>
          <span>Institution</span><span>Bank and FDR</span><span className="r">Amount</span><span>Matures</span><span>Stage · bank check</span><span />
        </div>
        {rows.map((r) => (
          <Link key={r.id} className="row" to={`/deposit/${r.id}`} style={{ gridTemplateColumns: "minmax(0,1.2fr) minmax(0,1fr) 120px 150px 170px 16px" }}>
            <span className="who"><b>{r.institution}</b><span className="mono">{r.id}</span> <span>· {r.region}</span></span>
            <span className="what">{r.bank}<div className="small muted mono">{r.fdr_no} · {r.ifsc}</div></span>
            <span className="r num">{inr(r.amount)}</span>
            <span className="small">{r.maturity_date ? new Date(r.maturity_date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "–"}{!["Renewed", "Released", "Release in progress"].includes(r.state) && <div><Days d={r.days} /></div>}</span>
            <span style={{ display: "grid", gap: 4 }}><Pill s={r.state} /><Pill s={r.verification} /></span>
            <ChevronRight size={16} className="chev" />
          </Link>
        ))}
        {all && !rows.length && <div className="empty">No deposits match. Clear the search or choose another stage.</div>}
      </div>
    </div>
  );
}
