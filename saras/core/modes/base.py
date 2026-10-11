from dataclasses import dataclass

from saras.integrations.obsidian_vault import read_note_body


@dataclass
class ModeResult:
    reply: str
    note_path: str | None = None  # set when the result was persisted to the Vault

    def full_text(self) -> str:
        """The saved note's body, which has more than the chat reply (a Discovery reply is
        only a short summary); the reply itself if nothing was saved or the note is gone."""
        if self.note_path:
            body = read_note_body(self.note_path)
            if body:
                return body
        return self.reply
