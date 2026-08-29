# Choicely — demo run of show

Target: ~4 minutes. One presenter, one screen.

## Setup (before judges are watching)

1. Backend up on :8000 — from `backend/`, venv active:
   `uvicorn app.main:app --port 8000` (no `--reload` on Windows)
2. Frontend up on :5173 — from `frontend/`: `npm run dev`
3. Clean the demo state: `python seed_demo_data.py --reset` (from `backend/`,
   works with the backend running)
4. Browser at http://localhost:5173, **Timeline** tab, zoomed to ~110%.
5. Pick a theme and stick with it (toggle is top-right of the header).
6. *(Optional, for the push beat)* Settings (top-right, click the name) →
   **Check-in reminders** → **Turn on**, allow the browser prompt. Then
   **Send test** to confirm a notification actually shows on this machine.
   Web Push needs `localhost` or HTTPS and a Chromium/Firefox browser;
   if it won't grant, skip the push beat — the in-app banner still lands.

Maya is pre-seeded: a planner who over-deliberates, ~2 weeks of history,
two decisions with a check-in almost due.

## Runtime

| Time | Beat | Do | Say |
|------|------|----|-----|
| 0:00 | Hook | (app idle) | "You make about 35,000 decisions a day. Most aren't hard — they're just *heavy*. Should I skip the gym. Should I text her back. We carry hundreds of these half-open, and it's exhausting. Choicely is a second brain for the decisions you're tired of carrying." |
| 0:25 | Mental load | Point at the banner at the top of the timeline | "This is Maya. The first thing she sees isn't a to-do list — it's what Choicely carried for her this week. Five decisions off her plate. Twelve loops closed. One still open. The metric is her mental load, not her output." |
| 0:55 | Auto-resolve | Type `should I skip breakfast today` → **Log it** | "Watch what happens with one Choicely already understands." *(card appears)* "It doesn't ask — it answers: *You always regret skipping meals, so: eat something.* She's logged this ten times. It's not a decision anymore, so Choicely takes it off her." |
| 1:35 | The forecast | **Regret forecast** tab → the *skipping meals* card | "Here's why it's allowed to do that. Every category starts at the population average — 71%. Choicely nudges that with Maya's onboarding answers — planner, hates missing out — 77%, then 82% (that's the staircase on the left). Then her own outcomes take over and the real number is 90%. The shaded band is a 95% interval — it genuinely narrows as the estimate earns its keep." |
| 2:10 | …opposite cases | Scroll through *going out despite low energy* and *skipping exercise* | "Same machine, opposite conclusions. Everyone — and her profile — expected her to regret forcing herself out, and skipping workouts. Her actual history says she's glad she went, and fine skipping. Population data alone would have told her the wrong thing about her own life — twice." |
| 2:35 | Proactive check-in | **Timeline** tab → **+1 day** (bottom-right control) | "Now a day goes by." *(check-in banner appears; if push is on, a notification fires too)* "Choicely came back on its own — even if the tab was closed. *How did the party go? How did replying to your sister land?* You don't have to remember to reflect — it brings the loop back to you." |
| 3:05 | Close a loop | Click **Went well** on the party check-in | "One tap. That outcome just fed her forecast." |
| 3:15 | Reflection | Point at the Reflection card | "And it notices what a thoughtful friend would. *You keep asking yourself about skipping meals.* *One question keeps coming back unanswered* — the club, four times, no decision. And always one thing she's getting right: *You can trust your gut on pushing yourself to go out.*" |
| 3:45 | Close | (app idle) | "Decision fatigue is a real tax on mental health. Choicely doesn't try to make you a better decision-maker. It carries the ones you shouldn't have to — population wisdom when you're new, your own patterns when you're not, and it always checks back." |

### Optional beat — it's a real app (use if asked "is this just a web page?")

Install it: browser menu → **Install Choicely** (or "Add to Home Screen").
It opens standalone, no address bar. "Check-ins reach you the way any app's
notifications do — this isn't a tab you have to keep open." The **+1 day**
control then fires an actual OS notification.

### Optional beat — track record (use if asked "how do you know the predictions are any good?")

**Track record** tab. "Choicely keeps score of its own predictions. Every
decision Maya closed the loop on, scored against what actually happened.
The honest read: when Choicely was confident enough to say 75%+, she
regretted it 90% of the time — 10 for 10. That's the only range it will
answer a decision outright in. Its middle-confidence guesses are looser,
and it shows you that too — the reliability curve doesn't hide the misses."

Then scroll to **When regret clusters** at the bottom: "It also looks at
what was going on *around* the decision, not just what kind it was. For
Maya: her morning decisions — the on-the-way-out-the-door ones — go
sideways 90% of the time, against 20% the rest of the day. Her evening
calls are the opposite. It checked time pressure, busy days, and
back-and-forth too; time of day is what moved the needle for her."

### Optional beat — comparing options (use if asked "what if it's not yes/no?")

On the timeline, the **"the weekend trip"** card. "Not every decision is
yes/no. Here Maya's weighing three ways to handle the weekend. Choicely
runs each one through the same machine — go for the whole thing reads at
29% regret for her, just Saturday at 35%, skipping at 76%, because her
history says she rarely regrets pushing herself out and her profile says
skipping is the risky move. It leans toward going. When she records which
one she picked, that option becomes the decision — it flows into the
forecast for that category like any other."

### Optional beat — interpersonal (use if asked "what about hard decisions with other people?")

Type `should I bring up the noise thing with my roommate` → **Log it**. The card
shows a structured breakdown — *what you want*, *what they likely want*, *the
move if they react well / badly* — tuned to Maya's conflict style (avoidant, so
the advice is a concrete low-friction script, not "just be direct"). The seeded
"reply to my sister" check-in carries the same breakdown once answered.

## If a judge asks

- **Is the dataset real?** It's a documented synthetic population prior
  (`backend/data/reference_dataset.json`, figures inspired by behavioral-psych
  findings on regret). The blend logic takes real aggregate data as a drop-in
  — nothing about the architecture changes.
- **How accurate is it?** The **Track record** tab scores every past
  prediction against the recorded outcome. Overall per-decision error is
  large by nature (a probability vs. a yes/no result), so the honest metric
  is group calibration: at the high-confidence end — the only place it
  auto-answers — predictions hold up (75%+ → 90% actual on the demo data).
  It surfaces its weak spots (mid-range guesses) rather than hiding them.
- **Where's the AI?** Claude does the decision classification, the
  game-theory breakdown for interpersonal decisions, and writes the weekly
  reflection. Each has a heuristic fallback, so it runs with no API key.
- **Isn't auto-answering risky?** It never auto-resolves until 10+ of *your*
  recorded outcomes **and** a lopsided signal (≥65% or ≤20% regret). Below
  that it shows a probability, never a verdict. The onboarding survey can
  never trigger it.
- **Privacy?** Local SQLite. Nothing leaves the machine except the
  classification call (and only if a key is set) and the Web Push envelope
  (endpoint + encrypted payload) when notifications are on.
- **What's next?** Calendar hooks (pre-empt decisions before events),
  regret-trigger analysis ("you regret decisions made after 10pm"), and
  shared decisions for the interpersonal ones (both parties' game theory).

## If something breaks

- **Check-ins didn't appear** → click **+1 day** again (the seeded pending
  decisions are ~26–30h out).
- **Numbers look off** → `python seed_demo_data.py --reset`, refresh the page.
- **Backend down** → restart `uvicorn app.main:app --port 8000` from
  `backend/`. Don't use `--reload` on Windows — it can orphan the port.
- **Frontend can't reach the API** → check it's on :8000; override with
  `frontend/.env.local` → `VITE_API_BASE=http://localhost:PORT`.
