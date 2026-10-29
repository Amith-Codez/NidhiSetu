import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileText, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useRole } from "../App";
import { api, fmtDate, inr, post } from "../api";

const STAGES = ["Requested", "Scrutinised", "Recommended", "Approved", "Discharged"];
const ACTION: Record<string, [string, string, string]> = {
  Requested: ["scrutinise", "Scrutinise", "Dealing hand"],
  Scrutinised: ["recommend", "Recommend release", "Section Officer"],
  Recommended: ["approve", "Approve release", "Competent authority"],
  Approved: ["discharge", "Send discharge letter to bank", "Regulation Bureau"],
};

export default function Releases() {
  const qc = useQueryClient();
  const role = useRole();
  const { data } = useQuery({ queryKey: ["releases"], queryFn: () => api<any[]>("/api/releases") });
  const [note, setNote] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<Record<string, { ok: boolean; t: string }>>({});

  async function step(r: any, action: string) {
    try {
      const out = await post(`/api/releases/${r.id}/${action}`, { actor: role, note: note[r.id] || "" });
      setMsg({ ...msg, [r.id]: { ok: true, t: `${out.state}. Logged in the audit ledger (${String(out.hash).slice(0, 12)}…).` } });
    } catch (e: any) { setMsg({ ...msg, [r.id]: { ok: false, t: e.message } }); }
    qc.invalidateQueries();
  }

  return (
    <div className="page">
      <div className="page-head"><div><h1>Release requests</h1>
        <p>Release or refund of a security deposit: conditions checked first, then two different officials, then a letter asking the bank to remove AICTE's lien. Switch "Acting as" at the top to play each role.</p></div></div>
      {data?.map((r) => {
        const at = STAGES.indexOf(r.state);
        const next = ACTION[r.state];
        return (
          <section key={r.id} className="section" style={{ borderTop: "1px solid var(--n-150)", paddingTop: 20 }}>
            <div className="section-h"><h2><Link to={`/deposit/${r.instrument_id}`}>{r.inst_name}</Link></h2>
              <span className="sub">{r.id} · FDR {r.fdr_no} · {r.bank} · {inr(r.amount)} · {r.grounds_text}</span></div>
            <div className="track" aria-label={`Stage: ${r.state}`}>
              {STAGES.map((s, k) => {
                const st = r.steps.find((x: any) => x.state === s);
                return (
                  <div key={s} className={`s ${k < at ? "done" : k === at ? "now" : ""}`}>
                    <i>{k <= at && <Check size={11} />}</i><b>{s}</b>
                    <span>{st ? `${st.by.split(" (")[0]} · ${fmtDate(st.ts)}` : k === at + 1 && next ? next[2] : ""}</span>
                  </div>
                );
              })}
            </div>
            <div className="grid g2" style={{ gap: 24 }}>
              <div>
                <div className="grp" style={{ paddingTop: 0 }}>Conditions, checked automatically</div>
                <div className="chk">
                  {r.checklist.map((c: any) => (
                    <div key={c.item}><span className={c.ok ? "ok" : "no"}>{c.ok ? <Check size={16} /> : <X size={16} />}</span>
                      <span>{c.item}<span className="small muted"> · {c.note}</span></span></div>
                  ))}
                </div>
              </div>
              <div style={{ display: "grid", gap: 10, alignContent: "start" }}>
                {next ? (
                  <>
                    <div className="small muted">Next: <b style={{ color: "var(--n-900)", fontWeight: 500 }}>{next[1]}</b> · by the {next[2].toLowerCase()}</div>
                    <input className="input" placeholder="Note for the record (optional)" value={note[r.id] || ""}
                      onChange={(e) => setNote({ ...note, [r.id]: e.target.value })} aria-label="Note" />
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="btn primary" onClick={() => step(r, next[0])}>{next[1]}</button>
                      <button className="btn" onClick={() => step(r, "return")}>Return to institution</button>
                    </div>
                  </>
                ) : r.letter ? (
                  <a className="btn" href={`/api/letters/${r.letter}`} target="_blank" rel="noreferrer" style={{ width: "max-content" }}>
                    <FileText size={14} />Discharge letter to the bank</a>
                ) : <span className="small muted">{r.state}</span>}
                {msg[r.id] && <p className="small" role="status" style={{ margin: 0, color: msg[r.id].ok ? "var(--ok)" : "var(--bad)" }}>{msg[r.id].t}</p>}
              </div>
            </div>
          </section>
        );
      })}
      {data && !data.length && <div className="empty">No release requests. Start one from a matured deposit.</div>}
    </div>
  );
}
