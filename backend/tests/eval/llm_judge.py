"""
LLM-as-judge eval: scores agent reviews against human reviews.
Usage: python -m tests.eval.llm_judge
"""

import json
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

JUDGE_PROMPT = """You are evaluating an automated code review against a human one.
Score how well the agent review agrees with the human review.

Return ONLY valid JSON in exactly this format, no other text:
{
  "overall": <0-10>,
  "issues_found": <0-10>,
  "severity_accuracy": <0-10>,
  "actionability": <0-10>,
  "reasoning": "<one sentence>"
}

10 = perfect agreement, 0 = completely missed the point."""


# 10 realistic PR fixture pairs (agent review vs human review)
FIXTURES = [
    {
        "pr": "Add input validation to login endpoint",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Validation logic is clean
### ⚠️ Issues
- Missing rate limiting on login attempts
- No test for SQL injection edge case
### 🧪 Testing: No tests added for new validation""",
        "human": """Looks mostly good. Main concerns:
- Need rate limiting to prevent brute force
- Add tests for the validation logic
- SQL injection case not covered""",
    },
    {
        "pr": "Refactor database connection pooling",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Pool size is configurable
### ⚠️ Issues
- Connection timeout not handled
- No retry logic on connection failure
### 🧪 Testing: Missing integration tests""",
        "human": """Good refactor overall.
- Timeout handling is missing
- Should add retry with backoff
- Need integration tests with real DB""",
    },
    {
        "pr": "Add CSV export feature",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Clean implementation
### ⚠️ Issues
- Large datasets may cause memory issues (loads all rows)
- No streaming support
### 🧪 Testing: Happy path tested, edge cases missing""",
        "human": "Streams not used, will OOM on large exports. Tests look okay.",
    },
    {
        "pr": "Fix timezone bug in scheduler",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- UTC conversion looks correct
### ⚠️ Issues
- DST transitions not handled
- Hardcoded timezone in one place (line 42)
### 🧪 Testing: No DST edge case tests""",
        "human": "UTC fix is right but DST edge cases will still break. Line 42 hardcodes timezone.",
    },
    {
        "pr": "Add pagination to /users endpoint",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Cursor-based pagination is a good choice
### ⚠️ Issues
- Default page size (1000) is too large
- No max page size enforced
### 🧪 Testing: Pagination logic tested""",
        "human": "Cursor pagination good. Default limit of 1000 is dangerous, cap it at 100.",
    },
    {
        "pr": "Migrate from callbacks to async/await",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Async/await is cleaner
### ⚠️ Issues
- Some callbacks still remain in utils.js
- Error handling missing in two async functions
### 🧪 Testing: No new tests""",
        "human": "Good migration but utils.js still has callbacks. Missing error handling in async fns.",
    },
    {
        "pr": "Add Redis caching layer",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Cache invalidation strategy is sound
### ⚠️ Issues
- No TTL set on cache keys (memory leak risk)
- Redis connection not pooled
### 🧪 Testing: Cache hit/miss tested""",
        "human": "TTL missing on keys — this will grow unbounded. Pool the Redis connections.",
    },
    {
        "pr": "Implement JWT refresh tokens",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Refresh token rotation implemented
### ⚠️ Issues
- Refresh tokens not stored server-side (can't revoke)
- No expiry on refresh tokens
### 🧪 Testing: Basic auth flow tested""",
        "human": "Rotation is good but tokens aren't revocable. Add expiry. Tests are thin.",
    },
    {
        "pr": "Add file upload endpoint",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- File type validation present
### ⚠️ Issues
- No file size limit (DoS risk)
- Uploaded files stored in /tmp (not persistent)
### 🧪 Testing: No tests for malicious file types""",
        "human": "Missing size limit is a DoS vector. /tmp storage won't survive restarts.",
    },
    {
        "pr": "Optimize N+1 query in orders endpoint",
        "agent": """## 🤖 AI Code Review
### ✅ What looks good
- Eager loading fixes the N+1
### ⚠️ Issues
- Missing database index on orders.user_id
- Query still loads unused columns
### 🧪 Testing: Performance test missing""",
        "human": "N+1 fixed. Add index on user_id or it'll still be slow at scale.",
    },
]


def judge_pair(pr_title: str, agent_review: str, human_review: str) -> dict:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=JUDGE_PROMPT),
        contents=[f"PR: {pr_title}\n\nAGENT REVIEW:\n{agent_review}\n\nHUMAN REVIEW:\n{human_review}"],
    )
    text = response.candidates[0].content.parts[0].text.strip()
    # strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def run_eval(fixtures: list[dict]) -> dict:
    results = []
    print(f"Running eval on {len(fixtures)} PR fixtures...\n")

    for i, fix in enumerate(fixtures):
        try:
            score = judge_pair(fix["pr"], fix["agent"], fix["human"])
            results.append(score)
            print(f"[{i+1:2d}] {fix['pr'][:45]:<45} overall={score['overall']}/10  {score['reasoning'][:60]}")
        except Exception as e:
            print(f"[{i+1:2d}] ERROR: {e}")

    if not results:
        print("No results — check your API key.")
        return {}

    avg_overall        = sum(r["overall"] for r in results) / len(results)
    avg_issues         = sum(r["issues_found"] for r in results) / len(results)
    avg_severity       = sum(r["severity_accuracy"] for r in results) / len(results)
    avg_actionability  = sum(r["actionability"] for r in results) / len(results)
    agreement_pct      = sum(1 for r in results if r["overall"] >= 7) / len(results) * 100

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Eval results  ({len(results)} fixtures)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall avg score   : {avg_overall:.1f} / 10
Issues found        : {avg_issues:.1f} / 10
Severity accuracy   : {avg_severity:.1f} / 10
Actionability       : {avg_actionability:.1f} / 10
Agreement (≥7/10)   : {agreement_pct:.0f}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")

    return {
        "avg_overall": round(avg_overall, 1),
        "agreement_pct": round(agreement_pct),
        "n": len(results),
    }


if __name__ == "__main__":
    run_eval(FIXTURES)