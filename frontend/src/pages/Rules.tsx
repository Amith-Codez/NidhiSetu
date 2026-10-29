import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function Rules() {
  const { data } = useQuery({ queryKey: ["rules"], queryFn: () => api("/api/rules") });
  const rules: any[] = data?.parsed?.rules || [];
  return (
    <div className="page">
      <div className="page-head"><div><h1>Rulebook</h1>
        <p>Security deposit rules as an editable file, each tied to its source. Hard rules decide the status; soft rules only raise the risk score. When a norm changes, officers edit this file, not the code. Version: {data?.parsed?.version}</p></div></div>
      <table className="table">
          <thead><tr><th>Rule</th><th>What it checks</th><th>Kind</th><th>Source</th></tr></thead>
          <tbody>{rules.map((r) => <tr key={r.id}><td className="mono small">{r.id}</td><td>{r.title}</td>
            <td className="small nowrap">{r.severity === "hard" ? "Hard rule" : "Warning sign"}</td><td className="small muted">{r.ref}</td></tr>)}</tbody>
      </table>
      <details className="source">
        <summary>View the rule file as stored (rules.yaml)</summary>
        <pre className="code">{data?.text}</pre>
      </details>
    </div>
  );
}
