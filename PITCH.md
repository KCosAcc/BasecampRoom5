# PITCH.md

Six lines and a lever. Your words. The last two are scored.

Built: A Larkspur Airlines disruption-care agent on the Claude Messages API — a tool-use loop with 9 core tools, a local reopen_stats function, and an MCP-served next_available_day tool, capped at 8 tool calls before human handoff.

Does: Resolves a disruption contact in 3–4 API turns: looks up the booking, checks live flight status, applies the correct entitlement policy, and either confirms a rebooking path or routes to a human — without offering care the policy does not authorise.

Number: 5 disruption shapes, all resolved at end_turn, 0 loop failures; 19 total turns, 14 tool calls, avg 3.8 turns and ~14 seconds per case; fastest close was 10.5s (missed connection), slowest 25s (clean cancellation).

Guardrail: MAX_TOOL_CALLS = 8 caps runaway loops and hands off to escalate_to_human; check_policy returns a prohibited-wording list (no "guaranteed", "compensation is owed"); group, partner-segment, and unaccompanied-minor bookings route to specialist queues before any entitlement is offered.

Next: Build 4 — author TONE_ADDENDUM to classify abusive messages and legal threats before policy lookup runs, so they escalate instead of resolve.

Still broken: R8KD3F (abusive message + legal threat) resolves as a normal delay case — the agent calls check_policy and offers entitlements rather than escalating. TONE_ADDENDUM is empty.

Lever: cost

## Priya asked

Costs: ~$0.047 per disruption contact (avg 12,262 input tokens at $3/1M + 650 output tokens at $15/1M); fare_rules excluded from the tool list each turn to keep schema overhead lean. At ~250 contacts/hour per instance, a 500-contact DEN ground stop costs ~$24 in API spend.

Wrong: Abusive contacts and legal threats resolve as normal policy cases — R8KD3F is the live example. 100% resolution rate is on 5 tested shapes; it is not a production claim.

Runs it: An IROPs team handling hundreds of cancellation contacts during a ground stop — anyone who needs to triage at scale without a staff surge. Human tier-1 contacts run $8–12 fully loaded; this runs at ~$0.047, roughly 200× cheaper, and answers in 14 seconds vs. a 30–60 minute hold queue.

Left out: Tone detection (TONE_ADDENDUM empty), refund execution (human-only by policy), partner-segment rebooking, group contract changes, multi-turn conversation memory.
