import { useQuery } from "@tanstack/react-query";
import { Link2, ShieldCheck, ShieldX } from "lucide-react";
import { useState } from "react";
import { api } from "../api";

export default function Ledger() {
  const { data } = useQuery({ queryKey: ["ledger"], queryFn: () => api<any[]>("/api/audit?limit=80") });
  const [chk, setChk] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="page">
      <div className="page-head"><div><h1>Audit ledger</h1>
        <p>Every upload, bank answer, reminder, escalation and release step. Each entry carries the fingerprint of the one before it, so changing any past entry breaks every fingerprint after it.</p></div>
        <div className="actions"><button className="btn primary" disabled={busy} onClick={async () => { setBusy(true); setChk(await api("/api/audit/verify")); setBusy(false); }}>
          <Link2 size={14} />{busy ? "Checking…" : "Verify the whole chain"}</button></div>
      </div>
      {chk && (
        <div className={`next ${chk.ok ? "" : "bad"}`} role="status">
          <span className="ic">{chk.ok ? <ShieldCheck size={17} color="var(--ok)" /> : <ShieldX size={17} />}</span>
          <div><b>{chk.ok ? `Intact: all ${chk.entries} entries recomputed and matched` : `Broken at entry #${chk.broken_at}`}</b>
            {chk.head && <p className="mono">Latest fingerprint {chk.head}</p>}</div><span />
        </div>
      )}
      <table className="table ledger">
        <thead><tr><th className="r">#</th><th>Time (UTC)</th><th>Who</th><th>What happened</th><th>Subject</th><th>Previous fingerprint</th><th>This entry</th></tr></thead>
        <tbody>{data?.map((r) => (
          <tr key={r.seq}><td className="r num">{r.seq}</td><td className="small mono">{r.ts.replace("T", " ").slice(0, 19)}</td><td className="small">{r.actor}</td>
            <td className="small">{r.action}</td><td className="mono small">{r.subject}</td>
            <td className="h">{r.prev_hash.slice(0, 14)}…</td><td className="h">{r.hash.slice(0, 14)}…</td></tr>))}
        </tbody>
      </table>
    </div>
  );
}
