"""The search agent.

The model does not get the whole database. It gets TOOLS and decides what to
call, like a person searching:

  search_screenshots       keyword + date search over the descriptions
  list_recent              newest screenshots in a date range
  get_screenshot_details   full record (including visible text) of one screenshot
  look_at_screenshot       re-open the REAL image and ask the vision model a question

If the provider or model cannot do tool calling, it falls back to a simpler
"model writes keywords, we search" mode so the app still works.
"""
import json
from datetime import datetime
from pathlib import Path

import config
import llm

SYSTEM = (
    "You are Screen Memory, a search agent over the user's personal screenshot database. "
    "Each screenshot has an id, date, title, description, visible text and tags, written earlier "
    "by a vision model.\n"
    "How to work:\n"
    "- Use tools to find screenshots. Call search_screenshots with several relevant keywords AND "
    "synonyms (single words). Use since/until when the user mentions time. If nothing is found, "
    "retry with different words or a wider date range before giving up.\n"
    "- Use get_screenshot_details to read the full text of a candidate, and look_at_screenshot to "
    "ask a specific question about the real image when the description is not enough to be sure.\n"
    "- When finished, reply with ONLY this JSON: "
    '{"answer": "<1-2 friendly sentences>", "results": [{"id": "<id>", "why": "<short reason it matches>"}]}. '
    "Best match first, at most 5. Use an empty results list if nothing matches. Never invent ids."
)


def _tool(name, description, properties, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


_DATES = {
    "since": {"type": "string", "description": "Earliest date, YYYY-MM-DD (optional)"},
    "until": {"type": "string", "description": "Latest date, YYYY-MM-DD (optional)"},
}

TOOLS = [
    _tool("search_screenshots",
          "Search screenshot descriptions, visible text and tags. Returns the best matches.",
          {"keywords": {"type": "array", "items": {"type": "string"},
                        "description": "Single words and synonyms to look for"},
           **_DATES, "limit": {"type": "integer", "description": "Max results (default 8)"}},
          ["keywords"]),
    _tool("list_recent", "List the newest screenshots, optionally within a date range.",
          {**_DATES, "limit": {"type": "integer", "description": "Max results (default 10)"}}),
    _tool("get_screenshot_details", "Get the full record of one screenshot by id.",
          {"id": {"type": "string"}}, ["id"]),
    _tool("look_at_screenshot",
          "Look at the actual image of a screenshot and answer a specific question about it.",
          {"id": {"type": "string"}, "question": {"type": "string"}}, ["id", "question"]),
]


def _brief(r):
    return {"id": r["id"], "date": r["taken_at"], "title": r["title"],
            "description": (r.get("description") or "")[:300], "tags": r.get("tags", "")}


def _fmt(value, limit=110):
    """Readable one-line form of a tool argument; adds ... only if it is really cut."""
    s = json.dumps(value, ensure_ascii=False)
    return s if len(s) <= limit else s[: limit - 3].rstrip() + "..."


def _words(value):
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    out = []
    for w in value or []:
        w = "".join(ch for ch in str(w) if ch.isalnum() or ch in "_-").strip("-_")
        if w:
            out.append(w)
    return out


def run_tool(name, args, store, seen):
    try:
        if name in ("search_screenshots", "list_recent"):
            since, until = args.get("since"), args.get("until")
            if name == "search_screenshots":
                rows = store.search(_words(args.get("keywords")), since, until,
                                    int(args.get("limit") or 8))
            else:
                rows = store.recent(since, until, int(args.get("limit") or 10))
            for r in rows:
                seen[r["id"]] = r
            out = {"count": len(rows), "results": [_brief(r) for r in rows]}
            if not rows:
                out["hint"] = "Nothing found. Try other synonyms or a wider date range."
            return out
        if name == "get_screenshot_details":
            r = store.get(str(args.get("id")))
            if not r:
                return {"error": "unknown id"}
            seen[r["id"]] = r
            return {k: r.get(k) for k in ("id", "taken_at", "title", "description", "text_seen", "tags")}
        if name == "look_at_screenshot":
            r = store.get(str(args.get("id")))
            if not r:
                return {"error": "unknown id"}
            if not Path(r["path"]).exists():
                return {"error": "the image file is missing on disk"}
            seen[r["id"]] = r
            return {"answer": llm.ask(str(args.get("question", "Describe this screenshot.")), r["path"])}
        return {"error": f"unknown tool {name}"}
    except Exception as e:
        return {"error": str(e)}


def _fallback(question, store, on_step):
    """Keyword mode: the model turns the question into keywords + dates, we search."""
    on_step("keyword mode (no tool calling available)")
    prompt = (
        f"Today is {datetime.now().strftime('%Y-%m-%d (%A)')}. The user is searching their screenshot "
        'history. Reply with ONLY JSON: {"keywords": [3-8 single words and synonyms], '
        '"since": "YYYY-MM-DD or null", "until": "YYYY-MM-DD or null"}. '
        f"Be generous with dates.\nQuestion: {question}"
    )
    plan = llm.parse_json(llm.ask(prompt), {"keywords": question.split()})
    words = _words(plan.get("keywords") or question.split())
    since, until = plan.get("since"), plan.get("until")
    on_step(f"search_screenshots({words}, {since}, {until})")
    rows = store.search(words, since, until, 6) or store.search(words, None, None, 6)
    answer = f"Found {len(rows)} possible match(es)." if rows else "Nothing matched that description."
    return {"answer": answer, "results": [{**r, "why": ""} for r in rows], "mode": "keyword"}


def run_agent(question, store, on_step=lambda s: None):
    """Answer a natural-language question. Returns {"answer", "results": [record+why], "mode"}."""
    seen = {}
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Today is {datetime.now().strftime('%Y-%m-%d (%A)')}.\nQuestion: {question}"},
    ]
    final = None
    try:
        for step in range(config.MAX_AGENT_STEPS):
            msg = llm.chat(messages, tools=TOOLS)
            calls = msg.get("tool_calls") or []
            if not calls:
                if step == 0 and not seen:       # model ignored the tools entirely
                    return _fallback(question, store, on_step)
                final = msg.get("content") or ""
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                fn = c.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                short = ", ".join(f"{k}={_fmt(v)}" for k, v in args.items())
                on_step(f"{name}({short})")
                result = run_tool(name, args, store, seen)
                if isinstance(result, dict) and "count" in result:
                    on_step(f"   -> {result['count']} result(s)")
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "name": name,
                                 "content": json.dumps(result, ensure_ascii=False)[:6000]})
        else:  # ran out of steps: ask for the answer without tools
            messages.append({"role": "user", "content": "Give your final JSON answer now."})
            final = llm.chat(messages).get("content") or ""
    except llm.LLMError as e:
        if e.status == 400 and not seen:         # provider rejected the `tools` field
            return _fallback(question, store, on_step)
        raise

    data = llm.parse_json(final, None)
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        results = []
        for item in data["results"][:6]:
            rid = str(item.get("id") if isinstance(item, dict) else item)
            rec = seen.get(rid) or store.get(rid)
            if rec:
                results.append({**rec, "why": item.get("why", "") if isinstance(item, dict) else ""})
        return {"answer": data.get("answer", ""), "results": results, "mode": "agent"}
    # the model answered in plain text: show what it looked at
    return {"answer": final, "results": [{**r, "why": ""} for r in list(seen.values())[:5]],
            "mode": "agent"}
