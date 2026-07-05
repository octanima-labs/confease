import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


__all__ = [
    "TERMINAL_EDITORS",
    "VISUAL_EDITORS",
    "EDITORS",
    "TextEditor",
]


TERMINAL_EDITORS = [["sensible-editor"], ["editor"], ["nano"], ["vim"], ["vi"]]
VISUAL_WAIT_FLAGS = {
    "code": "--wait",
    "code-insiders": "--wait",
    "codium": "--wait",
    "subl": "--wait",
    "sublime-text": "--wait",
    "sublime_text": "--wait",
}
VISUAL_EDITORS = [
    ["code", "--wait"],
    ["code-insiders", "--wait"],
    ["codium", "--wait"],
    ["subl", "--wait"],
    ["sublime-text", "--wait"],
    ["notepadpp.exe"],
    ["notepad.exe"],
]
EDITORS = [*TERMINAL_EDITORS, *VISUAL_EDITORS]


class TextEditor:
    """Small blocking text-editor launcher."""

    def __init__(self, editor: str | None = None):
        self._editor: list[str] | None = None
        self.editor = editor

    @property
    def editor(self):
        """Return the configured editor command, or None for auto-detection."""
        return self._editor

    @editor.setter
    def editor(self, value: str | None):
        if value is None:
            self._editor = None
            return

        try:
            command = shlex.split(value)
        except ValueError as exc:
            raise RuntimeError(f"Invalid editor command: {value}") from exc
        if not command:
            raise RuntimeError("Editor command cannot be empty")
        self._editor = command

    @staticmethod
    def _with_wait_flag(command: list[str]) -> list[str]:
        """Add blocking flags for known visual editors when omitted."""
        executable = Path(command[0]).name.lower()
        wait_flag = VISUAL_WAIT_FLAGS.get(executable)
        if wait_flag and wait_flag not in command[1:]:
            return [command[0], wait_flag, *command[1:]]
        return command

    @staticmethod
    def _split_env_editor(value: str) -> list[str]:
        try:
            return shlex.split(value)
        except ValueError as exc:
            raise RuntimeError(f"Invalid editor command: {value}") from exc

    def _editor_command(self) -> list[str]:
        if self._editor:
            editors = [self._editor]
        else:
            editors = list(EDITORS)
            env_editor = os.environ.get("EDITOR", "").strip() or os.environ.get("VISUAL", "").strip()
            if env_editor:
                editor_command = self._split_env_editor(env_editor)
                if editor_command:
                    editors.insert(0, editor_command)

        for command in editors:
            if shutil.which(command[0]):
                return self._with_wait_flag(command)
        raise RuntimeError(f"Text editor not found '{self._editor}'" if self._editor else "No text editor found")

    def open(self, path: str | Path) -> str:
        """Open the configured editor and return the edited path."""
        if path is None:
            raise ValueError("Path not provided")
        try:
            abs_path = Path(path).expanduser()
            with open(abs_path, mode="a+", encoding="utf-8") as message_file:
                subprocess.run([*self._editor_command(), message_file.name], check=True)
                return str(abs_path)
        except OSError as error:
            raise Exception(f"could not open text editor: {error}") from error
        except subprocess.CalledProcessError as error:
            raise Exception(f"text editor process failed: {error}") from error

    def read(self):
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+",
                encoding="utf-8",
            ) as message_file:
                subprocess.run([*self._editor_command(), message_file.name], check=True)
                message_file.seek(0)
                return message_file.read()
        except OSError as error:
            raise Exception(f"could not open text editor: {error}") from error
        except subprocess.CalledProcessError as error:
            raise Exception(f"text editor process failed: {error}") from error


def usage():
    editor = TextEditor()
    editor.open("~/.bashrc")
    return editor.read()
