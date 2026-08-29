# Choicely

A second brain for the decisions you're tired of carrying. Log an everyday
decision; Choicely classifies it, predicts how much you'll regret it by
blending a population prior with your own recorded outcomes, answers it
outright once it's seen enough, checks back on its own to close the loop,
and tells you the patterns a friend would notice.

Demo walkthrough: **DEMO.md** (4-minute run of show).

## Run it

Backend (FastAPI, port 8000):
```
cd backend
.venv\Scripts\activate
pip install -r requirements.txt   # first run / after pulling: adds pywebpush
uvicorn app.main:app --reload --port 8000
```

Frontend (React/Vite, port 5173):
```
cd frontend
npm run dev
```

Open http://localhost:5173. A fresh launch (no `choicely.db`) starts at the
welcome screen → survey → the app, with no data.

**For a demo**, load the "Maya" persona and ~2 weeks of history:
```
cd backend && python seed_demo_data.py --reset
```
Then open http://localhost:5173/?demo — the `?demo` flag reveals the
time-travel control (bottom-right) that brings pending check-ins due.

If port 8000 is taken, run the backend elsewhere (`uvicorn app.main:app --port 8001`)
and point the frontend at it with `frontend/.env.local`:
```
VITE_API_BASE=http://localhost:8001
```
(restart `npm run dev` after changing it). The API origin is centralized in
`frontend/src/api.js`.

### Tests

```
cd backend
pip install -r requirements-dev.txt
pytest
```
Covers the regret blend, the crisis screen, the community-prior math, the
compare-options pipeline, and the main API flows. Each test runs against
its own throwaway SQLite file (`tests/conftest.py`).

### One-container build (API + frontend together)

```
docker build -t choicely . && docker run -p 8000:8000 -v choicely-data:/srv/data choicely
```
FastAPI serves the built React app from the same origin. See **DEPLOY.md**.

## Claude API

`backend/app/classifier.py` calls the real Claude API when `ANTHROPIC_API_KEY`
is set in the environment. Without a key it falls back to a keyword-based
heuristic classifier with the same interface, so the app runs end-to-end
without one. To go live:
```
setx ANTHROPIC_API_KEY "sk-ant-..."
```
(restart the terminal/backend after setting it)

## Wellness layer (hackathon push)

- **Regret forecast** (`backend/app/insights.py`, `GET /insights`,
  `frontend/src/RegretForecast.jsx`): for every category with recorded
  outcomes, shows a plain horizontal scale (0-100%) with a tick for the
  population rate and a tick for the reader's own estimate, a strip of
  coloured squares for the recorded outcomes, and one plain sentence:
  "71% of people regret this. Your 10 recorded outcomes pushed your
  estimate up to 90%." The blend math is still `regret.py`; `_interval` in
  `insights.py` and the earlier line-chart machinery remain in the payload
  but the UI is deliberately minimal. New "Regret forecast" tab.
- **Track record** (`backend/app/calibration.py`, `GET /track-record`,
  `frontend/src/TrackRecord.jsx`): Choicely scoring its own past
  predictions against the outcomes later recorded. Framed as
  accountability, not a victory lap -- per-decision error is inherently
  large (a probability judged against a 0/0.5/1 outcome), so the page
  leads with group calibration: a reliability curve (predictions bucketed
  by confidence vs. the actual regret rate in each bucket), a per-tier
  "typical miss" comparison (prior-only vs. blended vs. personal), and the
  count of confident calls (>=75% or <=25%) that the outcome bore out. The
  high-confidence end -- the only range auto-resolve fires in -- holds up;
  the middle is looser and the curve shows it. New "Track record" tab.
- **Regret triggers** (`backend/app/triggers.py`, `GET /triggers`,
  `frontend/src/RegretPatterns.jsx`): where the forecast asks "what kind
  of decision is this?", this asks "what was going on when you made it?"
  -- it splits every closed decision by time of day, time pressure, how
  many decisions were already logged that day, and how much back-and
  -forth preceded it, and surfaces the splits where the regret rate
  actually moves (both sides need >=4 decisions and a gap of >=18pp at
  >=1.4x, or it says nothing rather than invent a pattern). Positive
  windows are called out too. Shown as a "When regret clusters" section
  on the Track record tab. On the demo seed: Maya's morning decisions
  regret 90% vs 20% the rest of the day; her evenings are the reverse.
  `frontend/src/MentalLoad.jsx`): windowed to the last 7 days --
  decisions taken off your plate (auto-resolved + confidently estimated),
  loops closed (outcomes recorded), and questions still open (decision
  debt + live unresolved loops), plus average time-to-close. Sits at the
  top of the timeline as the app's headline metric.
- **Proactive check-ins** (`backend/app/checkins.py`, `GET /check-ins`,
  `frontend/src/CheckIns.jsx`): every decision gets an `outcome_due_at`
  stamp when logged (hours out for urgent/routine things, days for
  high-stakes). Once that passes with no outcome recorded, the decision
  surfaces at the top of the timeline as a check-in Choicely asks about
  ("you were weighing X -- how did it land?"). Answering feeds the same
  outcome pipeline as the manual buttons. This is the promise the old
  "I'll check back in a day or two" copy couldn't keep.
- **Installable PWA + push** (`frontend/public/manifest.webmanifest`,
  `frontend/public/sw.js`, `backend/app/push.py`): Choicely is an
  installable app (manifest + service worker + offline shell), and it can
  push a check-in notification with the tab closed. Settings has the
  opt-in (`frontend/src/Notifications.jsx`); a dismissible nudge on the
  timeline surfaces it once there's a decision to be reminded about. Web
  Push uses VAPID keys auto-generated to `backend/data/vapid_*` on first
  run (gitignored; the browser fetches the public key from
  `GET /push/config`). Subscriptions live in a `push_subscriptions`
  table; `push.notify_due()` fires one notification per newly-due
  check-in and is idempotent (a `notified_at` column). With no running
  scheduler, it's called from `POST /demo/advance` -- advancing the demo
  clock now also buzzes any installed client. Everything degrades
  cleanly: unsupported browser, denied permission, or `pywebpush` not
  installed all fall back to the in-app banner.
- **Weekly reflection** (`backend/app/reflection.py`, `GET /reflection`,
  `frontend/src/Reflection.jsx`): a short plain-language read on recent
  decisions. With `ANTHROPIC_API_KEY` set, Claude writes it from a compact
  serialization of the history; without one, a set of heuristic generators
  (habit callouts, an affirming note, the standing debt question,
  stakes-vs-latency, action bias, time-of-day, volume) each compute a
  candidate insight from the data, get scored by signal strength, and the
  strongest three are returned -- with an affirming one guaranteed a slot
  if the data supports it. Same shape either way. Sits below the mental-
  load banner.
- **Community priors** (`backend/app/community.py`, `GET /community/stats`,
  Settings opt-in): the reference dataset is a documented synthetic prior;
  this layer lets real opt-in outcomes correct it. Each shared row is a
  category label and an outcome -- no text, no id. Once a category has
  >=12 shared outcomes, the population rate Choicely quotes shifts
  partway toward the community rate: `effective = reference * (1 - k) +
  community * k`, `k = 0.55 * n / (n + 35)` so the shift is real but
  capped (community never fully overrides the reference). New decision
  cards show the provenance ("reference 62% · 50 shared outcomes ->
  66%"); the forecast tab deliberately keeps showing the untouched
  reference rate. Contributing is a per-browser toggle; outcomes are sent
  with `contribute: true` on the outcome POST. The pool is seeded with a
  labelled starter set (`community.STARTER_POOL`, applied by `init_db`
  when the table is empty).
- **Crisis guardrails** (`backend/app/safety.py`, screened in
  `POST /decisions`, `SafetyBox` on the card): some things typed into a
  decision box are not decisions a regret model should score. Two tiers:
  a **crisis** match (self-harm, abuse, a medical emergency) is logged so
  the person doesn't lose what they wrote, but gets no estimate, no
  category, and no check-in -- just a short calm message and a real
  resource (988, findahelpline.com, a local emergency number). A
  **sensitive** match (payday loans, gambling savings, cashing out
  retirement) still shows the estimate, with a banner above it naming who
  to talk to. Conservative phrase matching (a false positive is a kind
  message with a hotline; a false negative isn't survivable), with a
  Claude screen tried first when `ANTHROPIC_API_KEY` is set and the phrase
  matcher as fallback. Crisis notes are held out of the forecast,
  calibration, triggers, debt, and mental-load accounting.
- **Compare options** (`backend/app/options.py`, `POST /decisions` with an
  `options` list, `frontend` composer + `OptionsBox`): a decision doesn't
  have to be yes/no. Give Choicely 2-4 alternatives and each one is run
  through the full cold-start pipeline on its own -- classified for its
  type, matched to a population prior, adjusted for planning style and
  personality, blended with any personal history for that category -- so
  every option gets its own regret estimate and the lowest is Choicely's
  lean. Recording the outcome takes a `chosen_option`; at that point the
  decision *adopts* that option (`models.adopt_chosen_option`) -- it takes
  on the chosen category and estimate and from then on behaves like an
  ordinary resolved decision (shows in the forecast, feeds calibration).
- **Demo clock** (`POST /demo/advance`, `frontend/src/DemoControls.jsx`):
  a bottom-right control that rewinds every decision's clock by 1 or 3
  days so pending check-ins come due on stage. Demo aid only -- shown when
  running the dev server, or with `?demo` in the URL; hidden otherwise.
- **Theme**: three-state light/dark/system toggle (`ThemeToggle.jsx`),
  persisted to `localStorage`.
- **Design system** (`frontend/src/index.css`): one token set — a
  teal accent, an amber "your data" hue, cool-grey neutrals, a 4px spacing
  scale. UI text is Hanken Grotesque; Choicely's own judgments (verdicts,
  reflections, auto-resolve answers, the game-theory breakdown) are set in
  Newsreader; every number is IBM Plex Mono with tabular figures. Fonts
  load from Google Fonts with system fallbacks. Flat bordered surfaces, no
  drop shadows except the floating demo control. Full light/dark parity.

The demo seed (`seed_demo_data.py`) now also creates the persona profile
("Maya") and inserts her history as normal decisions (not flagged
demo/seed), so it flows through mental-load, forecast, and debt views the
way a real user's data would.

## What's built (steps 1-8 of the build plan -- feature-complete)

- Decision capture + classification (type / stakes / urgency)
- SQLite storage (`backend/data/choicely.db`, auto-created)
- Cold-start dataset lookup: `backend/data/reference_dataset.json` is a
  synthetic-but-labeled "population prior" dataset (documented as such, not
  real personal data) that gets matched against each new decision by type
  and keyword (whole-word matched, see `dataset.py`) to produce a "general
  pattern" suggestion
- Regret-prediction + prior-to-personal blending (`backend/app/regret.py`),
  keyed by the matched dataset category (e.g. "skipping exercise" vs.
  "skipping meals" build separate personal signals even though both are
  `health` decisions):
  - 1st decision ever: no prediction shown, just a "logged, I'll check back"
    confirmation (`source: "cold_start"`)
  - Subsequent decisions with no personal outcomes yet for that category:
    dataset prior only (`source: "dataset_prior"`)
  - Once outcomes are recorded for a category: `confidence = min(1, personal_data_points / 10)`,
    `blended = (1 - confidence) * prior + confidence * personal` (`source: "blended"`,
    or `"personal"` once confidence hits 1.0)
  - Single-tap outcome feedback (good/neutral/regret) on each decision card
    feeds back into future personal estimates for that category
- Game-theoretic interpersonal breakdown (`backend/app/gametheory.py`):
  triggers automatically when a decision classifies as `interpersonal` --
  what you likely want, what they likely want, and the best move if they
  react well or poorly. Real Claude call when `ANTHROPIC_API_KEY` is set,
  templated fallback otherwise.
- Decision debt dashboard (`backend/app/debt.py`, `GET /dashboard`):
  matches new decisions against past unresolved ones by word-overlap
  similarity; decisions logged 2+ times with no outcome ever recorded show
  up as a reopened-without-deciding callout.
- Auto-resolve: once confidence hits 1.0 for a category and the regret rate
  is strongly one-sided (>=65% or <=20%), the system answers directly
  instead of predicting a probability, e.g. "You always regret skipping
  meals, so: eat something."
- Demo seed data: `backend/seed_demo_data.py` backfills three things so all
  of the above are demoable live without waiting on real elapsed time:
  5 "skip the workout" decisions (confidence 50%, shows blending mid-flight),
  10 "skip breakfast" decisions mostly regretted (confidence 100%, triggers
  auto-resolve), and 4 repeated undecided "should I quit this club" entries
  (shows up on the decision-debt dashboard).
  Run it once before demoing: `python seed_demo_data.py` (from `backend/`,
  with the venv active) -- delete `backend/data/choicely.db` first for a
  clean slate, since it re-seeds on top of whatever's already there.
- Onboarding survey (`backend/app/profile.py`, `frontend/src/Onboarding.jsx`):
  on first open (no saved profile), the app asks for a name and a 5-question
  spontaneous-vs-planner survey before showing the main screen. The result
  (`planning_score`, 0=spontaneous to 1=planner) nudges the *population*
  prior toward what's statistically likelier for that kind of person, before
  any personal outcome data exists -- a third cold-start tier sitting
  between the raw dataset prior and real personal blending:
  `dataset prior -> profile-adjusted prior -> blended -> personal`
  (`source: "profile_prior"`, shown as "General pattern, tuned to your
  style"). Each dataset category is tagged `planning_alignment` (+1 if the
  measured action is spontaneous-leaning, e.g. skipping/canceling/avoiding;
  -1 if planner-leaning, e.g. saving/following through; `null` on the
  general catch-all categories, which are left unadjusted). The shift is
  capped at +-15 percentage points and deliberately never feeds auto-resolve
  -- a 5-question survey is too coarse a signal to answer a decision
  outright; only real outcome history can do that.
