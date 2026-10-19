import { useEffect, useMemo, useState } from "react";
import { api, weekNum, type LedgerLine, type League, type Standings } from "../api";
import { ErrorBox, EVENT_ICONS, Loading, Points } from "./common";

type Props = { leagueKey: string; league: League; week: number; version: number };

export default function Leaderboard({ leagueKey, league, week, version }: Props) {
  const [data, setData] = useState<Standings | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [ledger, setLedger] = useState<LedgerLine[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api.standings(leagueKey, week).then(setData).catch((e) => setError(e.message));
  }, [leagueKey, week, version]);

  useEffect(() => {
    if (!selected) return;
    setLedger(null);
    api.ledger(leagueKey, selected).then(setLedger).catch((e) => setError(e.message));
  }, [leagueKey, selected, version]);

  // Spoiler shield: only show points from weeks the user has watched, newest first.
  const visibleLedger = useMemo(
    () => (ledger ?? []).filter((l) => weekNum(l.week) <= week).sort((a, b) => weekNum(b.week) - weekNum(a.week)),
    [ledger, week],
  );

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;

  const maxWeek = Math.max(1, ...data.standings.flatMap((r) => Object.values(r.by_week).map(Math.abs)));
  const rosterOf = (name: string) => league.players.find((p) => p.name === name)?.roster ?? [];

  return (
    <div className="grid-side" style={{ gridTemplateColumns: selected ? "1fr 420px" : "1fr" }}>
      <section>
        <h2 className="section">The leaderboard</h2>
        <p className="hint">Through {data.weeks[data.weeks.length - 1]}. Tap a player to see every point and the receipt behind it.</p>
        <div className="board">
          {data.standings.map((row, i) => (
            <article key={row.player} className={`card player ${selected === row.player ? "selected" : ""}`}
                     onClick={() => setSelected(selected === row.player ? null : row.player)}>
              <div className={`rank r${i + 1}`}>{i + 1}</div>
              <div>
                <div className="pname">{row.player}{league.commissioner === row.player && <span className="badge gold" style={{ marginLeft: 8 }}>👑 commissioner</span>}</div>
                <div className="chips">
                  {rosterOf(row.player).map((slot) => {
                    const started = (slot.from_week ?? 1) <= week;
                    return (
                      <span key={slot.islander} className="chip" style={started ? undefined : { opacity: 0.4 }}
                            title={started ? undefined : `Joins this team in Week ${slot.from_week}`}>
                        {slot.islander}
                        <b><Points n={row.by_islander[slot.islander] ?? 0} /></b>
                      </span>
                    );
                  })}
                </div>
                <div className="weekbars" title="Points per week">
                  {data.weeks.map((w) => {
                    const p = row.by_week[w] ?? 0;
                    return <span key={w} className={p < 0 ? "negbar" : ""} title={`${w}: ${p}`}
                                 style={{ height: `${Math.max(4, (Math.abs(p) / maxWeek) * 34)}px` }} />;
                  })}
                </div>
              </div>
              <div className="total">{row.total}<small>points</small></div>
            </article>
          ))}
        </div>
      </section>

      {selected && (
        <aside className="card" style={{ position: "sticky", top: 16 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>{selected}'s receipts</h3>
            <button className="btn ghost small" onClick={() => setSelected(null)}>Close</button>
          </div>
          <p className="hint small" style={{ marginTop: 6 }}>Every line comes from a verified event plus a league rule.</p>
          {!ledger ? <Loading /> : (
            <div className="ledger">
              {visibleLedger.map((l, i) => (
                <div className="line" key={`${l.event_id}-${l.rule_id}-${l.islander}-${i}`}>
                  <div className="pts"><Points n={l.points} /></div>
                  <div>
                    <div><b>{l.islander}</b> · {l.label} <span className="muted small">· {l.week}</span></div>
                    {l.source_id === "code"
                      ? <div className="receipt">{EVENT_ICONS.survived_week} still in the villa when the week ended</div>
                      : <div className="receipt">“{l.quote}” <span className="muted">({l.source_id})</span></div>}
                  </div>
                </div>
              ))}
              {visibleLedger.length === 0 && <p className="muted">No points yet.</p>}
            </div>
          )}
        </aside>
      )}
    </div>
  );
}
