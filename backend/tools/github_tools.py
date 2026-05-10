import os
import subprocess
from github import Github

gh = Github(os.getenv("GITHUB_TOKEN"))


def get_pr_diff(repo_full_name: str, pr_number: int) -> str:
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    files = pr.get_files()
    diff_parts = []
    total_lines = 0
    for f in files:
        if total_lines > 3000:
            diff_parts.append(f"\n[truncated — remaining files omitted]")
            break
        patch = getattr(f, "patch", None) or "[binary or no diff]"
        diff_parts.append(f"### {f.filename} ({f.status})\n{patch}")
        total_lines += patch.count("\n")
    return "\n\n".join(diff_parts)


def run_linter(repo_full_name: str, pr_number: int) -> str:
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    python_files = [f.filename for f in pr.get_files() if f.filename.endswith(".py")]
    if not python_files:
        return "No Python files changed — linter not applicable."
    try:
        result = subprocess.run(
            ["ruff", "check", "--select=E,W,F"] + python_files,
            capture_output=True, text=True, timeout=30
        )
        return result.stdout or "ruff found no issues."
    except FileNotFoundError:
        return f"ruff not installed. Python files changed: {', '.join(python_files)}"


def get_test_coverage(repo_full_name: str, pr_number: int) -> str:
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    changed = [f.filename for f in pr.get_files()]
    source_files = [f for f in changed if not any(p in f for p in ("test", "spec"))]
    test_files = [f for f in changed if any(p in f for p in ("test_", "_test.", ".spec.", ".test."))]
    untested = []
    for src in source_files:
        base = src.replace(".py", "").replace(".ts", "").split("/")[-1]
        has_test = any(base in t for t in test_files)
        if not has_test:
            untested.append(src)
    if not untested:
        return f"All {len(source_files)} changed files appear to have tests."
    return f"{len(untested)} file(s) may lack tests:\n" + "\n".join(f"  - {f}" for f in untested)


def search_related_issues(repo_full_name: str, pr_number: int, pr_title: str, pr_body: str) -> str:
    repo = gh.get_repo(repo_full_name)
    stopwords = {"fix", "add", "update", "remove", "the", "a", "an", "and", "or", "for"}
    keywords = [w for w in pr_title.lower().split() if w not in stopwords and len(w) > 3]
    if not keywords:
        return "Could not extract keywords from PR title."
    try:
        issues = repo.get_issues(state="open")
        matches = []
        for issue in issues:
            if issue.pull_request:
                continue
            if any(k in issue.title.lower() for k in keywords):
                matches.append(f"  #{issue.number}: {issue.title}")
            if len(matches) >= 5:
                break
        return "Related issues:\n" + "\n".join(matches) if matches else "No related issues found."
    except Exception as e:
        return f"Issue search failed: {e}"


TOOL_FUNCTIONS = {
    "get_pr_diff": get_pr_diff,
    "run_linter": run_linter,
    "get_test_coverage": get_test_coverage,
    "search_related_issues": search_related_issues,
}