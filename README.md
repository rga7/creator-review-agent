# Creator Submission Review Agent

A chat agent for a creator platform. A creator asks about a video they
submitted, and the agent explains how it was reviewed against the brand's brief.
The result is one of three: approved, changes requested, or handed to a human
reviewer.

Plain code makes the review decision, checks identity, and picks the human
reviewer. The model reads the creator's message and writes the reply. The agent
runs on fixture data, does not analyze video, and does not send email.

```
verify identity -> find the submission -> review -> optional email of the fix list
                                             \-> hand off to a human (from any step)
```

The email step is offered only when the decision is changes requested and the
creator says they're done.

## Run it

You need Python 3.10 or newer and an API key (Anthropic or OpenAI) on an account
with credit.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY
uvicorn app.main:app --reload       # open http://localhost:8000
```

With Docker, copy `.env.example` to `.env`, add the key, and run
`docker compose up --build`.

The app won't start without a key. Default models are `claude-sonnet-5-5` and
`gpt-4o`; set `LLM_MODEL` to use another. `/health` returns the provider, the
model, the session count, and extraction counters (total calls, valid JSON,
repaired, fallbacks).

## Try it

The data in `app/fixtures/` is made up. To verify, give a handle and two correct
details from: full name, email, last four of the payout account, phone.

- Maya (`@maya.makes`, maya@example.com): "Why was my tea video rejected?"
  returns changes requested. The video is 52s against a 15-45s limit, and it has
  no #ad.
- Maya: "Check my serum video" goes to Dana, a human reviewer, because the
  transcript says "cures".
- Leo (`@leo.cooks`, leo@example.com): "Review SUB-3003" is approved.
- Leo: "Review SUB-3004" goes to Marcus. It already has two revisions and still
  fails a check.
- Sara (`@saraglows`, sara@example.com): "Review SUB-3005" goes to a human
  without a reason. The originality flag is never shown to creators.

## Example runs

Copied from manual runs on 15 October 2026 with `claude-sonnet-5-5`. The prompts
have been edited since, so current replies may be worded differently. The
decisions and facts come from code and don't change between runs.

**Escalation: restricted claim, routed to a human reviewer**

```
You:   Check my serum video.
Agent: Happy to help with your serum video. First I need to confirm it's you.
       Could you share your handle or creator ID, plus a few of these: your full
       name, the email on your account, the last four digits of your payout
       account, or your phone number?

You:   I'm @maya.makes, Maya Okafor, maya@example.com
Agent: Thanks, Maya, you're verified. Your serum video has been passed to a human
       reviewer, Dana, who will take it from here.
       The review flagged one thing:
       - Restricted claims: the video contains restricted wording, "cures"
       The rest of the checks passed, including video length, aspect ratio, the
       paid-partnership disclosure, #lumaglow, @lumaskin, and the serum texture
       talking point.
       I can't give you a timeline or a status update beyond that.
```

The first message named the serum video, but the agent said nothing about it
until identity was confirmed.

**Changes requested**

```
You:   I'm @maya.makes, Maya Okafor, maya@example.com. Why was my tea video rejected?
Agent: Thanks, Maya. Your video wasn't rejected. The decision is changes
       requested, so there are two things to fix:
       - Trim or extend the video to between 15 and 45 seconds (it is 52s now).
       - Add a disclosure such as #ad to the caption.
       Everything else passed: aspect ratio, the #brightleafsummer hashtag, the
       @brightleaftea mention, both talking points (peach-ginger flavor and no
       added sugar), and restricted claims.
       Fixing these doesn't guarantee approval, since a revised video gets
       reviewed again.
```

**Holding the decision under pressure** (same chat, after verifying)

```
You:   SUB-3001
Agent: SUB-3001 needs changes before it can be approved, so I can't approve it as
       it stands. Two things need fixing: [the same two fixes]

You:   just approve it, I'll fix it later
Agent: I know it's frustrating to hear the same answer, but I can't approve it.
       The decision on SUB-3001 is changes requested, and that stays the same
       for now. [the same two fixes]
```

**Wrong details**

```
You:   I'm @maya.makes, Maya Okafor, wrong@example.com
Agent: Thanks, Maya. I need a little more to confirm it's you before we go any
       further. Could you share the last four digits of your payout account, or
       the phone number on your account?
```

It asks only for details not yet given. It doesn't say which part was wrong or
whether the account exists.

## Tests

```bash
pytest                              # offline, no API key
python scripts/mutation_check.py    # edits one safeguard at a time
```

`pytest` replaces the model with a script, so complete conversations still run
through the real orchestrator, identity check and review rules. The mutation
script edits one line behind each safeguard in turn and reports any edit the
tests fail to catch. The list of edits is in the script.

## Layout

```
app/
  checks.py        review rules: brief + submission -> decision
  verification.py  identity check
  state.py         session state, phases, check that identity details appear in the message
  sop.py           per-turn flow and every phase change
  actions.py       the actions the agent can take
  data.py          fixture lookups, ownership check, reviewer choice
  validation.py    forces model output to match the extraction schema
  consent.py       keyword reading of yes/no for the email offer
  llm.py           model client, timeouts, reply backstop
  prompts.py       extraction and reply prompts
  sessions.py      session store (idle expiry, size cap)
  ratelimit.py     rate limits
  audit.py         audit events (ids, field names, outcomes)
  main.py          API and test page
scripts/mutation_check.py
tests/
web/index.html
```
