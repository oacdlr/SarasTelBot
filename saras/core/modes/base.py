from dataclasses import dataclass


@dataclass
class ModeResult:
    reply: str
    note_path: str | None = None  # set when the result was persisted to the Vault
