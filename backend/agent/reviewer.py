import os
from dotenv import load_dotenv
from fastapi import WebSocket
from github import Github
from google import genai
from google.genai import types

from tools.github_tools import TOOL_FUNCTIONS

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
gh = Github(os.getenv("GITHUB_TOKEN"))

TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="get_pr_diff",
            description="Fetch the full diff of all files changed in this pull request. Call this first.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "repo_full_name": types.Schema(type="STRING"),
                    "pr_number": types.Schema(type="INTEGER"),
                },
                required=["repo_full_name", "pr_number"],
            ),
        ),
        types.FunctionDeclaration(
            name="run_linter",
            description="Run static analysis on changed Python files to detect style issues and bugs.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "repo_full_name": types.Schema(type="STRING"),
                    "pr_number": types.Schema(type="INTEGER"),
                },
                required=["repo_full_name", "pr_number"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_test_coverage",
            description="Check whether changed source files have corresponding test files.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "repo_full_name": types.Schema(type="STRING"),
                    "pr_number": types.Schema(type="INTEGER"),
                },
                required=["repo_full_name", "pr_number"],
            ),
        ),
        types.FunctionDeclaration(
            name="search_related_issues",
            description="Search open issues related to this PR based on the title and description.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "repo_full_name": types.Schema(type="STRING"),
                    "pr_number": types.Schema(type="INTEGER"),
                    "pr_title": types.Schema(type="STRING"),
                    "pr_body": types.Schema(type="STRING"),
                },
                required=["repo_full_name", "pr_number", "pr_title", "pr_body"],
            ),
        ),
    ])
]

SYSTEM_PROMPT = """You are an expert code reviewer. Your job is to review GitHub pull requests thoroughly.

When given a PR you must:
1. ALWAYS call get_pr_diff first to see what changed
2. Call run_linter to check for code style issues
3. Call get_test_coverage to check if tests are included
4. Call search_related_issues to find related context
5. After gathering all information, write a structured review

Your final review must be formatted as a GitHub comment in Markdown:

## 🤖 AI Code Review

### Summary
(1-2 sentences on what this PR does)

### ✅ What looks good
(bullet points)

### ⚠️ Issues & suggestions
(bullet points with file references)

### 🧪 Testing
(comment on test coverage)

### 🔗 Related issues
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
        types.Content(
            role="user",
            parts=[types.Part(text=(
                f"Please review this pull request.\n\n"
                f"**Repository:** {repo_full_name}\n"
                f"**PR #{pr_number}:** {pr_title}\n"
                f"**Description:** {pr_body or 'No description provided.'}\n\n"
                f"Use your tools to gather information, then write a thorough code review."
            ))]
        )
    ]

    final_review = None

    for iteration in range(10):
        await send_ws_update(websocket, {
            "type": "thinking",
            "message": f"Agent thinking... (step {iteration + 1})"
        })

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=TOOLS,
            ),
        )

        messages.append(types.Content(
            role="model",
            parts=response.candidates[0].content.parts,
        ))

        # Check for tool calls
        tool_calls = [
            p.function_call
            for p in response.candidates[0].content.parts
            if p.function_call is not None
        ]

        if not tool_calls:
            for part in response.candidates[0].content.parts:
                if part.text:
                    final_review = part.text
                    break
            break

        # Execute tools and collect results
        tool_result_parts = []
        for call in tool_calls:
            tool_name = call.name
            tool_args = dict(call.args)

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

            tool_result_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response={"result": str(result)},
                    )
                )
            )

        messages.append(types.Content(role="user", parts=tool_result_parts))

    # Post review to GitHub
    if final_review:
        await send_ws_update(websocket, {"type": "status", "message": "Posting review to GitHub..."})
        try:
            repo = gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(final_review)
            await send_ws_update(websocket, {
                "type": "complete",
                "message": "Review posted!",
                "review": final_review,
            })
        except Exception as e:
            await send_ws_update(websocket, {"type": "error", "message": f"Failed to post: {e}"})
    else:
        await send_ws_update(websocket, {"type": "error", "message": "Agent did not produce a review."})