// Thin typed client for the NidhiSetu API. All calls go through /api (proxied in dev, same origin in production).
export interface Row {
  id: string; institution_id: string; institution: string; region: string; bank: string; ifsc: string; fdr_no: string;
  amount: number; maturity_date: string; deposit_date: string; days: number | null; state: string; verification: string;
  risk: number; next: string; channel: string | null; story: string | null;
}
export interface Check {
  id: number; engine: string; code: string; title: string; outcome: string; severity: "hard" | "soft" | "info";
  weight: number; detail: string; rule_ref?: string | null; created_at: string;
  evidence: { page?: number; bbox?: number[] | null; tier?: number; [k: string]: unknown };
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}

export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/** Indian grouping, as on a receipt: ₹25,00,000 */
export function inr(x: number | null | undefined, short = false) {
  if (x == null) return "–";
  if (short) {
    if (x >= 1e7) return `₹${(x / 1e7).toFixed(x >= 1e8 ? 0 : 2)} Cr`;
    if (x >= 1e5) return `₹${(x / 1e5).toFixed(x % 1e5 ? 1 : 0)} L`;
  }
  return "₹" + Math.round(x).toLocaleString("en-IN");
}

export const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso.length === 10 ? iso + "T00:00:00" : iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "–";

export const FIELD_LABEL: Record<string, string> = {
  bank: "Bank", branch: "Branch", ifsc: "IFSC", fdr_no: "FDR number", depositor: "Depositor", favour: "In favour of",
  lien: "Lien for AICTE", amount_inr: "Amount", rate: "Interest rate", deposit_date: "Date of deposit",
  period_months: "Period", maturity_date: "Maturity date", maturity_value: "Maturity value", auto_renewal: "Auto renewal",
};
