"""Larkspur disruption agent. This is the file you build.

It runs right now, and it is wrong in four places. The trace shows each one
before the code does, so read the trace first:

    python3 run.py K7PQ2M --trace

Where you edit:   grep -n '✏' agent.py   (six marks, one per place)
Steps and gates:  https://anthropicpartnerbasecamp.bts.com/
"""
from __future__ import annotations
# [Room 5] 2.1: added json, pathlib — were not imported; required by reopen_stats to read transcripts_sample.jsonl
import json, pathlib
from typing import Any, Dict, List
from support import (MODEL, SYSTEM_PROMPT, call_local, execute_tool, mcp_client,
                     new_session, record_tool_result, runtime_preamble)

# [Room 5] 2.1: added reopen_stats — was not present; reads data/americas/transcripts_sample.jsonl
#               to return 72-hour reopen rate for contacts matching a given shape
_TRANSCRIPTS = pathlib.Path(__file__).parent / "data" / "americas" / "transcripts_sample.jsonl"

def reopen_stats(intent_label: str = "", cause_code: str = "", fare_family: str = "") -> dict:
    """Return the historical 72-hour reopen rate for transcripts matching this shape."""
    total = reopened = 0
    with _TRANSCRIPTS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if intent_label and rec.get("intent_label") != intent_label:
                continue
            if cause_code and rec.get("disruption", {}).get("cause_code") != cause_code:
                continue
            if fare_family and rec.get("fare_family") != fare_family:
                continue
            total += 1
            if rec.get("reopened_within_72h"):
                reopened += 1
    if total == 0:
        return {"total": 0, "reopened": 0, "reopen_rate": None,
                "note": "No transcripts matched this shape."}
    return {"total": total, "reopened": reopened,
            "reopen_rate": round(reopened / total, 3)}

MAX_TOOL_CALLS = 8  # Larkspur's own build capped the loop here; then a human takes over.

TONE_ADDENDUM = ""                       # ✏️ Build 4, step 4.1, intelligence lane
# [Room 5] EXTRA_TOOLS: schemas Claude sees on every call. The description is the routing
# signal — it's the only thing that steers Claude toward this tool vs. search_alternatives.
# The floor is 40 chars; the gate checks this before it runs any conversation.
# [Room 5] next_available_day removed from EXTRA_TOOLS at step 2.2: it now lives in
# mcp_server.py and is discovered at runtime via tool_list(). reopen_stats stays here
# because it is not in the MCP server.
EXTRA_TOOLS: List[Dict[str, Any]] = [   # ✏️ Build 2, step 2.1: schemas for the tools you add
    # [Room 5] 2.2: next_available_day schema removed from EXTRA_TOOLS → now served by MCP (duplicate routing otherwise)
    # [Room 5] 2.2: fare_rules is also served by MCP — schema injected by mcp_client.tools() in tool_list(); no local copy needed
    # {
    #     "name": "next_available_day",
    #     "description": (
    #         "Checks the earliest available alternative flight date when the customer "
    #         "is prioritising speed or urgency. Call this after lookup_booking has "
    #         "returned the segment details (origin, dest, date, cabin). Returns the "
    #         "soonest date with a seat, or null if none found."
    #     ),
    #     "input_schema": {
    #         "type": "object",
    #         "properties": {
    #             "origin": {"type": "string"},
    #             "dest": {"type": "string"},
    #             "date": {"type": "string", "description": "YYYY-MM-DD"},
    #             "cabin": {"type": "string"},
    #             "pax_count": {"type": "integer"},
    #         },
    #         "required": ["origin", "dest", "date", "cabin"],
    #     },
    # },
    # [Room 5] 2.1: added reopen_stats schema to EXTRA_TOOLS — was not present; routes Claude to the local function
    {
        "name": "reopen_stats",
        "description": (
            "Look up the historical 72-hour reopen rate for disruption contacts that "
            "match this case's shape: intent, cause code, and fare family. Call this "
            "when the policy or tone of a resolution might leave unresolved questions "
            "— e.g. to flag that refund contacts on Basic fares reopen at a high rate "
            "and the customer should receive a reference number. Returns total matching "
            "transcripts, how many reopened within 72 hours, and the reopen rate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intent_label": {"type": "string",
                    "description": "e.g. rebook_after_cancellation, compensation_hotel_request"},
                "cause_code": {"type": "string", "enum": ["WX", "ATC", "MX", "CREW", "SEC"]},
                "fare_family": {"type": "string",
                    "description": "Basic, Main, or Main Plus — from the booking"},
            },
            "required": [],
        },
    },
]

# [Room 5] LOCAL_TOOLS: maps tool name → Python function. tool_results() checks this dict
# before falling through to support/tools.py. Without this entry, every call to
# next_available_day returns an error and the gate never sees a successful invocation.
LOCAL_TOOLS: Dict[str, Any] = {         # ✏️ Build 2, step 2.1: the functions behind them
    # [Room 5] 2.2: next_available_day removed from LOCAL_TOOLS → was "next_available_day": next_available_day; now dispatched via mcp_client
    # "next_available_day": next_available_day,
    # [Room 5] 2.1: added reopen_stats — was not present; needed so tool_results() dispatches calls to the local function
    "reopen_stats": reopen_stats,
}


def text_of(response) -> str:
    """Given. The last non-empty text block, never content[0]."""
    texts = [b.text for b in response.content if getattr(b, "type", None) == "text" and b.text]
    return texts[-1] if texts else ""


def tool_results(response) -> List[Dict[str, Any]]:
    """Given. Runs every tool_use block and packages the results the way the
    API expects them back. A tool can live in three places: the MCP server,
    LOCAL_TOOLS, or support/tools.py."""
    # three branches, no try/except in this file: mcp_client.call_remote() and
    # support.call_local() answer with an error dict instead of raising, and both
    # record what came back on the trace
    results = []
    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if block.name in mcp_client.tool_names:
            output = mcp_client.call_remote(block.name, block.input)
        elif block.name in LOCAL_TOOLS:
            output = call_local(LOCAL_TOOLS[block.name], block.name, block.input)
        else:
            output = execute_tool(block.name, block.input)
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": str(output),
        })
    return results


def run_agent(pnr: str, last_name: str, message: str) -> str:            # ✏️ Build 1, step 1.2
    """Run the tool loop until Claude stops asking for tools. Return its final text."""
    client, tracer = new_session()
    tools = tool_list()
    messages = [
        {"role": "user", "content": f"PNR {pnr}, last name {last_name}. {message}"},
    ]

    response = client.messages.create(
        model=MODEL, max_tokens=4096, system=runtime_preamble() + SYSTEM_PROMPT + TONE_ADDENDUM,
        thinking={"type": "adaptive"}, tools=tools, messages=messages,
    )

    answer = ""
    turns = 1
    while response.stop_reason == "tool_use" and turns < MAX_TOOL_CALLS:
        # [Room 5] 1.2: was text_of(response) → response.content (must include tool_use + thinking blocks, not just text)
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results(response)})
        answer = text_of(response)
        response = client.messages.create(
            model=MODEL, max_tokens=4096, system=runtime_preamble() + SYSTEM_PROMPT + TONE_ADDENDUM,
            thinking={"type": "adaptive"}, tools=tools, messages=messages,
        )
        turns += 1

    # [Room 5] 1.2: added — was missing, causing return "" (final response text only available after loop exits)
    answer = text_of(response)
    return answer


def tool_list() -> List[Dict[str, Any]]:                   # ✏️ Build 2, step 2.2
    """Given. Exactly what Claude is offered on every turn; run.py --show-tools
    prints this list."""
    # [Room 5] 2.2: added mcp_client.tools() so MCP-served tools are included.
    # fare_rules excluded: routing trigger requires a customer dispute, which never
    # occurs in probe conversations. Re-add by adding "fare_rules" to this set.
    _mcp_allowed = {"next_available_day"}
    return build_tools() + EXTRA_TOOLS + [t for t in mcp_client.tools() if t["name"] in _mcp_allowed]


# ──────────────────────────────────────────────────────────────────────────────
# Below this line: what Claude is told about each tool. Step 1.3.
# The functions these describe are written and correct, in support/tools.py.
# ──────────────────────────────────────────────────────────────────────────────
def build_tools() -> List[Dict[str, Any]]:                 # ✏️ Build 1, step 1.3
    """Anthropic-shaped schemas: name, description, input_schema. What Claude is
    told about each of the nine tools, and all it is ever told."""
    return [
        {
            "name": "lookup_booking",
            "description": (
                "Retrieve a Larkspur reservation from Altura by confirmation code (PNR) "
                "and the passenger's last name. Both are required to prevent a lookup on "
                "a guessed PNR. Returns fare family, loyalty tier, the segment that needs "
                "attention, and any group/partner/minor/SSR flags relevant to scope."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"pnr": {"type": "string"}, "last_name": {"type": "string"}},
                "required": ["pnr", "last_name"],
            },
        },
        {
            "name": "get_flight_status",
            "description": (
                "Look up a Larkspur or Larkspur Link flight's current OpsFeed status for "
                "one local date: status, delay minutes, and cause. Use this before telling "
                "a customer anything about a flight's timing; never state it from memory."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "flight_no": {"type": "string"},
                    # [Room 5] 1.3: was "MM/DD/YYYY" → "YYYY-MM-DD" (backend rejects non-ISO format)
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["flight_no", "date"],
            },
        },
        # [Room 5] 1.3: description was "search" → full routing description (one word gave Claude no routing signal)
        {
            "name": "search_alternatives",
            "description": (
                "Find available Larkspur rebooking options for a disrupted passenger. "
                "Call this after get_flight_status has confirmed the disruption and before "
                "offering any specific flight to the customer. Returns a list of alternatives "
                "with option_ids that hold_seat and confirm_rebooking require."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"pnr": {"type": "string"}},
                "required": ["pnr"],
            },
        },
        {
            "name": "check_policy",
            "description": (
                "Resolve what Larkspur owes this customer for the disruption: rebooking "
                "waiver, refund path, meal/hotel/ground care, goodwill eligibility and cap, "
                "and any escalation triggers. cause_code, delay_minutes and status describe "
                "what get_flight_status told you; fare_family, loyalty_tier and whether this "
                "is overnight are looked up from the booking, not asked of you. Every "
                "response carries a policy_row_id. Cite it if you reference this decision "
                "again."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pnr": {"type": "string"},
                    "cause_code": {"type": "string", "enum": ["WX", "ATC", "MX", "CREW", "SEC"]},
                    "delay_minutes": {"type": "integer"},
                    "status": {"type": "string", "enum": ["ON_TIME", "DELAYED", "CANCELLED", "DIVERTED"]},
                    "wait_minutes_for_alternative": {"type": "integer"},
                    "chosen_option_id": {"type": "string"},
                },
                "required": ["pnr", "cause_code", "delay_minutes", "status"],
            },
        },
        {
            "name": "hold_seat",
            "description": "Place a 15-minute hold on one alternative. Reversible. It simply expires.",
            "input_schema": {
                "type": "object",
                "properties": {"option_id": {"type": "string"}, "pnr": {"type": "string"}},
                "required": ["option_id", "pnr"],
            },
        },
        {
            "name": "confirm_rebooking",
            "description": (
                "Finalize a held seat. Irreversible. Requires a confirmation_token that "
                "only the customer's own Confirm-click can produce. You cannot supply it "
                "yourself, and 'the customer said yes' in chat does not substitute for it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"hold_id": {"type": "string"}, "confirmation_token": {"type": "string"}},
                "required": ["hold_id", "confirmation_token"],
            },
        },
        {
            "name": "issue_voucher",
            "description": (
                "Issue a meal, ground, hotel, or goodwill voucher. Auto-approves within the "
                "policy's threshold for that type; above it, returns a pending status for a "
                "human. It does not fail. Always pass the policy_row_id that made it eligible."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "voucher_type": {"type": "string", "enum": ["meal", "ground", "hotel", "goodwill"]},
                    "amount_usd": {"type": "number"},
                    "pnr": {"type": "string"},
                    "policy_row_id": {"type": "string"},
                },
                "required": ["voucher_type", "amount_usd", "pnr", "policy_row_id"],
            },
        },
        {
            "name": "escalate_to_human",
            "description": (
                "Hand this conversation to a human, with your reasoning attached. Use for "
                "groups, partner segments, unaccompanied minors, refunds, or anything else "
                "out of scope. This is the correct outcome for those cases, not a failure."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pnr": {"type": "string"}, "reason": {"type": "string"},
                    "summary_for_human": {"type": "string"}, "queue": {"type": "string"},
                },
                "required": ["pnr", "reason", "summary_for_human"],
            },
        },
        {
            "name": "send_confirmation",
            "description": "Send the customer a written confirmation of what was just done. Benign.",
            "input_schema": {
                "type": "object",
                "properties": {"pnr": {"type": "string"}, "message": {"type": "string"}},
                "required": ["pnr", "message"],
            },
        },
    ]
