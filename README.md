# GitHub Review Agent

An autonomous GitHub PR reviewer powered by an LLM agent with multi-tool orchestration.

## What it does

When a PR is opened, a webhook triggers an agentic loop that:

1. Fetches the full diff via GitHub API
2. Runs `ruff` static analysis on changed Python files
3. Checks whether changed source files have corresponding tests
4. Searches open issues for related context
5. Synthesizes a structured review and posts it as a GitHub comment
6. Streams live progress to a TypeScript dashboard over WebSocket

## Architecture

```
GitHub webhook → FastAPI server → Agent loop (Gemini + 4 tools) → GitHub PR comment
                                         ↓
                              TypeScript dashboard (WebSocket)
```

## Tech stack

| Layer | Technology |
|---|---|
| Agent | Google Gemini API with function calling, ReAct-style loop |
| Backend | Python 3.11, FastAPI, WebSockets, uvicorn |
| Tools | GitHub API (PyGithub), ruff (subprocess), test coverage checker, issue search |
| Frontend | TypeScript, React, WebSocket client |
| Testing | pytest, pytest-asyncio, mocked GitHub API fixtures |
| Eval | LLM-as-judge scoring agent reviews against human reviews |
| Deploy | Docker, docker-compose |

## Project structure

```
github-bot/
├── backend/
│   ├── agent/
│   │   └── reviewer.py        # ReAct agent loop — core of the project
│   ├── tools/
│   │   └── github_tools.py    # 4 typed tool implementations
│   ├── tests/
│   │   ├── test_agent.py      # 14 unit + integration tests
│   │   └── eval/
│   │       └── llm_judge.py   # LLM-as-judge eval over 10 PR fixtures
│   └── main.py                # FastAPI webhook server + WebSocket
├── dashboard/                 # TypeScript/React frontend
│   └── src/
│       └── App.tsx            # Live agent stream + review output
├── Dockerfile
└── docker-compose.yml
```

## Running locally

```bash
# 1. Clone and set up environment
git clone <your-repo>
cd github-bot
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# 2. Set environment variables
cp backend/.env.example backend/.env
# Fill in GEMINI_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET

# 3. Start the backend
cd backend
uvicorn main:app --reload

# 4. Start the dashboard (separate terminal)
cd dashboard
npm install
npm start

# 5. Or run everything via Docker
docker compose up --build
```

## Running tests

```bash
cd backend
python -m pytest tests/test_agent.py -v
```

Expected output:
```
14 passed in 0.55s
```

## Running the eval

```bash
cd backend
python -m tests.eval.llm_judge
```

Scores agent-generated reviews against human reviews across 10 PR fixtures using an LLM-as-judge. Reports agreement rate and per-dimension scores (issues found, severity accuracy, actionability).

## Exposing the webhook locally

```bash
# Install ngrok
brew install ngrok

# Expose port 8000
ngrok http 8000

# Set the forwarding URL as your GitHub webhook:
# https://<your-ngrok-id>.ngrok.io/webhook
# Content type: application/json
# Events: Pull requests
```

## Environment variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GITHUB_TOKEN` | GitHub personal access token (repo scope) |
| `GITHUB_WEBHOOK_SECRET` | Secret set when creating the GitHub webhook |

## How the agent loop works

The agent runs up to 10 iterations. Each iteration:

1. Sends the conversation history to Gemini
2. If the model returns tool calls → executes them, appends results, loops
3. If the model returns text with no tool calls → that is the final review
4. Each step broadcasts a WebSocket event to the dashboard in real time

This is a ReAct (Reason + Act) pattern: the model reasons about what information it needs, acts by calling tools, observes the results, and repeats until it has enough context to write the review.