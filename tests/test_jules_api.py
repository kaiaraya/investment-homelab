from scripts.legacy.jules_bridge import (
    match_task_branch,
    source_name_from_remote_url,
)


def test_source_name_from_remote_url_ssh():
    assert (
        source_name_from_remote_url("git@github.com:kaiaraya/investment-homelab.git")
        == "sources/github/kaiaraya/investment-homelab"
    )


def test_source_name_from_remote_url_https_with_and_without_dot_git():
    assert (
        source_name_from_remote_url("https://github.com/kaiaraya/investment-homelab.git")
        == "sources/github/kaiaraya/investment-homelab"
    )
    assert (
        source_name_from_remote_url("https://github.com/kaiaraya/investment-homelab")
        == "sources/github/kaiaraya/investment-homelab"
    )


def test_source_name_from_remote_url_non_github_returns_none():
    assert source_name_from_remote_url("https://gitlab.com/foo/bar.git") is None
    assert source_name_from_remote_url("not a url") is None


def test_match_task_branch_prefers_session_id_suffix():
    branches = [
        "task/sq1-nego-policy-and-dryrun-badge",
        "task/sq1-nego-policy-and-dryrun-badge-3690014478060889858",
    ]
    assert (
        match_task_branch(branches, "sq1-nego-policy-and-dryrun-badge", session_id="3690014478060889858")
        == "task/sq1-nego-policy-and-dryrun-badge-3690014478060889858"
    )


def test_match_task_branch_exact_or_shortest_fallback():
    assert match_task_branch(["task/foo"], "foo") == "task/foo"
    assert match_task_branch(["task/foo-123"], "foo") == "task/foo-123"
    assert match_task_branch(["task/foo", "task/foo-123"], "foo") == "task/foo"
    assert match_task_branch(["task/bar"], "foo") is None
