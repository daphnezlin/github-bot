import pytest
from unittest.mock import MagicMock, patch
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGetPrDiff:
    def _make_file(self, filename, patch_text, status="modified"):
        f = MagicMock()
        f.filename = filename
        f.patch = patch_text
        f.status = status
        return f

    @patch("tools.github_tools.gh")
    def test_returns_diff_for_python_file(self, mock_gh):
        mock_file = self._make_file("src/main.py", "@@ -1,3 +1,4 @@\n+new line")
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [mock_file]
        from tools.github_tools import get_pr_diff
        result = get_pr_diff("owner/repo", 1)
        assert "src/main.py" in result
        assert "new line" in result

    @patch("tools.github_tools.gh")
    def test_truncates_large_diffs(self, mock_gh):
        big_patch = "\n".join([f"line {i}" for i in range(4000)])
        files = [self._make_file(f"file{i}.py", big_patch) for i in range(3)]
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = files
        from tools.github_tools import get_pr_diff
        result = get_pr_diff("owner/repo", 1)
        assert "truncated" in result

    @patch("tools.github_tools.gh")
    def test_handles_binary_file(self, mock_gh):
        f = MagicMock()
        f.filename = "image.png"
        f.patch = None
        f.status = "added"
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [f]
        from tools.github_tools import get_pr_diff
        result = get_pr_diff("owner/repo", 1)
        assert "binary or no diff" in result


class TestRunLinter:
    @patch("tools.github_tools.gh")
    def test_no_python_files(self, mock_gh):
        f = MagicMock()
        f.filename = "README.md"
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [f]
        from tools.github_tools import run_linter
        result = run_linter("owner/repo", 1)
        assert "not applicable" in result

    @patch("tools.github_tools.subprocess.run")
    @patch("tools.github_tools.gh")
    def test_ruff_finds_issues(self, mock_gh, mock_run):
        f = MagicMock()
        f.filename = "src/bad.py"
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [f]
        mock_run.return_value = MagicMock(stdout="src/bad.py:1:1: E501 line too long")
        from tools.github_tools import run_linter
        result = run_linter("owner/repo", 1)
        assert "E501" in result

    @patch("tools.github_tools.subprocess.run", side_effect=FileNotFoundError)
    @patch("tools.github_tools.gh")
    def test_ruff_not_installed(self, mock_gh, mock_run):
        f = MagicMock()
        f.filename = "app.py"
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [f]
        from tools.github_tools import run_linter
        result = run_linter("owner/repo", 1)
        assert "not installed" in result


class TestGetTestCoverage:
    @patch("tools.github_tools.gh")
    def test_detects_missing_tests(self, mock_gh):
        f = MagicMock()
        f.filename = "src/payments.py"
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [f]
        from tools.github_tools import get_test_coverage
        result = get_test_coverage("owner/repo", 1)
        assert "lack tests" in result
        assert "payments.py" in result

    @patch("tools.github_tools.gh")
    def test_detects_present_tests(self, mock_gh):
        src = MagicMock()
        src.filename = "src/payments.py"
        tst = MagicMock()
        tst.filename = "tests/test_payments.py"
        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = [src, tst]
        from tools.github_tools import get_test_coverage
        result = get_test_coverage("owner/repo", 1)
        assert "appear to have tests" in result


class TestSearchRelatedIssues:
    @patch("tools.github_tools.gh")
    def test_finds_related_issue(self, mock_gh):
        issue = MagicMock()
        issue.number = 42
        issue.title = "rate limiter is broken"
        issue.pull_request = None
        mock_gh.get_repo.return_value.get_issues.return_value = [issue]
        from tools.github_tools import search_related_issues
        result = search_related_issues("owner/repo", 1, "fix rate limiter bug", "")
        assert "#42" in result
        assert "rate limiter" in result

    @patch("tools.github_tools.gh")
    def test_no_issues_found(self, mock_gh):
        mock_gh.get_repo.return_value.get_issues.return_value = []
        from tools.github_tools import search_related_issues
        result = search_related_issues("owner/repo", 1, "fix obscure thing", "")
        assert "No related issues" in result


class TestWebhookSecurity:
    def test_valid_signature_accepted(self):
        import hmac, hashlib
        from main import verify_github_signature
        secret = b"testsecret"
        payload = b'{"action":"opened"}'
        sig = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "testsecret"}):
            assert verify_github_signature(payload, sig) is True

    def test_invalid_signature_rejected(self):
        from main import verify_github_signature
        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "testsecret"}):
            assert verify_github_signature(b"payload", "sha256=wrongsig") is False


@pytest.mark.asyncio
async def test_agent_posts_review_no_tools():
    from google.genai import types as gtypes
    with patch("agent.reviewer.client") as mock_client, \
         patch("agent.reviewer.gh") as mock_gh:

        real_part = gtypes.Part(text="## 🤖 AI Code Review\n\nLooks good!")
        real_content = gtypes.Content(role="model", parts=[real_part])

        mock_candidate = MagicMock()
        mock_candidate.content = real_content
        mock_client.models.generate_content.return_value = MagicMock(
            candidates=[mock_candidate]
        )

        mock_pr = MagicMock()
        mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

        from agent.reviewer import run_review_agent
        await run_review_agent("owner/repo", 1, "fix bug", "", websocket=None)

        mock_pr.create_issue_comment.assert_called_once()
        assert "AI Code Review" in mock_pr.create_issue_comment.call_args[0][0]


@pytest.mark.asyncio
async def test_agent_calls_tool_then_reviews():
    from google.genai import types as gtypes
    with patch("agent.reviewer.client") as mock_client, \
         patch("agent.reviewer.gh") as mock_gh:

        # Round 1: real tool call part
        tool_part = gtypes.Part(
            function_call=gtypes.FunctionCall(
                name="get_pr_diff",
                args={"repo_full_name": "owner/repo", "pr_number": 1}
            )
        )
        tool_content = gtypes.Content(role="model", parts=[tool_part])

        # Round 2: real text review part
        review_part = gtypes.Part(text="## 🤖 AI Code Review\n\nAll good.")
        review_content = gtypes.Content(role="model", parts=[review_part])

        mock_candidate_1 = MagicMock()
        mock_candidate_1.content = tool_content
        mock_candidate_2 = MagicMock()
        mock_candidate_2.content = review_content

        mock_client.models.generate_content.side_effect = [
            MagicMock(candidates=[mock_candidate_1]),
            MagicMock(candidates=[mock_candidate_2]),
        ]

        mock_gh.get_repo.return_value.get_pull.return_value.get_files.return_value = []
        mock_pr = MagicMock()
        mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

        from agent.reviewer import run_review_agent
        await run_review_agent("owner/repo", 1, "add feature", "", websocket=None)

        assert mock_client.models.generate_content.call_count == 2
        mock_pr.create_issue_comment.assert_called_once()