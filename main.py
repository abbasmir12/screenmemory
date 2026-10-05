"""Screen Memory entry point.

    python main.py            open the app (same as: python main.py ui)
    python main.py check      test your model + database settings
    python main.py index      describe all existing screenshots
    python main.py watch      describe new screenshots as they appear (no window)
    python main.py search "the site where I compared laptop prices last week"
    python main.py sync       copy local SQLite records into MongoDB Atlas
"""
import sys
import time

import config
import llm
from store import SqliteStore, get_store


def cmd_check():
    print(config.summary(), "\n")
    store = get_store()
    print(f"Records indexed: {store.count()}")
    print("Model reply    :", llm.ask("Reply with the single word OK.").strip()[:80])
    ping = [{"type": "function", "function": {
        "name": "ping", "description": "Call this tool.",
        "parameters": {"type": "object", "properties": {}}}}]
    try:
        msg = llm.chat([{"role": "user", "content": "Call the ping tool now."}], tools=ping)
        ok = bool(msg.get("tool_calls"))
        print("Tool calling   :", "works" if ok else
              "not used by this model (the app will use keyword mode instead)")
    except llm.LLMError as e:
        print("Tool calling   : not supported by this provider ->", e)


def cmd_index():
    import indexer
    print(config.summary(), "\n")
    indexer.index_all(get_store())


def cmd_watch():
    import indexer
    store = get_store()
    print(config.summary(), "\n")
    indexer.start_watcher(store, on_indexed=lambda r: print("  described:", r["title"]))
    print("Take a screenshot. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def cmd_search(question):
    import agent
    res = agent.run_agent(question, get_store(), on_step=lambda s: print("  >", s))
    print("\n" + (res["answer"] or ""))
    for i, r in enumerate(res["results"], 1):
        print(f"\n{i}. {r['title']}  ({r['taken_at']})\n   {r['description']}")
        if r.get("why"):
            print(f"   why: {r['why']}")
        print(f"   {r['path']}")


def cmd_sync():
    if not config.MONGODB_URI:
        print("Set MONGODB_URI in .env first.")
        return
    from store import MongoStore
    rows = SqliteStore().all()
    remote = MongoStore(config.MONGODB_URI)
    print(f"Copying {len(rows)} records (text only) to MongoDB Atlas ...")
    for r in rows:
        remote.add(r)
    print("Done.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ui"
    if cmd == "ui":
        import ui
        ui.run()
    elif cmd == "check":
        cmd_check()
    elif cmd == "index":
        cmd_index()
    elif cmd == "watch":
        cmd_watch()
    elif cmd == "search" and len(sys.argv) > 2:
        cmd_search(" ".join(sys.argv[2:]))
    elif cmd == "sync":
        cmd_sync()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
