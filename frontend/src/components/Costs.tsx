import { useEffect, useState } from "react";
import { api, fmtUsd, type AgentUsage } from "../api";
import { ErrorBox, Loading } from "./common";

type Props = { version: number; weeksScored: number; players: number };

const AGENTS: Record<string, { name: string; role: string; per: string }> = {
  scout: { name: "🔎 Scout", role: "Gathers wiki, news and web sources for a week", per: "per show-week (shared by every league)" },
  recapper: { name: "📝 Recapper", role: "Turns sources into events with exact quotes", per: "per show-week (shared by every league)" },
  host: { name: "🎙️ Host", role: "Writes the weekly drop", per: "per league-week" },
  ref: { name: "⚖️ Ref", role: "Investigates a dispute", per: "per dispute" },
  rulesmith: { name: "📜 Rulesmith", role: "Drafts house rules", per: "per request" },
};

export default function Costs({ version, weeksScored, players }: Props) {
  const [usage, setUsage] = useState<Record<string, AgentUsage> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.usage().then(setUsage).catch((e) => setError(e.message));
  }, [version]);

  if (error) return <ErrorBox error={error} />;
  if (!usage) return <Loading />;

  const avg = (k: string) => usage[k]?.avg_cost_usd ?? 0;
  // One league alone for one week: it carries the whole show-week pipeline, one drop and one dispute.
  const leagueWeek = avg("scout") + avg("recapper") + avg("host") + avg("ref");
  const total = Object.values(usage).reduce((s, a) => s + a.cost_usd, 0);

  return (
    <section>
      <h2 className="section">What it costs to run</h2>
      <p className="hint">Measured from the token counts the API returned on every billed run (gpt-6-luna through Portkey). Runs answered from Portkey's cache or blocked by the provider cost nothing and are listed as free.</p>
      <div className="grid2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="small muted">One league, one week (Scout + Recapper + Host + one dispute, average measured runs)</div>
          <div style={{ fontSize: "2.4rem", fontWeight: 800 }}>{fmtUsd(leagueWeek)}</div>
          <div className="small muted">≈ {fmtUsd(leagueWeek * weeksScored)} for a {weeksScored}-week season · {players} players → {fmtUsd((leagueWeek * weeksScored) / players)} each</div>
        </div>
        <div className="card">
          <div className="small muted">Billed so far in this app ({weeksScored} weeks scored, including tests)</div>
          <div style={{ fontSize: "2.4rem", fontWeight: 800 }}>{fmtUsd(total)}</div>
          <div className="small muted">Scout + Recapper run once per episode week no matter how many leagues follow the show.</div>
        </div>
      </div>
      <div className="card">
        <table className="tbl">
          <thead>
            <tr><th>Agent</th><th>Billed</th><th className="num">Runs</th><th className="num">Avg cost</th><th className="num">Avg time</th>
              <th className="num">Avg input tok</th><th className="num">Avg cached</th><th className="num">Avg output tok</th><th className="num">Free runs</th></tr>
          </thead>
          <tbody>
            {Object.entries(AGENTS).map(([k, a]) => {
              const u = usage[k];
              return (
                <tr key={k}>
                  <td><b>{a.name}</b><div className="small muted">{a.role}</div></td>
                  <td className="small muted">{a.per}</td>
                  <td className="num">{u?.runs ?? 0}</td>
                  <td className="num">{u ? fmtUsd(u.avg_cost_usd) : "–"}</td>
                  <td className="num">{u ? `${u.avg_seconds}s` : "–"}</td>
                  <td className="num">{u?.avg_input_tokens.toLocaleString() ?? "–"}</td>
                  <td className="num">{u?.avg_cached_input_tokens.toLocaleString() ?? "–"}</td>
                  <td className="num">{u?.avg_output_tokens.toLocaleString() ?? "–"}</td>
                  <td className="num">{u?.free_runs ?? 0}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
