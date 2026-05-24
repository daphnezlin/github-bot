# PR Review Agent
An autonomous code reviewer that runs as a GitHub bot. When a pull request is opened, it fetches the diff, runs static analysis, checks test coverage, searches related issues, and posts both inline comments on specific lines of code and a structured summary review, all without human involvement.

## Live demo
| | URL |
|---|---|
| Dashboard | http://github-bot-dashboard.s3-website.ca-central-1.amazonaws.com |
| Backend API | http://15.223.46.157:8000 |

## What it does
- Receives GitHub webhook events and verifies HMAC-SHA256 signatures
- Runs a ReAct-style agentic loop using the Anthropic Claude API with 4 tools
- Posts inline comments on specific lines of code via GitHub's review API
- Posts a structured summary review as an overall PR comment
- Streams live progress to a TypeScript dashboard over WebSocket
- Saves every review to MongoDB for a persistent review history

## Architecture
```
GitHub webhook → FastAPI server → Claude agent (ReAct loop + 4 tools) → GitHub PR review (inline + summary)
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
| Deploy | AWS EC2 (backend), AWS S3 (frontend), systemd, Docker |

## Project structure
```
github-bot/
├── backend/
│   ├── agent/
│   │   └── reviewer.py        # ReAct agent loop + inline comment logic
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
2. If Claude returns tool calls- executes them, appends results, loops
3. If Claude returns JSON with no tool calls- parses it into inline comments and a summary review
4. Every step broadcasts a WebSocket event to the dashboard in real time

This is a ReAct (Reason + Act) pattern: the model reasons about what information it needs, calls a tool, observes the result, and repeats until it has enough context to write the review.

The final output is a GitHub review containing:
- Inline comments attached to specific lines in the diff
- A structured summary comment on the Conversation tab

## Deployment
The backend runs as a systemd service on AWS EC2, staying live 24/7 without any local process running. The frontend is hosted as a static site on AWS S3.

To add the bot to any GitHub repo:
1. Go to Settings → Webhooks → Add webhook
2. Set Payload URL to: `http://15.223.46.157:8000/webhook`
3. Content type: `application/json`
4. Secret: your `GITHUB_WEBHOOK_SECRET`
5. Events: Pull requests only

## Running locally
```bash
# Clone and set up
git clone https://github.com/daphnezlin/github-bot
cd github-bot
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Set environment variables
# Create backend/.env with ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET, MONGODB_URI

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

## Environment variables
| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GITHUB_TOKEN` | GitHub personal access token (repo scope) |
| `GITHUB_WEBHOOK_SECRET` | Secret set when creating the GitHub webhook |
| `MONGODB_URI` | MongoDB Atlas connection string |