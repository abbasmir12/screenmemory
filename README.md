# Screen Memory

Your screenshots, searchable in plain language. A vision model describes every
screenshot when you take it. Later you ask a question and a search AGENT uses tools
(search, read details, re-inspect the real image) to find it for you.

## Files
| File | Job |
|---|---|
| `main.py` | commands: ui, check, index, watch, search, sync |
| `config.py` | settings from `.env` / environment variables |
| `llm.py` | OpenAI-compatible client (vision + tool calling) |
| `store.py` | SQLite or MongoDB Atlas, keeps the file path of every screenshot |
| `indexer.py` | describes screenshots, batch indexing, folder watcher |
| `agent.py` | the tool-calling search agent (+ keyword fallback) |
| `ui.py` | the tkinter app |

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, choose your provider (local Ollama, Google AI Studio, OpenRouter, ...).
3. `python main.py check`   (tests the model, tool calling, and database)
4. `python main.py`         (opens the app; click "Index existing screenshots" once)

Double-click `run.bat` to start the app without a terminal. Put a shortcut to it in
`shell:startup` so new screenshots are described automatically after every login.

## What leaves your PC
The model endpoint receives each screenshot you index (resized) and your search
questions. With a local endpoint (localhost) nothing leaves. With MongoDB Atlas, only
text descriptions and file paths are stored there, never images. The app shows
LOCAL / REMOTE in its header so you always know which one you are using.
