import { useEffect, useState } from "react";
import { api, fmtUsd, type DropRecord } from "../api";
import { ErrorBox, Loading, Points } from "./common";

type Props = { leagueKey: string; week: number; version: number; onChanged: (msg?: string) => void };

export default function DropView({ leagueKey, week, version, onChanged }: Props) {
  const [record, setRecord] = useState<DropRecord | null>(null);
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setRecord(null);
    setMissing(false);
    setError(null);
    api.drop(leagueKey, week)
      .then((r) => (r ? setRecord(r) : setMissing(true)))
      .catch((e) => setError(e.message));
  }, [leagueKey, week, version]);

  async function write() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.makeDrop(leagueKey, week);
      setRecord(r);
      setMissing(false);
      onChanged(`Week ${week} drop written (${fmtUsd(r.cost_usd ?? 0)})`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function copyForChat() {
    if (!record) return;
    const d = record.drop;
    const table = record.facts.standings.map((r) => `${r.rank}. ${r.player} ${r.total} (${r.this_week >= 0 ? "+" : ""}${r.this_week})`).join("\n");
    const text = [`💖 ${d.headline}`, "", d.opener, "", table, "", ...d.player_lines.map((p) => `• ${p.player}: ${p.line}`), "", d.closer].join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const moments = record ? Object.fromEntries(record.facts.moments.map((m) => [m.event_id, m])) : {};

  return (
    <section>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h2 className="section" style={{ margin: 0 }}>The Week {week} drop</h2>
            <p className="hint" style={{ margin: "4px 0 0" }}>The Host writes the group-chat recap. Code checks every number and name against the real standings, and nothing past Week {week} can sneak in.</p>
          </div>
          <div className="row">
            {record && <button className="btn ghost" onClick={copyForChat}>{copied ? "Copied! 📋" : "📋 Copy for the group chat"}</button>}
            <button className="btn" onClick={write} disabled={busy}>{record ? "🎙️ Rewrite" : "🎙️ Write the drop"}</button>
          </div>
        </div>
        {busy && <Loading kind="host" />}
        <ErrorBox error={error} />
      </div>

      {!record && !missing && !busy && <Loading />}
      {missing && !busy && <div className="card muted">No drop for Week {week} yet. Your host is ready when you are.</div>}

      {record && (
        <article className="card drop">
          <h1>{record.drop.headline}</h1>
          <p className="muted small">{record.facts.league} · {record.week}{record.cost_usd !== undefined && ` · ${fmtUsd(record.cost_usd)}`}</p>
          <p className="opener">{record.drop.opener}</p>

          <table className="tbl" style={{ margin: "14px 0" }}>
            <thead><tr><th>#</th><th>Player</th><th className="num">Total</th><th className="num">This week</th><th className="num">Move</th></tr></thead>
            <tbody>
              {record.facts.standings.map((r) => (
                <tr key={r.player}>
                  <td>{r.rank === 1 ? "👑" : r.rank}</td>
                  <td><b>{r.player}</b> <span className="muted small">{r.team.join(", ")}</span></td>
                  <td className="num"><b>{r.total}</b></td>
                  <td className="num"><Points n={r.this_week} /></td>
                  <td className="num">{r.rank_change === 0 ? "–" : r.rank_change > 0 ? <span className="pos">▲{r.rank_change}</span> : <span className="neg">▼{-r.rank_change}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>The group chat report</h3>
          {record.drop.player_lines.map((p) => <p key={p.player} className="pl"><b>{p.player}:</b> {p.line}</p>)}

          <h3 style={{ marginTop: 18 }}>Moments that moved the league</h3>
          {record.drop.moments.map((m) => (
            <div key={m.event_id} className="line" style={{ gridTemplateColumns: "1fr", marginBottom: 8 }}>
              <div>{m.line}</div>
              {moments[m.event_id] && (
                <div className="receipt">“{moments[m.event_id].quote}” · {moments[m.event_id].scored.join(", ")}</div>
              )}
            </div>
          ))}
          <p className="closer">{record.drop.closer}</p>
        </article>
      )}
    </section>
  );
}
