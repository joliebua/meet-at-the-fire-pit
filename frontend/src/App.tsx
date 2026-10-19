import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { api, weekNum, type AppConfig, type League, type LeagueSummary, type WeekInfo } from "./api";
import { ErrorBox, Loading } from "./components/common";
import Leaderboard from "./components/Leaderboard";
import Villa from "./components/Villa";
import HouseRules from "./components/HouseRules";
import Disputes from "./components/Disputes";
import DropView from "./components/Drop";
import Costs from "./components/Costs";
import PlayView from "./components/PlayView";

const HeartBurst = lazy(() => import("./components/three/HeartBurst"));

const DEMO = "demo_league";
const NEW = "__new__";

const TABS = [
  { id: "board", label: "🏝️ Leaderboard", play: true, classic: true },
  { id: "play", label: "🎯 Draft & Moves", play: true, classic: true },
  { id: "villa", label: "📺 This Week in the Villa", play: true, classic: true },
  { id: "drop", label: "🔥 Fire Pit", play: true, classic: true },
  { id: "rules", label: "📜 House Rules", play: false, classic: true },
  { id: "disputes", label: "⚖️ Disputes", play: false, classic: true },
  { id: "costs", label: "💸 Cost to Run", play: true, classic: true },
] as const;
type Tab = (typeof TABS)[number]["id"];

// Links like /#league=demo_league&tab=disputes&week=3 open a view directly (handy for sharing and screenshots).
function fromHash(): { tab?: Tab; week?: number; league?: string } {
  const h = new URLSearchParams(window.location.hash.slice(1));
  const tab = TABS.find((t) => t.id === h.get("tab"))?.id;
  return { tab, week: Number(h.get("week")) || undefined, league: h.get("league") || undefined };
}

export default function App() {
  const initial = fromHash();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [leagues, setLeagues] = useState<LeagueSummary[]>([]);
  const [leagueKey, setLeagueKey] = useState(initial.league ?? DEMO);
  const [newLeague, setNewLeague] = useState(false);
  const [league, setLeague] = useState<League | null>(null);
  const [weeks, setWeeks] = useState<WeekInfo[]>([]);
  const [watched, setWatched] = useState<number | null>(initial.week ?? null);
  const [tab, setTab] = useState<Tab>(initial.tab ?? "board");
  const [version, setVersion] = useState(0); // bump to refetch after any change
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [burst, setBurst] = useState(0);

  const isPlay = league?.mode === "play";
  const week = isPlay ? league?.current_week ?? 0 : watched;

  useEffect(() => {
    const h = new URLSearchParams({ league: leagueKey, tab, ...(watched && !isPlay ? { week: String(watched) } : {}) });
    window.history.replaceState(null, "", `#${h}`);
  }, [leagueKey, tab, watched, isPlay]);

  const changed = useCallback((message?: string) => {
    setVersion((v) => v + 1);
    if (message) {
      setToast(message);
      setTimeout(() => setToast(null), 3500);
    }
  }, []);
  const celebrate = useCallback(() => setBurst((b) => b + 1), []);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    api.leagues().then(setLeagues).catch((e) => setError(e.message));
  }, [version]);

  useEffect(() => {
    api.league(leagueKey)
      .then((lg) => {
        setLeague(lg);
        return api.weeks(lg.season);
      })
      .then((ws) => {
        setWeeks(ws);
        const recapped = ws.filter((w) => w.recapped).map((w) => weekNum(w.week));
        setWatched((cur) => cur ?? (recapped.length ? Math.max(...recapped) : null));
      })
      .catch((e) => setError(e.message));
  }, [leagueKey, version]);

  function switchLeague(key: string) {
    if (key === NEW) {
      setNewLeague(true);
      setTab("play");
      return;
    }
    setNewLeague(false);
    setLeague(null);
    setLeagueKey(key);
    const target = leagues.find((l) => l.key === key);
    if (target?.mode === "play" && !TABS.find((t) => t.id === tab)?.play) setTab("board");
  }

  const recappedWeeks = weeks.filter((w) => w.recapped);
  const show = league && config ? config.seasons[league.season] : null;
  const tabs = TABS.filter((t) => (isPlay ? t.play : t.classic));
  const highlight = isPlay ? league?.you : league?.commissioner;
  const needsWeek = isPlay && week === 0 && (tab === "villa" || tab === "drop");

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="logo" title="Islanders, meet me at the fire pit">Meet at the Fire Pit <span className="flame" aria-hidden="true">🔥</span></h1>
        <label className="league-name row" style={{ gap: 8 }}>
          <select value={newLeague ? NEW : leagueKey} onChange={(e) => switchLeague(e.target.value)} title="Switch league">
            {leagues.map((l) => (
              <option key={l.key} value={l.key}>{l.mode === "play" ? "🎯 " : "🏝️ "}{l.name}</option>
            ))}
            <option value={NEW}>＋ New play-along league…</option>
          </select>
          {show && <span>{show.show} season {show.season}</span>}
        </label>
        <div className="spacer" />
        {config && (
          <span className={`badge ${config.source_mode === "live" ? "hot" : "pool"}`}
                title={config.source_mode === "live" ? "Gathering from live wiki, news and web search" : "Replaying the saved snapshot offline"}>
            {config.source_mode === "live" ? "🔴 Live sources" : "💾 Snapshot mode"}
          </span>
        )}
        {isPlay ? (
          <span className="badge gold" title="Play-along: nobody can see past the current week">
            📅 {week === 0 ? "Pre-season draft" : `Week ${week} of ${recappedWeeks.length}`}
          </span>
        ) : recappedWeeks.length > 0 && watched !== null && (
          <label className="watch" title="Spoiler shield: scores and drops only use weeks you've watched">
            🙈 I've watched through
            <select value={watched} onChange={(e) => setWatched(Number(e.target.value))}>
              {recappedWeeks.map((w) => (
                <option key={w.week} value={weekNum(w.week)}>{w.week}</option>
              ))}
            </select>
          </label>
        )}
      </header>

      <nav className="tabs">
        {tabs.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <ErrorBox error={error} />
      {!league || week === null ? (
        !error && <Loading />
      ) : (
        <main>
          {needsWeek && <div className="card muted">Nothing has aired in this league yet. Finish the draft and play Week 1 in 🎯 Draft & Moves.</div>}
          {tab === "board" && <Leaderboard leagueKey={leagueKey} league={league} week={week} version={version} highlight={highlight} />}
          {tab === "play" && (
            <PlayView leagueKey={newLeague || !isPlay ? null : leagueKey} celebrate={celebrate}
              onChanged={changed}
              onCreated={(key) => { setNewLeague(false); setLeague(null); setLeagueKey(key); changed("Welcome to the villa 🌴"); }} />
          )}
          {tab === "villa" && !needsWeek && <Villa league={league} weeks={weeks} watched={week} version={version} onChanged={changed} />}
          {tab === "drop" && !needsWeek && <DropView leagueKey={leagueKey} week={week} version={version} onChanged={changed} />}
          {tab === "rules" && !isPlay && <HouseRules leagueKey={leagueKey} league={league} onChanged={changed} />}
          {tab === "disputes" && !isPlay && <Disputes leagueKey={leagueKey} league={league} onChanged={changed} />}
          {tab === "costs" && <Costs version={version} weeksScored={recappedWeeks.length} players={league.players.length} />}
        </main>
      )}

      {burst > 0 && <Suspense fallback={null}><HeartBurst burst={burst} /></Suspense>}
      {toast && <div className="toast">{toast}</div>}
      <footer className="foot">
        Islanders, meet me at the fire pit 🔥 · fan-made fantasy league tool · not affiliated with Love Island, ITV or Peacock · every point has a receipt
        {config && <> · model {config.model}</>}
      </footer>
    </div>
  );
}
