from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src import telegram_sender


class FakeResponse:
    def __init__(self, ok: bool = True, status_code: int = 200, text: str = '{"ok":true}'):
        self.ok = ok
        self.status_code = status_code
        self.text = text


def write_env(project_root: Path) -> None:
    (project_root / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=test_token\n"
        "TELEGRAM_CHAT_ID=123456789\n",
        encoding="utf-8",
    )


def create_output_files(output_dir: Path, summary_text: str = "hello") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "telegram_summary.txt").write_text(summary_text, encoding="utf-8")
    (output_dir / "daily_packet.md").write_text("# Daily Packet\n", encoding="utf-8")
    (output_dir / "prompt_for_gpt.txt").write_text("GPT prompt\n", encoding="utf-8")
    (output_dir / "prompt_for_claude.txt").write_text("Claude prompt\n", encoding="utf-8")


def test_split_message_under_limit_returns_single_chunk() -> None:
    chunks = telegram_sender._split_message("abc", max_chars=4000)

    assert chunks == ["abc"]


def test_split_message_over_limit_splits_chunks() -> None:
    text = "a" * 4500

    chunks = telegram_sender._split_message(text, max_chars=4000)

    assert len(chunks) == 2
    assert len(chunks[0]) == 4000
    assert len(chunks[1]) == 500


def test_split_message_prefers_newline() -> None:
    text = ("a" * 100) + "\n" + ("b" * 100)

    chunks = telegram_sender._split_message(text, max_chars=120)

    assert len(chunks) == 2
    assert chunks[0] == "a" * 100
    assert chunks[1] == "b" * 100


def test_missing_env_disables_telegram_without_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "output"
    create_output_files(output_dir)

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def fake_post(*args, **kwargs):
        raise AssertionError("requests.post should not be called when Telegram env is missing")

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    result = telegram_sender.send_telegram_outputs(
        project_root=tmp_path,
        output_dir=output_dir,
    )

    assert result["enabled"] is False
    assert result["ok"] is False
    assert any("TELEGRAM_BOT_TOKEN is missing" in note for note in result["data_quality_notes"])
    assert any("TELEGRAM_CHAT_ID is missing" in note for note in result["data_quality_notes"])


def test_send_telegram_outputs_sends_summary_and_three_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_env(tmp_path)

    output_dir = tmp_path / "output"
    create_output_files(output_dir)

    calls = []

    def fake_post(url, data=None, files=None, timeout=None):
        calls.append(
            {
                "url": url,
                "data": data,
                "has_files": files is not None,
                "timeout": timeout,
            }
        )
        return FakeResponse(ok=True)

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    result = telegram_sender.send_telegram_outputs(
        project_root=tmp_path,
        output_dir=output_dir,
    )

    assert result["enabled"] is True
    assert result["ok"] is True
    assert result["messages_sent"] == 1
    assert result["documents_sent"] == 3
    assert result["missing_files"] == []
    assert result["errors"] == []

    send_message_calls = [call for call in calls if call["url"].endswith("/sendMessage")]
    send_document_calls = [call for call in calls if call["url"].endswith("/sendDocument")]

    assert len(send_message_calls) == 1
    assert len(send_document_calls) == 3

    # parse_mode should not be sent.
    assert "parse_mode" not in send_message_calls[0]["data"]


def test_long_summary_is_split_into_multiple_send_message_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_env(tmp_path)

    output_dir = tmp_path / "output"
    create_output_files(output_dir, summary_text="a" * 8500)

    calls = []

    def fake_post(url, data=None, files=None, timeout=None):
        calls.append({"url": url, "data": data, "has_files": files is not None})
        return FakeResponse(ok=True)

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    result = telegram_sender.send_telegram_outputs(
        project_root=tmp_path,
        output_dir=output_dir,
    )

    send_message_calls = [call for call in calls if call["url"].endswith("/sendMessage")]

    assert result["messages_sent"] == 3
    assert len(send_message_calls) == 3
    assert all(len(call["data"]["text"]) <= 4000 for call in send_message_calls)


def test_missing_document_is_recorded_but_does_not_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_env(tmp_path)

    output_dir = tmp_path / "output"
    create_output_files(output_dir)

    missing_file = output_dir / "prompt_for_claude.txt"
    missing_file.unlink()

    def fake_post(url, data=None, files=None, timeout=None):
        return FakeResponse(ok=True)

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    notes: list[str] = []

    result = telegram_sender.send_telegram_outputs(
        project_root=tmp_path,
        output_dir=output_dir,
        data_quality_notes=notes,
    )

    assert result["enabled"] is True
    assert result["ok"] is False
    assert result["messages_sent"] == 1
    assert result["documents_sent"] == 2
    assert str(missing_file) in result["missing_files"]
    assert any("missing document file" in note for note in notes)


def test_telegram_api_error_is_recorded_without_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_env(tmp_path)

    output_dir = tmp_path / "output"
    create_output_files(output_dir)

    def fake_post(url, data=None, files=None, timeout=None):
        if url.endswith("/sendMessage"):
            return FakeResponse(ok=False, status_code=401, text='{"ok":false,"description":"Unauthorized"}')
        return FakeResponse(ok=True)

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)

    result = telegram_sender.send_telegram_outputs(
        project_root=tmp_path,
        output_dir=output_dir,
    )

    assert result["enabled"] is True
    assert result["ok"] is False
    assert result["messages_sent"] == 0
    assert result["documents_sent"] == 3
    assert any("summary send failed" in error for error in result["errors"])
    assert any("Unauthorized" in note for note in result["data_quality_notes"])