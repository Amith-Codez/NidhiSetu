import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Landmark } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, fmtDate, inr, post } from "../api";

/** What the bank branch sees when it opens the signed one-time link (Tier 3). */
export default function Confirm() {
  const { token = "" } = useParams();
  const qc = useQueryClient();
  const { data: c, error } = useQuery({ queryKey: ["confirm", token], queryFn: () => api(`/api/confirmations/${token}`) });
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string>("");
  if (error) return <div className="page"><div className="empty">This link is not valid.</div></div>;
  if (!c) return <div className="page"><div className="empty">Loading…</div></div>;
  async function answer(a: string) {
    const r = await post(`/api/confirmations/${token}/answer`, { answer: a, note });
    setDone(`Thank you. Your answer is recorded (${String(r.hash).slice(0, 12)}…).`);
    qc.invalidateQueries();
  }
  return (
    <div className="page" style={{ maxWidth: 640 }}>
      <div className="page-head"><div><h1>Did your branch issue this FDR?</h1>
        <p>{c.bank} · request sent to {c.contact}. This one-time link was signed by AICTE's Regulation Bureau and works once.</p></div></div>
      <div className="next">
        <span className="ic" style={{ color: "var(--p-600)" }}><Landmark size={17} /></span>
        <div><b>{c.institution}</b>
          <dl className="kv" style={{ marginTop: 8 }}>
            <dt>FDR number</dt><dd className="mono">{c.fdr_no}</dd><dt>IFSC</dt><dd className="mono">{c.ifsc}</dd>
            <dt>Amount</dt><dd>{inr(c.amount)}</dd><dt>Deposited</dt><dd>{fmtDate(c.deposit_date)}</dd><dt>Matures</dt><dd>{fmtDate(c.maturity_date)}</dd>
          </dl></div><span />
      </div>
      {c.state === "sent" && !done ? (
        <>
          <input className="input" placeholder="Note (optional), e.g. lien marked on 12 June" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" onClick={() => answer("yes")}>Yes, we issued it, with lien to AICTE</button>
            <button className="btn" onClick={() => answer("no")}>No, we did not issue this</button>
          </div>
        </>
      ) : <p role="status">{done || `Already answered: ${c.state}.`}</p>}
    </div>
  );
}
