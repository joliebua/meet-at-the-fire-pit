import { useEffect, useState } from "react";
import { api, fmtUsd, weekNum, type League, type Source, type VillaEvent, type WeekInfo } from "../api";
import { ErrorBox, EVENT_ICONS, EVENT_LABELS, Loading } from "./common";

type Props = { league: League; weeks: WeekInfo[]; watched: number; version: number; onChanged: (msg?: string) => void };

export default function Villa({ league, weeks, watched, version, onChanged }: Props) {
  const visible = weeks.filter((w) => weekNum(w.week) <= watched || !w.recapped);
  const [week, setWeek] = useState<string>(`Week ${watched}`);
  const [events, setEvents] = useState<VillaEvent[] | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [gaps, setGaps] = useState<string[]>([]);
  const [showRejected, setShowRejected] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const info = weeks.find((w) => w.week === week);

  useEffect(() => {
    setEvents(null);
    setError(null);
    if (!info?.recapped) {
      setEvents([]);
      setSources([]);
      return;
    }
    Promise.all([api.events(league.season, week), api.sources(league.season, week)])
      .then(([ev, src]) => {
        setEvents(ev[week] ?? []);
        setSources(src.sources);
        setGaps(src.gaps);
      })
      .catch((e) => setError(e.message));
  }, [league.season, week, info?.recapped, version]);

  async function refresh() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.refresh(league.season, weekNum(week));
      onChanged(`${r.week}: ${r.verified_events} verified events from ${r.sources} sources (${fmtUsd(r.cost_usd)}, ${r.seconds}s)`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const srcById = Object.fromEntries(sources.map((s) => [s.id, s]));
  const shown = (events ?? []).filter((e) => showRejected || e.status === "verified");
  const rejected = (events ?? []).filter((e) => e.status === "rejected").length;

  return (
    <div className="grid-side">
      <aside className="weeks">
        <h2 className="section">Episodes</h2>
        {visible.map((w) => (
          <button key={w.week} className={`weekbtn ${w.week === week ? "active" : ""}`} onClick={() => setWeek(w.week)}>
            <div className="wk">{w.week}</div>
            <div className="small muted">Ep {w.episodes[0]}–{w.episodes[w.episodes.length - 1]} · aired {w.first_aired.slice(5)} → {w.last_aired.slice(5)}</div>
            <div className="small" style={{ marginTop: 4 }}>
              {w.recapped ? <><span className="pos">✓ {w.verified_events} events</span>{w.rejected_events > 0 && <span className="neg"> · ✗ {w.rejected_events}</span>}</>
                : <span className="muted">not recapped yet</span>}
            </div>
          </button>
        ))}
        <p className="small muted">Later weeks are hidden by your spoiler shield.</p>
      </aside>

      <section>
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h2 style={{ margin: 0 }}>{week} in the villa</h2>
              <p className="hint" style={{ margin: "4px 0 0" }}>
                The Scout gathers sources, the Recapper lists events, and code checks every quote before anything scores.
              </p>
            </div>
            <button className="btn pool" onClick={refresh} disabled={busy}>{busy ? "Working…" : "🔄 Re-scout & recap"}</button>
          </div>
          {busy && <Loading kind="scout" />}
          <ErrorBox error={error} />
        </div>

        {events === null ? <Loading /> : (
          <>
            {sources.length > 0 && (
              <div className="card">
                <h3>Sources the Scout used</h3>
                <div className="chips">
                  {sources.map((s) => (
                    <a key={s.id} className="chip" href={s.url || undefined} target="_blank" rel="noreferrer"
                       title={s.title} style={{ color: "inherit", textDecoration: "none" }}>
                      {s.id} · {s.kind === "wiki" ? "📖" : s.kind === "web_search" ? "🔎" : "📰"} {s.outlet || s.kind}
                      {s.flags.length > 0 && <span className="badge bad" style={{ marginLeft: 6 }}>⚠ {s.flags.length}</span>}
                    </a>
                  ))}
                </div>
                {gaps.length > 0 && <p className="small muted" style={{ marginBottom: 0 }}>Gaps: {gaps.join(" · ")}</p>}
              </div>
            )}

            <div className="card">
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                <h3 style={{ margin: 0 }}>Events with receipts</h3>
                {rejected > 0 && (
                  <label className="small muted row" style={{ gap: 6 }}>
                    <input type="checkbox" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} />
                    show {rejected} rejected
                  </label>
                )}
              </div>
              {shown.length === 0 && <p className="muted">Nothing recapped for this week yet. Hit “Re-scout & recap”.</p>}
              <div className="events">
                {shown.map((e) => (
                  <div key={e.id} className={`event ${e.status}`}>
                    <div className="icon">{EVENT_ICONS[e.type] ?? "✨"}</div>
                    <div>
                      <div className="title">
                        {EVENT_LABELS[e.type] ?? e.type}: {e.islanders.join(" & ")}
                        {e.others.length > 0 && <span className="muted"> (with {e.others.join(", ")})</span>}
                      </div>
                      <div className="row small" style={{ gap: 6, marginTop: 2 }}>
                        {e.day !== null && <span className="badge dim">Day {e.day}</span>}
                        {e.detail && <span className="badge dim">{e.detail}</span>}
                        {e.status === "verified"
                          ? <span className="badge pool">✓ verified{e.corroborated_by > 1 ? ` · ${e.corroborated_by} sources agree` : ""}</span>
                          : <span className="badge bad">✗ receipt didn't check out</span>}
                      </div>
                      {e.evidence.map((ev, i) => (
                        <div key={i} className="receipt">
                          “{ev.quote}” <span className="muted">— {ev.source_id}{srcById[ev.source_id] ? ` · ${srcById[ev.source_id].outlet}` : ""}</span>
                        </div>
                      ))}
                      {e.problems.length > 0 && <div className="problems">{e.problems.join(" · ")}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
