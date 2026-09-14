# Choicely — Devpost submission

Copy each section below straight into the matching Devpost field. Everything
is written the way I'd actually explain it to someone, not as marketing copy
— edit anything that doesn't sound like you before you post it.

**Tagline** (Devpost's short one-liner field):
> A second brain for the decisions you're tired of carrying.

Try it out: _<paste your live URL here, or remove this line if you're not deploying>_
GitHub: _<paste your repo URL here>_
Video demo: _<paste your video link here>_

---

## Inspiration

Most of what wears me out in a day isn't the big decisions. It's the small
ones that never really get closed: should I skip the gym again, should I
finally text her back, should I just quit that club I've been half-attending
for six months. None of those are hard, exactly — I've usually already
"decided" them a dozen times in my head. I just never let myself off the
hook, so they sit there, half-open, taking up space.

I wanted to build something that would actually carry that weight instead of
just tracking it. Not a to-do list, not a journal — something that notices
when I've effectively already made a call and just tells me, follows up on
the ones I never got back to, and, when I dump a real messy problem on it,
actually reasons about it using what it knows about *my* history instead of
handing me a generic pep talk. That's Choicely.

## What it does

You log a decision the way you'd say it out loud — "should I skip breakfast
again," "should I quit this club" — and Choicely goes to work on it:

- It **classifies** the decision and estimates how much you'll regret it,
  starting from a population average and blending in your own recorded
  outcomes for that exact kind of call as you build up history.
- Once it's genuinely sure — enough of *your* outcomes, lopsided enough one
  way — it **just answers**: "You always regret skipping meals, so: eat
  something." No probability, no hedge. It only does this when the evidence
  is real, never on a first guess.
- It **checks back on its own.** Every decision gets a rough "this should
  have played out by now" timer, and when it fires, Choicely asks how it
  landed — even if you never open the app that day.
- It **notices patterns** you probably haven't put into words yourself:
  "your morning decisions go sideways 90% of the time, your evenings are the
  opposite," or "you keep logging the same question and never deciding it."
- If you're actually stuck on something, there's a **grounded debrief**:
  dump the messy paragraph you'd normally text a friend, and it reads it
  back — the real question underneath, what's actually at stake, your
  options, and a recommendation — with every claim tied to a number or a
  specific past decision from your own log, not a generic answer.
- And because I think "carrying your mental load" is the actual point, the
  home screen doesn't lead with decisions logged — it leads with what got
  taken *off* your plate: loops closed, questions still open, mental load
  lifted.

There's also an **Agent tab** that's just honest about all of this: it shows
you, in plain language, everything Choicely has done on its own — what it
answered outright, what it's still watching, what patterns it found — so
none of it feels like it's happening behind your back.

## How I built it

- **Backend**: FastAPI + SQLite, no ORM — I wanted to actually see the SQL I
  was writing. One connection helper handles WAL mode and cleanup so
  concurrent requests don't fight each other.
- **The regret model**: a documented synthetic population-prior dataset,
  matched to each decision by type and keywords, adjusted for the person's
  planning style and personality (from a short onboarding survey), then
  blended toward their own outcomes as more come in. Confidence climbs
  toward 1.0 as outcomes accumulate, and Choicely only auto-answers once
  it's fully confident *and* the signal is lopsided.
- **Calibration**: every closed decision's stored prediction gets scored
  against what actually happened, so the Track Record tab can show a real
  reliability curve instead of just claiming to be accurate.
- **Frontend**: React + Vite, no charting library — every chart on the
  Regret Forecast page is hand-drawn inline SVG. Near-monochrome design,
  every number monospaced, light/dark/system theming.
- **The agent log** is an append-only event table written idempotently from
  hooks on logging, recording an outcome, and the demo clock — so "what did
  the agent do" is a real audit trail, not something generated on the fly
  for show.
- Also in there: an installable PWA with real Web Push, opt-in shared
  "community" outcome priors, crisis-decision guardrails that refuse to
  score anything that reads as self-harm or a medical emergency, and a
  compare-two-to-four-options mode for the decisions that aren't yes/no.
- **Tests**: 74 pytest tests, each running against its own throwaway SQLite
  file so nothing leaks between them.

## How I used Claude

I didn't want Claude to be a chatbot bolted onto the side — I wanted it to
be the part of the app that does the thing arithmetic can't. So the model
(the regret blend, the calibration math, the pattern detection) does all the
actual computation, and Claude only ever gets handed a fixed, pre-computed
context block to reason over and write back in plain language:

1. **The grounded debrief** — the feature I'm proudest of. Everything
   Claude is allowed to say is grounded in retrieval I do myself first: the
   matching population prior, every outcome the person has recorded in that
   category, whether this exact question is already sitting unresolved in
   their log. I pin all of those numbers before Claude ever sees the
   prompt, so it's writing the *read*, not inventing the facts.
2. **The agent's backlog triage** — for every open decision, Claude decides
   whether Choicely should just answer it, keep watching it, or leave it
   alone entirely. Deciding when *not* to say anything turned out to matter
   as much as deciding what to say.
3. **Check-in questions**, written in context instead of from a template.
4. **The weekly reflection** — three specific, non-judgmental observations
   read off a compact summary of recent decisions.
5. **Classification, the game-theory breakdown** for interpersonal
   decisions (what you want vs. what they probably want), and the
   **crisis-guardrail screen** that decides when a decision shouldn't be
   scored at all.

The debrief, the agent's triage and check-in questions, and the weekly
reflection all go through one shared seam with a response cache and a
cooldown after a failure; classification, the game-theory breakdown, and the
crisis screen each call Claude directly but carry their own heuristic
fallback. Every single one of them degrades gracefully with no API key at
all — just less sharp than with one.

## Challenges I ran into

- **Keeping Claude honest.** The first version of the debrief let Claude see
  the raw decision history and it would confidently invent details that
  weren't there. The fix was architectural, not prompt-tweaking: do all the
  retrieval and all the math in Python, and only ever hand Claude a
  pre-computed, pinned context block. It writes the sentence; it doesn't get
  to make up the number inside it.
- **A slow "Log it" button that looked broken, not slow.** Late in building
  this, I noticed that logging a single decision could take 7-9 seconds —
  and the button just sat there greyed out with no explanation, so it
  genuinely looked like the app had crashed. I traced it to three or four
  Claude calls firing back-to-back inside one request (a safety check, a
  classifier, sometimes a game-theory read, then a "friendly note" on top).
  The real fix wasn't a spinner — it was admitting the friendly note didn't
  need to be in the critical path at all, moving it to a background task
  that fills in a few seconds after the card already appears. The spinner
  came after, so the wait that's left is honest about being a wait.
- **The agent tab drowning in its own noise.** Once Choicely started logging
  its own activity, a normal seed history produced 40+ near-identical
  events. I split them into "signal" events (an answer, a check-in, a
  pattern — always shown) and "routine churn" (only the last few shown),
  and collapsed a repeated question down to one entry instead of one per
  repeat.
- **Timezones, of course.** SQLite's `datetime('now')` is UTC; every other
  timestamp in the app is local wall-clock. Getting those to agree — and
  keeping the demo's fast-forward clock consistent with both — took an
  annoyingly long time for something so unglamorous.

## Accomplishments that I'm proud of

- Choicely **grades its own predictions.** The Track Record tab isn't a
  marketing claim — it's every closed decision's stored estimate checked
  against the outcome, including a reliability curve that shows exactly
  where the model is *and isn't* trustworthy. It doesn't hide its
  mid-confidence misses.
- The **agent's activity log is a real audit trail**, not a generated
  summary — every "answered outright" or "found a pattern" is a row written
  at the moment it happened, so what you see is literally what it did.
- It's **honest about not knowing.** Auto-resolve only fires once there's
  real personal history *and* a lopsided result — otherwise it shows a
  number and lets you decide. And a handful of inputs (anything reading as
  self-harm or a medical crisis) get refused a score entirely, on purpose.
- The whole thing **works with zero API key** — every Claude-backed feature
  has a genuine heuristic fallback, not a "feature unavailable" wall.
- I caught and fixed a real production-shaped bug (the slow-logging issue
  above) by actually profiling it under Playwright instead of guessing, a
  couple of days before I had to record the demo.

## What I learned

- Grounding beats prompting. The single biggest jump in how trustworthy the
  debrief felt didn't come from a better prompt — it came from refusing to
  let Claude see anything it wasn't allowed to cite.
- Perceived speed and actual speed are different bugs. A slow request with
  no feedback reads as broken; the same request with a spinner and a clear
  "logging…" reads as normal. I fixed both, but they were two different
  fixes.
- Deciding when an agent should say *nothing* is a real design problem, not
  a fallback case — "stay quiet" needed just as much care as "answer now."
- Small, honest seed data beats a big impressive-looking one. I actually cut
  a whole category out of my own demo data late in the process because two
  clean, contrasting stories were easier for a person watching to follow
  than three.

## What's next for Choicely

- A real scheduler for the agent loop — it's triggered by app activity
  today; a deployed version would run it on a cron.
- Voice-note input into the debrief (transcript in, same pipeline).
- Multi-user, with the opt-in community priors becoming an actual shared
  signal instead of a seeded starter set.
- Calendar hooks, so Choicely can catch a decision before the event it's
  attached to, not just after.

## Built With

python, fastapi, sqlite, anthropic-claude, react, vite, javascript, html5,
css3, docker, pytest, progressive-web-app, web-push
