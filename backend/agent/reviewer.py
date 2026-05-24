import os
import json
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

Your final response MUST be valid JSON in exactly this format:
{
  "summary": "1-2 sentence summary of what this PR does",
  "inline_comments": [
    {
      "path": "exact/file/path.py",
      "position": <diff position integer>,
      "body": "specific comment about this line"
    }
  ],
  "overall_comment": "## AI Code Review\\n\\n### Summary\\n...\\n\\n### What looks good\\n...\\n\\n### Issues and suggestions\\n...\\n\\n### Testing\\n...\\n\\n### Related issues\\n...\\n\\n---\\n*Reviewed by github-bot*"
}

For inline_comments:
- position is the line's position in the unified diff (1-indexed, counting from the first @@ line of each file's diff)
- Only include inline comments for lines that start with + in the diff (added lines)
- Be specific — reference the exact issue on that line
- Include 2-5 inline comments maximum on the most important issues
- If there are no significant issues on specific lines, return an empty array for inline_comments

Return ONLY the JSON object, no other text before or after it."""


def parse_diff_positions(diff_text: str) -> dict[str, dict[int, int]]:
    """
    Parse a unified diff and return a mapping of:
    {filename: {actual_line_number: diff_position}}
    
    diff_position is what GitHub's API needs for inline comments.
    """
    file_positions = {}
    current_file = None
    diff_position = 0
    current_line = 0

    for line in diff_text.split("\n"):
        if line.startswith("### "):
            # Our custom format: ### filename (status)
            parts = line[4:].split(" (")
            if parts:
                current_file = parts[0].strip()
                file_positions[current_file] = {}
                diff_position = 0
                current_line = 0
        elif line.startswith("@@"):
            # Parse @@ -old_start,old_count +new_start,new_count @@
            diff_position += 1
            try:
                new_part = line.split("+")[1].split("@@")[0].strip()
                current_line = int(new_part.split(",")[0]) - 1
            except (IndexError, ValueError):
                current_line = 0
        elif line.startswith("+") and not line.startswith("+++"):
            diff_position += 1
            current_line += 1
            if current_file and current_file in file_positions:
                file_positions[current_file][current_line] = diff_position
        elif line.startswith("-") and not line.startswith("---"):
            diff_position += 1
        elif not line.startswith("\\"):
            diff_position += 1
            current_line += 1

    return file_positions


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
    active_connections: dict | None = None,
):
    def get_ws():
        return (active_connections or {}).get(pr_number)
    
    await send_ws_update(get_ws(), {
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
                f"Use your tools to gather information, then write a thorough code review. "
                f"Remember to return your final review as a JSON object."
            )
        }
    ]

    final_review_json = None
    diff_text = None

    for iteration in range(10):
        await send_ws_update(get_ws(), {
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
                    try:
                        text = block.text.strip()
                        start = text.find("{")
                        end = text.rfind("}") + 1
                        if start != -1 and end > start:
                            text = text[start:end]
                        final_review_json = json.loads(text)
                    except json.JSONDecodeError:
                        # fallback: treat as plain text review
                        final_review_json = {
                            "summary": "",
                            "inline_comments": [],
                            "overall_comment": block.text
                        }
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

                await send_ws_update(get_ws(), {
                    "type": "tool_call",
                    "tool": tool_name,
                    "input": tool_args,
                })

                tool_fn = TOOL_FUNCTIONS.get(tool_name)
                try:
                    result = tool_fn(**tool_args) if tool_fn else f"Unknown tool: {tool_name}"
                    # save the diff text so we can parse positions later
                    if tool_name == "get_pr_diff":
                        diff_text = str(result)
                except Exception as e:
                    result = f"Tool error: {e}"

                await send_ws_update(get_ws(), {
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
                    try:
                        text = block.text.strip()
                        start = text.find("{")
                        end = text.rfind("}") + 1
                        if start != -1 and end > start:
                            text = text[start:end]
                        final_review_json = json.loads(text)
                    except json.JSONDecodeError:
                        final_review_json = {
                            "summary": "",
                            "inline_comments": [],
                            "overall_comment": block.text
                        }
                    break
            break

    # post review to GitHub
    if final_review_json:
        await send_ws_update(get_ws(), {"type": "status", "message": "Posting review to GitHub..."})
        try:
            repo = gh.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)

            overall_comment = final_review_json.get("overall_comment", "")
            inline_comments = final_review_json.get("inline_comments", [])

            # parse diff positions if we have inline comments
            if inline_comments and diff_text:
                file_positions = parse_diff_positions(diff_text)

                # build valid inline comments with correct positions
                valid_comments = []
                for c in inline_comments:
                    path = c.get("path", "")
                    position = c.get("position")
                    body = c.get("body", "")

                    if path and position and body:
                        valid_comments.append({
                            "path": path,
                            "position": position,
                            "body": body,
                        })

                if valid_comments:
                    try:
                        pr.create_review(
                            body=overall_comment,
                            event="COMMENT",
                            comments=valid_comments,
                        )
                        await send_ws_update(get_ws(), {
                            "type": "status",
                            "message": f"Posted review with {len(valid_comments)} inline comments"
                        })
                    except Exception as e:
                        # fallback to plain comment if inline fails
                        await send_ws_update(get_ws(), {
                            "type": "status",
                            "message": f"Inline comments failed ({e}), posting as regular comment"
                        })
                        pr.create_issue_comment(overall_comment)
                else:
                    pr.create_issue_comment(overall_comment)
            else:
                pr.create_issue_comment(overall_comment)

            save_review(repo_full_name, pr_number, pr_title, overall_comment)

            await send_ws_update(get_ws(), {
                "type": "complete",
                "message": "Review posted!",
                "review": overall_comment,
            })

        except Exception as e:
            await send_ws_update(get_ws(), {"type": "error", "message": f"Failed to post: {e}"})
    else:
        await send_ws_update(get_ws(), {"type": "error", "message": "Agent did not produce a review."})