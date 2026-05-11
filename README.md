# PR Review Agent

An autonomous code reviewer that runs as a GitHub bot. When a pull request is opened, it fetches the diff, runs static analysis, checks test coverage, searches related issues, and posts a structured review as a comment — all without human involvement.

## What it does

- Receives GitHub webhook events and verifies HMAC-SHA256 signatures
- Runs a ReAct-style agentic loop using the Anthropic Claude API with 4 tools
- Streams live progress to a TypeScript dashboard over WebSocket
- Saves every review to MongoDB for a persistent review history
- Posts the final review directly to the PR as a GitHub comment

## Architecture

```
GitHub webhook → FastAPI server → Claude agent (ReAct loop + 4 tools) → GitHub PR comment
                                          ↓
                               TypeScript dashboard (WebSocket)
                                          ↓
                                      MongoDB
```

## Tech stack

| Layer | Technology |
|---|---|
| Agent | Anthropic Claude API, ReAct-style agentic loop |
| Backend | Python, FastAPI, WebSockets, uvicorn |
| Tools | GitHub API (PyGithub), ruff, test coverage checker, issue search |
| Database | MongoDB Atlas (review history) |
| Frontend | TypeScript, React, WebSocket client |
| Testing | pytest, pytest-asyncio, mocked GitHub API fixtures |
| Eval | LLM-as-judge scoring across 10 PR fixtures |
| Deploy | Docker, docker-compose |

## Project structure

```
github-bot/
├── backend/
│   ├── agent/
│   │   └── reviewer.py        # ReAct agent loop
│   ├── tools/
│   │   └── github_tools.py    # 4 tool implementations
│   ├── tests/
│   │   ├── test_agent.py      # 14 unit + integration tests
│   │   └── eval/
│   │       └── llm_judge.py   # LLM-as-judge eval
│   ├── db.py                  # MongoDB connection and queries
│   └── main.py                # FastAPI server, webhook, WebSocket
├── dashboard/
│   └── src/
│       └── App.tsx            # Live stream + review history
├── Dockerfile
└── docker-compose.yml
```

## How the agent loop works

The agent runs up to 10 iterations. On each step:

1. Sends the conversation history to Claude
2. If Claude returns tool calls — executes them, appends results, loops
3. If Claude returns text with no tool calls — that is the final review
4. Every step broadcasts a WebSocket event to the dashboard in real time

This is a ReAct (Reason + Act) pattern: the model reasons about what information it needs, calls a tool, observes the result, and repeats until it has enough context to write the review.

## Running locally

```bash
# Clone and set up
git clone <your-repo>
cd github-bot
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Set environment variables
cp backend/.env.example backend/.env
# Fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET, MONGODB_URI

# Start the backend
cd backend
uvicorn main:app --reload

# Start the dashboard (separate terminal)
cd dashboard
npm install
npm start

# Or run everything via Docker
docker compose up --build
```

## Running tests

```bash
cd backend
python -m pytest tests/test_agent.py -v
# 14 passed
```

## Running the eval

```bash
cd backend
python -m tests.eval.llm_judge
```

Scores agent-generated reviews against human reviews across 10 PR fixtures on four dimensions: issues found, severity accuracy, actionability, and overall agreement.

## Exposing the webhook locally

```bash
ngrok http 8000
# Use the forwarding URL as your GitHub webhook payload URL
# Content type: application/json
# Events: Pull requests only
```

## Environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GITHUB_TOKEN` | GitHub personal access token (repo scope) |
| `GITHUB_WEBHOOK_SECRET` | Secret set when creating the GitHub webhook |
| `MONGODB_URI` | MongoDB Atlas connection string |