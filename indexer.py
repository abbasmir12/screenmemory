"""Turns screenshots into searchable records.

  index_file    describe one screenshot with the model and save it
  index_all     describe every screenshot in the folder (newest first)
  start_watcher describe new screenshots automatically as they appear
"""
import hashlib
import time
from datetime import datetime
from pathlib import Path

import config
import llm

DESCRIBE_PROMPT = (
    "You are indexing a screenshot so the user can find it again later. "
    "Reply with ONLY a JSON object with these keys: "
    '"title" (short), '
    '"description" (2-3 sentences: which app, website or tool this is and what the user was doing), '
    '"text_seen" (important visible text: names, URLs, error messages, numbers), '
    '"tags" (list of 5-8 keywords). No markdown, no extra text.'
)


def make_id(path) -> str:
    """Short stable id derived from the file path (easy for the model to copy)."""
    return hashlib.sha1(str(path).lower().encode()).hexdigest()[:8]


def index_file(store, path):
    """Describe one screenshot and save it. Returns the record, or None if already indexed."""
    path = Path(path)
    if store.exists(str(path)):
        return None
    raw = llm.ask(DESCRIBE_PROMPT, path)
    data = llm.parse_json(raw, {"title": path.stem, "description": raw[:500],
                                "text_seen": "", "tags": []})
    tags = data.get("tags", [])
    tags = " ".join(map(str, tags)) if isinstance(tags, list) else str(tags)
    record = {
        "id": make_id(path),
        "path": str(path),                       # back-reference to the real file
        "filename": path.name,
        "taken_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"),
        "indexed_at": datetime.now().isoformat(timespec="seconds"),
        "title": str(data.get("title", "")) or path.stem,
        "description": str(data.get("description", "")),
        "text_seen": str(data.get("text_seen", "")),
        "tags": tags,
    }
    store.add(record)
    return record


def index_all(store, log=print, stop=None):
    """Index every screenshot in the folder, newest first. `stop` is a threading.Event."""
    if not config.SHOTS_DIR.exists():
        log(f"Folder not found: {config.SHOTS_DIR}")
        return
    files = [p for p in config.SHOTS_DIR.iterdir() if p.suffix.lower() in config.EXTS]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    todo = [p for p in files if not store.exists(str(p))]
    log(f"{len(todo)} new screenshots to describe ({len(files)} in folder).")
    for i, p in enumerate(todo, 1):
        if stop is not None and stop.is_set():
            log("Stopped. Run again any time to continue.")
            return
        try:
            rec = index_file(store, p)
            log(f"[{i}/{len(todo)}] {rec['title'] if rec else p.name}")
        except Exception as e:
            log(f"[{i}/{len(todo)}] skipped {p.name}: {e}")
        time.sleep(config.DELAY)
    log("Indexing finished.")


def start_watcher(store, on_indexed=None, log=print, on_new=None):
    """Watch the screenshots folder. Returns the observer.

    Without on_new, each new file is described automatically. With on_new(path),
    the callback decides (the app uses it to ask the user first).
    """
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    def handle(path):
        path = Path(path)
        if path.suffix.lower() not in config.EXTS:
            return
        time.sleep(1.5)  # let Windows finish writing the file
        try:
            if store.exists(str(path)):
                return
            if on_new:
                on_new(path)
                return
            rec = index_file(store, path)
            if rec and on_indexed:
                on_indexed(rec)
        except Exception as e:
            log(f"Could not describe {path.name}: {e}")

    class Handler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                handle(event.src_path)

        def on_moved(self, event):  # some apps save to a temp name, then rename
            if not event.is_directory:
                handle(event.dest_path)

    obs = Observer()
    obs.schedule(Handler(), str(config.SHOTS_DIR), recursive=False)
    obs.daemon = True
    obs.start()
    log(f"Watching {config.SHOTS_DIR}")
    return obs
