# Design notes

## Who does what

The creator's question is almost always about one fact: what did the review
find? `checks.py` computes that once per submission and stores it. The model
never decides it.

Each turn calls the model twice. The first call turns the creator's message into
a small JSON object: identity details, submission hints, an intent, an emotion,
and a few flags. Code validates it (`validation.py`) and decides what happens
next. The second call writes the reply for the action code chose, using the
stored review as its only source of facts.

If the first call gets something wrong, the usual result is a misplaced
question, such as asking for a detail again or listing the wrong candidates. It
can't verify anyone on its own, because every identity detail has to appear in
the creator's message, and it can't change a decision, because `checks.py` makes
that without the model. If a call fails, the turn falls back to an empty
extraction (first call) or a short apology (second call).

## Review rules

`checks.py` compares a submission to its campaign brief: length, aspect ratio,
a disclosure tag (#ad or #sponsored), required hashtags and mentions, talking
points, restricted phrases, and the platform's originality flag.

- A failed length, ratio, tag, mention or talking-point check is something the
  creator can fix. The decision is changes requested.
- A restricted phrase or an originality flag goes to a human reviewer, whatever
  else passed.
- A submission that already has two revisions and still fails a fixable check
  also goes to a human. The limit doesn't stop an approval.

The originality flag is not shown to the creator, and the agent does not say
why that submission went to a human.

## Identity

A handle or creator ID finds the account. It is not proof. The creator also has
to give two correct details from: full name, email, last four of the payout
account, phone.

- A detail the model extracted is accepted only if it appears in the creator's
  message.
- The reply never says which details were right, and it is the same whether or
  not the account exists.
- A turn that offers identity details and doesn't verify counts as a failure.
  Five failures end the session's chat and hand it to a human. Correct details
  sent afterwards don't undo that.
- Fifteen failures from one IP address in 15 minutes make `/chat` return 429
  for that address until the window clears.
- A creator can only open their own submissions. An ID that belongs to someone
  else gets the same reply as one that doesn't exist.

## Handing off to a person

A handoff lasts for the rest of the session. The triggers:

- the creator asks for a person
- a restricted phrase, an originality flag, or the revision limit
- five failed identity turns
- three turns in a row labeled frustrated, angry or anxious
- three out-of-scope turns in a row
- the checklist email can't be sent because the account has no email address

For a blocked or over-limit review, the reviewer is the specialist for that
campaign category with the highest agreement rate with past decisions. The
agreement rates are fixture data.

## Email

The checklist is offered only for a changes-requested decision, after the
creator says they're done. To send, the reply has to read as a plain yes. When
the model returned a reading, the keyword check in `consent.py` has to agree, so
"yes, send it tomorrow", "yes, but only if..." and questions don't send. When
the model returned none, the keyword check decides alone.

The address comes from the account record. In this demo nothing is sent: the
agent says so and shows the checklist in the chat.

## Reply backstop

After the model writes a reply, `llm.py` checks it and appends what is missing:

- the decision, stated in words that fit it ("no changes needed" doesn't count
  as requesting changes)
- every required fix
- on a handoff, the reviewer's name and the flagged wording
- in demo mode, a note that no email was sent, plus the checklist

It only adds text. If the model writes a sentence that contradicts the
decision, the backstop can't remove it.

## Prompt layout

The turn's instructions and facts are in the system prompt. The creator's
message goes in alone. Earlier, the instructions were appended to the creator's
message, and the model treated them as an injection and refused them.

## Defaults

- Model calls: 30 s timeout, 2 retries. The reply call sees up to the last 6 messages.
- Sessions: 30 minutes idle, at most 5,000 held at once.
- Requests: messages up to 2,000 characters, 60 per minute per IP, 30 per
  minute per session.
- Audit events go to stderr as one JSON object per line.

## Not done

- Only a handful of conversations have been run against the real model.
  Extraction accuracy hasn't been measured.
- It doesn't watch video. It uses the duration, ratio, caption, tags and
  transcript the platform already has. A real version needs video analysis
  ahead of `checks.py`.
- Email isn't sent.
- Sessions, rate limits and audit output live in one process. Running several
  workers needs a shared store and somewhere durable for the audit events.
- Reviewer choice is a fixed rule, not learned.
