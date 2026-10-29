import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, FileText, ListChecks, Scale, ScanSearch, ScanText, ShieldCheck, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, Check as C, inr } from "../api";
import { OUTCOME_ICON, Pill, Section } from "../ui";

const STAGES = [
  { k: "READ", label: "Read", icon: <ScanText size={14} />, idle: "Fields off the receipt" },
  { k: "CHECK", label: "Check", icon: <ListChecks size={14} />, idle: "Security deposit rules" },
  { k: "CONFIRM", label: "Confirm", icon: <ShieldCheck size={14} />, idle: "Ask the bank" },
  { k: "DETECT", label: "Detect", icon: <ScanSearch size={14} />, idle: "Tampering signs" },
  { k: "DECIDE", label: "Decide", icon: <Scale size={14} />, idle: "Status and risk" },
];

export default function Verify() {
  const [params] = useSearchParams();
  const [ids, setIds] = useState<{ instrument_id: string; document_id: string } | null>(null);
  const [events, setEvents] = useState<{ stage: string; text: string; ms: number }[]>([]);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState("");
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { data: samples } = useQuery({ queryKey: ["samples"], queryFn: () => api<{ name: string; label: string }[]>("/api/samples") });
  const auto = params.get("sample");
  useEffect(() => { if (auto) sample(auto); }, [auto]);  // deep link: /verify?sample=<file>

  useEffect(() => {
    if (!ids) return;
    let stop = false;
    const tick = async () => {
      const ev = await api<any[]>(`/api/documents/${ids.document_id}/progress`);
      if (stop) return;
      setEvents(ev);
      if (ev.some((e) => e.stage === "DECIDE")) setResult(await api(`/api/instruments/${ids.instrument_id}`));
      else setTimeout(tick, 120);
    };
    tick();
    return () => { stop = true; };
  }, [ids]);

  function reset() { setEvents([]); setResult(null); setErr(""); }
  async function upload(f: File) {
    reset();
    if (!/\.(pdf|jpe?g|png)$/i.test(f.name)) { setErr("Upload the receipt as a PDF, JPG or PNG."); return; }
    if (f.size > 25 * 1024 * 1024) { setErr("That file is larger than 25 MB. A phone photo or the bank's PDF is enough."); return; }
    const fd = new FormData();
    fd.append("file", f);
    try { setIds(await api("/api/verify", { method: "POST", body: fd })); } catch (e: any) { setErr(e.message); }
  }
  async function sample(name: string) {
    reset();
    try { setIds(await api(`/api/samples/${encodeURIComponent(name)}/verify`, { method: "POST" })); } catch (e: any) { setErr(e.message); }
  }
  const done = new Set(events.map((e) => e.stage));
  const doneCount = STAGES.filter((s) => done.has(s.k)).length;
  const flags: C[] = (result?.checks || []).filter((c: C) => c.outcome === "Discrepancy found" || c.outcome === "flag");
  const good: C[] = (result?.checks || []).filter((c: C) => ["bank_confirmed", "sig_valid"].includes(c.code));

  return (
    <div className="page">
      <div className="page-head"><div><h1>Check an FDR</h1>
        <p>Check one receipt the way the portal checks every submission. Institutions can use this before they submit.</p></div></div>
      <div className="grid g-main">
        <div style={{ display: "grid", gap: 16 }}>
          <div className={`drop ${drag ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); }}>
            <UploadCloud size={26} color="var(--p-600)" aria-hidden="true" />
            <h3>Drag the fixed deposit receipt here</h3>
            <p className="muted small" style={{ margin: "0 0 14px" }}>The bank's e-FDR PDF, or a phone photo of the paper receipt. Up to 25 MB.</p>
            <button className="btn primary" onClick={() => input.current?.click()}>Choose a file</button>
            <input ref={input} type="file" hidden accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </div>
          {err && <p className="small" role="alert" style={{ color: "var(--bad)", margin: 0 }}>{err}</p>}
          <ol className="how">
            <li>Upload the receipt, or pick a sample on the right.</li>
            <li>Its fields are read and checked, and the bank is asked directly. This takes under a second.</li>
            <li>You see what the receipt says next to what the bank confirms, with any problem marked on the page.</li>
          </ol>
        </div>
        <Section title="Or try a sample" sub="synthetic receipts from sandbox banks">
          <div className="samples">
            {samples?.map((s) => (
              <button key={s.name} className="sample" onClick={() => sample(s.name)}><FileText size={16} color="var(--n-500)" /><span>{s.label}</span><span className="k">Run</span></button>
            ))}
          </div>
        </Section>
      </div>

      {(ids || events.length > 0) && (
        <Section title="Checking" sub={result ? `finished in ${events.find((e) => e.stage === "DECIDE")?.ms ?? "–"} ms` : "live"}>
          <div className="stepper" aria-live="polite">
            <span className="fill" style={{ width: `${Math.max(0, doneCount - 1) * 20}%` }} />
            {STAGES.map((s, i) => {
              const ev = events.find((e) => e.stage === s.k);
              const run = !ev && (i === 0 || done.has(STAGES[i - 1].k));
              return (
                <div key={s.k} className={`step ${ev ? "done" : run ? "run" : ""}`}>
                  <span className="dot">{ev ? <Check size={14} /> : s.icon}</span>
                  <span className="k">{s.label}</span>
                  <span className="s">{ev ? ev.text : run ? "Working…" : s.idle}</span>
                  {ev && <span className="ms">{ev.ms} ms</span>}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {result && (
        <Section title={`FDR ${result.fdr_no || "(number not read)"}`} sub={`${result.bank.name} · ${inr(result.amount)}`} right={<Pill s={result.verification} lg />}>
          <div className="evi">
            {(flags.length ? flags : good).slice(0, 5).map((c) => (
              <div className="check" key={c.id}><span className={`i ${OUTCOME_ICON(c.outcome)}`}>{c.outcome === "Confirmed by bank" ? "✓" : "!"}</span>
                <div><div className="t">{c.title}</div><div className="d">{c.detail}</div></div></div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="small muted" style={{ marginRight: "auto" }}>{flags.length ? `${flags.length} finding${flags.length > 1 ? "s" : ""}, each with evidence.` : "The bank confirmed every field. Nothing to fix."}</span>
            <Link className="btn primary" to={`/deposit/${result.id}`}>Paper vs bank, side by side <ArrowRight size={14} /></Link>
          </div>
        </Section>
      )}
    </div>
  );
}
