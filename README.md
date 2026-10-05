# Screen Memory

Find any screenshot by describing it in plain words. Gemma 4 reads each screenshot once and saves what it sees as text. Later, a small search agent looks through that text and brings the screenshot back.

Demo video: https://youtu.be/oH65CRKHw5Q

> I had 560 screenshots named like `Screenshot 2026-07-18 204819`.
> I knew I had taken the one I needed. I just could not find it.

## What it does

Type a question like "that ad about connecting to a Raspberry Pi remotely" and get the screenshot back, with a reason why it matched. The AI does not scan your folder. It uses tools to search, read, and double-check, then answers.

When you take a screenshot, a small popup asks "Describe it so you can search it later?". If you ignore it, nothing is sent anywhere. With a local model, your screenshots, your database, and your searches stay on your PC.

It works with any OpenAI-compatible endpoint, so you can use local Ollama, LM Studio, OpenRouter, Google AI Studio, and others by changing three settings.

## How it works

> Understand once. Search many times.

**Remember once.** When you say yes to the popup, Gemma 4 looks at the screenshot and writes a title, a description, the important text on screen, and tags. This is the only heavy AI work, and it happens once per screenshot.

**Store the text.** Everything goes into one SQLite file, with a full-text index over it. The image is never stored in the database, only its file path, which is how a result opens the real file.

**Search the text.** A search never sends images to the model. The agent gets a few short text results, so searches stay fast even with hundreds of screenshots.

The agent has four tools:

| Tool | What it does |
|---|---|
| `search_screenshots` | Searches descriptions, visible text, and tags, with optional dates |
| `list_recent` | Lists the newest screenshots in a date range |
| `get_screenshot_details` | Reads the full stored text of one screenshot |
| `look_at_screenshot` | Opens one real image and asks the vision model a question about it |

The agent answers with short ids, and the app looks up each path in the database, so it can only point to screenshots that really exist. If a model cannot use tools, the app falls back to a simpler keyword mode, and search keeps working.

## Quick start

Install the dependencies:

```
pip install -r requirements.txt
```

Get a model. This example uses local Ollama:

```
ollama pull gemma4:e2b
```

Any vision-capable model with tool calling works. Larger models write better descriptions.

Copy `.env.example` to `.env`. The defaults point at local Ollama:

```
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=gemma4:e2b
```

Test your setup. This checks the model, tool calling, and the database, and tells you what to fix:

```
python main.py check
```

Run the app, click "Index existing screenshots" once, then search:

```
python main.py
```

New screenshots are handled by the popup while the app is open.

## Choosing a model provider

Change only the three `LLM_` lines in `.env`. No code changes are needed.

| Provider | `LLM_BASE_URL` | Runs on |
|---|---|---|
| Ollama (default) | `http://localhost:11434/v1` | Your PC |
| LM Studio, llama.cpp, vLLM | their local `/v1` address | Your PC |
| OpenRouter | `https://openrouter.ai/api/v1` | Remote |
| Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai` | Remote |

The app header shows whether the model is local or remote, and the popup tells you where an image will go before you agree.

## Commands

| Command | What it does |
|---|---|
| `python main.py` | Opens the app |
| `python main.py check` | Tests your model and database settings |
| `python main.py index` | Describes all existing screenshots |
| `python main.py watch` | Describes new screenshots with no window |
| `python main.py search "..."` | Asks a question from the terminal |
| `python main.py sync` | Copies local records into MongoDB Atlas (optional, experimental) |

To start with Windows, put a shortcut to `run.bat` in `shell:startup` so the app is always watching for new screenshots.

## Privacy

With a local model, nothing leaves your PC. With a remote provider, each screenshot you agree to describe is sent to that provider, and so are your search questions. Your database and your original image files always stay on your machine.

The stored text can include anything that was on screen, like names or messages. Keep "Ask me first" turned on if you screenshot private things.

## Project structure

```
main.py        commands: ui, check, index, watch, search, sync
config.py      settings from .env
llm.py         OpenAI-compatible client (vision and tool calling)
store.py       SQLite storage that keeps every file path
indexer.py     describes screenshots, batch index, folder watcher
agent.py       the tool-calling search agent, with keyword fallback
ui.py          the desktop app (tkinter)
toast.py       corner popups for permission and confirmation
run.bat        starts the app without a terminal
.env.example   copy to .env
```

## Troubleshooting

Run `python main.py check` first. It usually names the problem.

| You see | It means |
|---|---|
| `HTTP 404` | `LLM_BASE_URL` is usually missing `/v1`, or the model name does not exist at that provider |
| `HTTP 401` or `403` | The `LLM_API_KEY` is wrong |
| `HTTP 429` | The provider is rate limiting you. Wait, or raise `LLM_DELAY` in `.env` |
| Tool calling not used | The model ignores tools, so the app uses keyword mode. Try a larger model |
| Screenshots not detected | Set `SHOTS_DIR` in `.env` if your folder is not `Pictures\Screenshots` |

## Roadmap

Search by meaning, so "cheap flights" finds "budget airfare". Start with Windows automatically. Package it as a single `.exe` so it runs without Python.

## Built for

The [Hacktoberfest Weekend Challenge: Build for a Friend](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01), around an open model, with the idea that your screenshots should stay yours.