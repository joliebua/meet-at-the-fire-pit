// Thin client for the FastAPI backend. Every call goes to /api on the same origin.

export type Evidence = { source_id: string; quote: string };

export type VillaEvent = {
  id: string;
  week: string;
  type: string;
  islanders: string[];
  others: string[];
  day: number | null;
  detail: string;
  evidence: Evidence[];
  status: "verified" | "rejected";
  problems: string[];
  corroborated_by: number;
};

export type Source = { id: string; kind: string; title: string; url: string; outlet: string; published: string; text: string; flags: string[] };

export type Rule = {
  id: string;
  label: string;
  event_type: string;
  points: number;
  applies_to: string;
  min_day: number | null;
  max_day: number | null;
  quote_keywords: string[];
  source: "standard" | "house";
  status: "approved" | "pending" | "declined";
  replaces: string | null;
  original_text: string;
};

export type StandingRow = { player: string; total: number; by_week: Record<string, number>; by_islander: Record<string, number> };
export type Standings = { league: string; weeks: string[]; standings: StandingRow[]; rules: Rule[] };

export type LedgerLine = { week: string; event_id: string; islander: string; rule_id: string; label: string; points: number; quote: string; source_id: string };

export type Player = { name: string; roster: { islander: string; from_week?: number }[] };

export type Ruling = {
  verdict: "uphold" | "partial" | "deny";
  explanation: string;
  add_events: (VillaEvent & { week: string })[];
  remove_event_ids: string[];
  injection_suspected: boolean;
};

export type Dispute = {
  id: string;
  player: string;
  text: string;
  filed: string;
  ruling: Ruling;
  adjustments: string[];
  input_flags: string[];
  status: "pending" | "approved" | "declined" | "closed";
};

export type League = {
  name: string;
  season: string;
  commissioner: string;
  players: Player[];
  house_rules: Rule[];
  disputes?: Dispute[];
};

export type WeekInfo = {
  week: string;
  episodes: string[];
  first_aired: string;
  last_aired: string;
  recapped: boolean;
  verified_events: number;
  rejected_events: number;
};

export type Impact = { player: string; before: number; after: number; change: number };

export type DropRecord = {
  week: string;
  written: string;
  drop: {
    headline: string;
    opener: string;
    player_lines: { player: string; line: string }[];
    moments: { event_id: string; line: string }[];
    closer: string;
  };
  facts: {
    league: string;
    standings: { rank: number; player: string; total: number; this_week: number; rank_change: number; team: string[] }[];
    moments: { event_id: string; islanders: string[]; scored: string[]; teams: string[]; points_for_teams: number; quote: string }[];
  };
  cost_usd?: number;
  seconds?: number;
};

export type AgentUsage = {
  runs: number;
  cost_usd: number;
  avg_cost_usd: number;
  avg_seconds: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  gateway_cache_hits: number;
};

export type AppConfig = { source_mode: string; snapshot: string; model: string; seasons: Record<string, { show: string; season: string }> };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  return body as T;
}

const post = <T,>(path: string, data?: unknown) => call<T>(path, { method: "POST", body: data ? JSON.stringify(data) : undefined });

export const api = {
  config: () => call<AppConfig>("/config"),
  league: (key: string) => call<League>(`/leagues/${key}`),
  standings: (key: string, week?: number) => call<Standings>(`/leagues/${key}/standings${week ? `?week=${week}` : ""}`),
  ledger: (key: string, player: string) => call<LedgerLine[]>(`/leagues/${key}/ledger?player=${encodeURIComponent(player)}`),
  weeks: (season: string) => call<WeekInfo[]>(`/seasons/${season}/weeks`),
  events: (season: string, week: string) => call<Record<string, VillaEvent[]>>(`/seasons/${season}/events?week=${encodeURIComponent(week)}`),
  sources: (season: string, week: string) => call<{ sources: Source[]; gaps: string[]; notes: string }>(`/seasons/${season}/sources?week=${encodeURIComponent(week)}`),
  refresh: (season: string, n: number) =>
    post<{ week: string; sources: number; verified_events: number; rejected_events: number; cost_usd: number; seconds: number }>(`/seasons/${season}/weeks/${n}/refresh`),
  proposeRules: (key: string, text: string) =>
    post<{ rules: Rule[]; unsupported: { original_text: string; reason: string }[]; impact: Impact[]; matches: Record<string, number>; cost_usd: number; seconds: number }>(
      `/leagues/${key}/house-rules`, { text }),
  decideRule: (key: string, id: string, decision: "approve" | "decline") => post(`/leagues/${key}/house-rules/${id}/${decision}`),
  fileDispute: (key: string, player: string, text: string) =>
    post<{ dispute: Dispute; impact: Impact[]; steps: string[]; cost_usd: number; seconds: number }>(`/leagues/${key}/disputes`, { player, text }),
  decideDispute: (key: string, id: string, decision: "approve" | "decline") => post<Dispute>(`/leagues/${key}/disputes/${id}/${decision}`),
  drop: (key: string, week: number) => call<DropRecord | null>(`/leagues/${key}/drops/${week}`),
  makeDrop: (key: string, week: number) => post<DropRecord>(`/leagues/${key}/drops/${week}`),
  usage: () => call<Record<string, AgentUsage>>("/usage"),
};

export const weekNum = (w: string) => Number(w.split(" ").pop());
export const fmtPts = (n: number) => (n > 0 ? `+${n}` : `${n}`);
export const fmtUsd = (n: number) => (n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`);
