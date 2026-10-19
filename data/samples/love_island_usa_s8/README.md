# Snapshot: Love Island USA season 8

Recorded answers from the live sources (Wikipedia + Fandom MediaWiki API, Google News RSS headlines, OpenAI web search answers) so the app runs offline with `VILLA_SOURCE_MODE=snapshot`.

- Wiki text is CC BY-SA (Wikipedia / Fandom contributors).
- News items are headlines + links only; full articles are never saved.

Scout runs used to record it:

```json
[
 {
  "week": "Week 1",
  "sources": 3,
  "cost_usd": 0.000712,
  "steps": [
   "episode_guide",
   "read_week",
   "read_week",
   "search_news"
  ]
 },
 {
  "week": "Week 2",
  "sources": 6,
  "cost_usd": 0.000767,
  "steps": [
   "episode_guide",
   "read_week",
   "read_week",
   "search_news"
  ]
 },
 {
  "week": "Week 3",
  "sources": 5,
  "cost_usd": 0.000889,
  "steps": [
   "episode_guide",
   "episode_guide",
   "read_week",
   "read_week",
   "search_news"
  ]
 },
 {
  "week": "Week 4",
  "sources": 4,
  "cost_usd": 0.000972,
  "steps": [
   "episode_guide",
   "episode_guide",
   "read_week",
   "read_week",
   "search_news"
  ]
 },
 {
  "week": "Week 5",
  "sources": 4,
  "cost_usd": 0.014577,
  "steps": [
   "episode_guide",
   "read_week",
   "read_week",
   "search_news",
   "web_search"
  ]
 }
]
```
