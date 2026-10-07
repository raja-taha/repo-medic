import pytest

from repomedic_core.github_client import parse_issue_url


def test_parse_issue_url():
    owner, repo, number = parse_issue_url("https://github.com/acme/widgets/issues/42")
    assert owner == "acme"
    assert repo == "widgets"
    assert number == 42


def test_parse_issue_url_invalid():
    with pytest.raises(ValueError):
        parse_issue_url("https://example.com/not-github")