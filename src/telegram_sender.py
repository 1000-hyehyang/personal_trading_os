"""
Telegram sender module for Personal Trading OS MVP.

Responsibilities:
- Read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env / environment.
- Send output/telegram_summary.txt via Telegram sendMessage.
- Send selected output files via Telegram sendDocument.
- Split long messages into <= 4000 character chunks.
- Never crash the whole program on missing files or Telegram API failures.
- Record issues into data_quality_notes.
- Avoid parse_mode by default to prevent Markdown parsing errors.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import dotenv_values


TELEGRAM_MAX_MESSAGE_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 30

SUMMARY_FILENAME = "telegram_summary.txt"

DOCUMENT_FILENAMES = [
    "daily_packet.md",
    "prompt_for_gpt.txt",
    "prompt_for_claude.txt",
]


@dataclass
class TelegramSendResult:
    """Structured result for Telegram send attempts."""

    enabled: bool
    ok: bool
    messages_sent: int = 0
    documents_sent: int = 0
    missing_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    data_quality_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ok": self.ok,
            "messages_sent": self.messages_sent,
            "documents_sent": self.documents_sent,
            "missing_files": self.missing_files,
            "errors": self.errors,
            "data_quality_notes": self.data_quality_notes,
        }


def get_project_root() -> Path:
    """
    Resolve project root from this file location.

    Expected layout:
        C:\\trading\\personal_trading_os\\src\\telegram_sender.py
    So project root is parent of src.
    """
    return Path(__file__).resolve().parents[1]


def _get_logger(logger: logging.Logger | None = None) -> logging.Logger:
    if logger is not None:
        return logger

    default_logger = logging.getLogger("personal_trading_os.telegram_sender")
    if not default_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        default_logger.addHandler(handler)
    default_logger.setLevel(logging.INFO)
    return default_logger


def _append_note(
    notes: list[str],
    message: str,
    logger: logging.Logger,
    level: str = "warning",
) -> None:
    notes.append(message)

    if level == "error":
        logger.error(message)
    elif level == "info":
        logger.info(message)
    else:
        logger.warning(message)


def _load_telegram_credentials(project_root: Path) -> tuple[str, str]:
    """
    Read Telegram credentials from project_root/.env without searching parent
    directories or mutating process-wide os.environ.

    Precedence:
    1. project_root/.env
    2. existing OS environment variables

    This prevents tests using tmp_path from accidentally loading the real
    project .env in CWD.
    """
    env_path = project_root / ".env"
    env_values: dict[str, str | None] = {}

    if env_path.exists():
        env_values = dotenv_values(env_path)

    token = str(
        env_values.get("TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN", "")
        or ""
    ).strip()

    chat_id = str(
        env_values.get("TELEGRAM_CHAT_ID")
        or os.getenv("TELEGRAM_CHAT_ID", "")
        or ""
    ).strip()

    return token, chat_id


def _split_message(text: str, max_chars: int = TELEGRAM_MAX_MESSAGE_CHARS) -> list[str]:
    """
    Split a Telegram message into safe chunks.

    Telegram sendMessage supports up to 4096 chars, but the project spec uses
    4000 chars as the operational split size.
    """
    if not text:
        return [""]

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n", 0, max_chars)

        # If there is no useful newline, hard split.
        if split_at <= 0:
            split_at = max_chars

        chunk = remaining[:split_at].rstrip()
        if chunk:
            chunks.append(chunk)

        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks or [""]


def _telegram_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _safe_response_error(response: requests.Response) -> str:
    """
    Build a safe error message from a Telegram response without exposing tokens.
    """
    try:
        body = response.text
    except Exception:
        body = "<unable to read response text>"

    return f"Telegram API error: status={response.status_code}, body={body[:500]}"


def send_message(
    *,
    token: str,
    chat_id: str,
    text: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    logger: logging.Logger | None = None,
) -> int:
    """
    Send text message to Telegram.

    Returns:
        Number of message chunks successfully sent.

    Raises:
        requests.RequestException or RuntimeError on API failure.
    """
    log = _get_logger(logger)
    chunks = _split_message(text)
    sent_count = 0

    for idx, chunk in enumerate(chunks, start=1):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            # parse_mode intentionally omitted.
            "disable_web_page_preview": True,
        }

        response = requests.post(
            _telegram_api_url(token, "sendMessage"),
            data=payload,
            timeout=timeout,
        )

        if not response.ok:
            raise RuntimeError(_safe_response_error(response))

        sent_count += 1
        log.info("Telegram message chunk sent: %s/%s", idx, len(chunks))

    return sent_count


def send_document(
    *,
    token: str,
    chat_id: str,
    file_path: Path,
    caption: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    logger: logging.Logger | None = None,
) -> None:
    """
    Send one file as Telegram document.

    Raises:
        FileNotFoundError, requests.RequestException, or RuntimeError.
    """
    log = _get_logger(logger)

    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    payload: dict[str, str] = {
        "chat_id": chat_id,
    }

    if caption:
        payload["caption"] = caption[:1024]

    with file_path.open("rb") as file_obj:
        files = {
            "document": (file_path.name, file_obj),
        }

        response = requests.post(
            _telegram_api_url(token, "sendDocument"),
            data=payload,
            files=files,
            timeout=timeout,
        )

    if not response.ok:
        raise RuntimeError(_safe_response_error(response))

    log.info("Telegram document sent: %s", file_path)


def _coerce_external_notes(data_quality_notes: Any) -> list[str]:
    """
    Accept common note containers without coupling this module to packet_builder.

    Supported:
    - None
    - list[str]
    - dict containing "data_quality_notes": list
    - dict containing "missing", "delayed", "fallback_used" lists
    """
    if data_quality_notes is None:
        return []

    if isinstance(data_quality_notes, list):
        return data_quality_notes

    if isinstance(data_quality_notes, dict):
        if isinstance(data_quality_notes.get("data_quality_notes"), list):
            return data_quality_notes["data_quality_notes"]

        for key in ("missing", "delayed", "fallback_used"):
            value = data_quality_notes.get(key)
            if isinstance(value, list):
                return value

    return []


def validate_telegram_config(
    token: str | None,
    chat_id: str | None,
    notes: list[str],
    logger: logging.Logger,
) -> bool:
    """
    Validate Telegram credentials.

    Missing Telegram config is not fatal for the whole MVP. The caller can still
    generate output files and finish normally.
    """
    ok = True

    if not token:
        _append_note(
            notes,
            "Telegram disabled: TELEGRAM_BOT_TOKEN is missing.",
            logger,
            level="warning",
        )
        ok = False

    if not chat_id:
        _append_note(
            notes,
            "Telegram disabled: TELEGRAM_CHAT_ID is missing.",
            logger,
            level="warning",
        )
        ok = False

    return ok


def send_telegram_outputs(
    *,
    project_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    data_quality_notes: Any = None,
    logger: logging.Logger | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """
    Send MVP output files to Telegram.

    Sends:
    1. output/telegram_summary.txt -> sendMessage
    2. output/daily_packet.md -> sendDocument
    3. output/prompt_for_gpt.txt -> sendDocument
    4. output/prompt_for_claude.txt -> sendDocument

    Missing files and API errors are recorded, but not raised.

    Returns:
        dict version of TelegramSendResult.
    """
    log = _get_logger(logger)

    root = Path(project_root).resolve() if project_root else get_project_root()
    out_dir = Path(output_dir).resolve() if output_dir else root / "output"

    token, chat_id = _load_telegram_credentials(root)

    notes = _coerce_external_notes(data_quality_notes)

    if not validate_telegram_config(token, chat_id, notes, log):
        result = TelegramSendResult(
            enabled=False,
            ok=False,
            data_quality_notes=notes,
        )
        return result.to_dict()

    result = TelegramSendResult(
        enabled=True,
        ok=True,
        data_quality_notes=notes,
    )

    summary_path = out_dir / SUMMARY_FILENAME

    if summary_path.exists():
        try:
            summary_text = summary_path.read_text(encoding="utf-8")
            result.messages_sent += send_message(
                token=token,
                chat_id=chat_id,
                text=summary_text,
                timeout=timeout,
                logger=log,
            )
        except Exception as exc:
            result.ok = False
            error_message = f"Telegram summary send failed: {exc}"
            result.errors.append(error_message)
            _append_note(notes, error_message, log, level="error")
    else:
        result.ok = False
        result.missing_files.append(str(summary_path))
        _append_note(
            notes,
            f"Telegram skipped missing summary file: {summary_path}",
            log,
            level="warning",
        )

    for filename in DOCUMENT_FILENAMES:
        file_path = out_dir / filename

        if not file_path.exists():
            result.ok = False
            result.missing_files.append(str(file_path))
            _append_note(
                notes,
                f"Telegram skipped missing document file: {file_path}",
                log,
                level="warning",
            )
            continue

        try:
            send_document(
                token=token,
                chat_id=chat_id,
                file_path=file_path,
                caption=filename,
                timeout=timeout,
                logger=log,
            )
            result.documents_sent += 1
        except Exception as exc:
            result.ok = False
            error_message = f"Telegram document send failed for {filename}: {exc}"
            result.errors.append(error_message)
            _append_note(notes, error_message, log, level="error")

    return result.to_dict()


def main() -> int:
    """
    Manual test entrypoint.

    Usage:
        .\\.venv\\Scripts\\python.exe src\\telegram_sender.py
    """
    result = send_telegram_outputs()
    print(result)

    # Do not return non-zero only because Telegram failed.
    # The MVP should keep output generation separate from delivery failures.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())