from subprocess import CompletedProcess

from gh_action.action import generate_registry


def test_generate_registry_rejects_crawler_fetch_errors(
    monkeypatch,
    tmp_path,
    capsys,
):
    def fake_run(*args, **kwargs):
        assert kwargs["capture_output"] is True
        return CompletedProcess(
            args,
            0,
            stdout="Saved registry\n",
            stderr="Error fetching https://example.com/g.json: invalid JSON\n",
        )

    monkeypatch.setattr("gh_action.action.run", fake_run)

    result = generate_registry(
        tmp_path,
        "https://example.com/repo.json",
        tmp_path / "out.json",
    )

    assert not result.succeeded
    assert result.fetch_errors == [
        "Error fetching https://example.com/g.json: invalid JSON"
    ]

    captured = capsys.readouterr()
    assert captured.out == "Saved registry\n"
    assert "Error fetching https://example.com/g.json" in captured.err
    assert "::error ::Registry generation reported a source fetch failure." in captured.err


def test_generate_registry_allows_other_crawler_stderr(
    monkeypatch,
    tmp_path,
):
    def fake_run(*args, **kwargs):
        return CompletedProcess(
            args,
            0,
            stdout="Saved registry\n",
            stderr="A non-fatal warning\n",
        )

    monkeypatch.setattr("gh_action.action.run", fake_run)

    result = generate_registry(
        tmp_path,
        "https://example.com/repo.json",
        tmp_path / "out.json",
    )

    assert result.succeeded
    assert result.fetch_errors == []
