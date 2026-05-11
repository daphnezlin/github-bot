import os
from dotenv import load_dotenv
from fastapi import WebSocket
from github import Github
import anthropic
from db import save_review

from tools.github_tools import TOOL_FUNCTIONS

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
gh = Github(os.getenv("GITHUB_TOKEN"))

TOOLS = [
    {
        "name": "get_pr_diff",
        "description": "Fetch the full diff of all files changed in this pull request. Call this first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_full_name": {"type": "string"},
                "pr_number": {"type": "integer"},
            },
            "required": ["repo_full_name", "pr_number"],
        },
    },
    {
        "name": "run_linter",
        "description": "Run static analysis on changed Python files to detect style issues and bugs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_full_name": {"type": "string"},
                "pr_number": {"type": "integer"},
            },
            "required": ["repo_full_name", "pr_number"],
        },
    },
    {
        "name": "get_test_coverage",
        "description": "Check whether changed source files have corresponding test files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_full_name": {"type": "string"},
                "pr_number": {"type": "integer"},
            },
            "required": ["repo_full_name", "pr_number"],
        },
    },
    {
        "name": "search_related_issues",
        "description": "Search open issues related to this PR based on the title and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_full_name": {"type": "string"},
                "pr_number": {"type": "integer"},
                "pr_title": {"type": "string"},
                "pr_body": {"type": "string"},
            },
            "required": ["repo_full_name", "pr_number", "pr_title", "pr_body"],
        },
    },
]

SYSTEM_PROMPT = """You are an expert code reviewer. Your job is to review GitHub pull requests thoroughly.

When given a PR you must:
1. ALWAYS call get_pr_diff first to see what changed
2. Call run_linter to check for code style issues
3. Call get_test_coverage to check if tests are included
4. Call search_related_issues to find related context
5. After gathering all information, write a structured review

Your final review must be formatted as a GitHub comment in Markdown:

## AI Code Review

### Summary
(1-2 sentences on what this PR does)

### What looks good
(bullet points)

### Issues and suggestions
(bullet points with file references)

### Testing
(comment on test coverage)

### Related issues
(any related open issues found)

---
*Reviewed by github-bot*

Be specific, actionable, and encouraging."""


async def send_ws_update(websocket: WebSocket | None, message: dict):
    if websocket:
        try:
            await websocket.send_json(message)
        except Exception:
            pass


async def run_review_agent(
    repo_full_name: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    websocket: WebSocket | None = None,
):
    await send_ws_update(websocket, {
        "type": "status",
        "message": f"Starting review for PR #{pr_number}: {pr_title}"
    })

    messages = [
        {
            "role": "user",
            "content": (
                f"Please review this pull request.\n\n"
                f"**Repository:** {repo_full_name}\n"
                f"**PR #{pr_number}:** {pr_title}\n"
                f"**Description:** {pr_body or 'No description provided.'}\n\n"
                f"Use your tools to gather information, then write a thorough code review."
            )
        }
    ]

    final_review = None

    for iteration in range(10):
        await send_ws_update(websocket, {
            "type": "thinking",
            "message": f"Agent thinking... (step {iteration + 1})"
        })

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # check if we're done
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    final_review = block.text
                    break
            break

        # process tool calls
        tool_results = []
        has_tool_use = False

        for block in response.content:
            if block.type == "tool_use":
                has_tool_use = True
                tool_name = block.name
                tool_args = block.input

                await send_ws_update(websocket, {
                    "type": "tool_call",
                    "tool": tool_name,
                    "input": tool_args,
                })

                tool_fn = TOOL_FUNCTIONS.get(tool_name)
                try:
                    result = tool_fn(**tool_args) if tool_fn else f"Unknown tool: {tool_name}"
                except Exception as e:
                    result = f"Tool error: {e}"

                await send_ws_update(websocket, {
                    "type": "tool_result",
                    "tool": tool_name,
                    "preview": str(result)[:200],
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })

        # add assistant response and tool results to messages
        messages.append({"role": "assistant", "content": response.content})

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        elif not has_tool_use:
            for block in response.content:
                if hasattr(block, "text"):
                    final_review = block.text
                    break
            break

    # post review to GitHub
    if final_review:
        await send_ws_update(websocket, {"type": "status", "message": "Posting review to GitHub..."})
        try:
            repo = gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(final_review)
            save_review(repo_full_name, pr_number, pr_title, final_review)
            await send_ws_update(websocket, {
                "type": "complete",
                "message": "Review posted!",
                "review": final_review,
            })
        except Exception as e:
            await send_ws_update(websocket, {"type": "error", "message": f"Failed to post: {e}"})
    else:
        await send_ws_update(websocket, {"type": "error", "message": "Agent did not produce a review."})