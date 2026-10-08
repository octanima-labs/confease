import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

__all__ = [
    "EDITORS",
    "TERMINAL_EDITORS",
    "VISUAL_EDITORS",
    "TextEditor",
]


TERMINAL_EDITORS = [["nano"], ["vim"], ["nvim"], ["vi"]]
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
    """Small blocking text-editor launcher.

    ``TextEditor`` resolves an explicit editor command, ``EDITOR``/``VISUAL``,
    or a small list of common terminal and visual editors. Known visual editors
    receive a wait flag when needed so callers can safely read the file after
    the process exits.
    """

    def __init__(self, editor: str | None = None):
        """Create an editor launcher.

        Args:
            editor: Optional shell-style editor command, for example
                ``"nano -w"`` or ``"code --wait"``. When omitted, the launcher
                auto-detects an available editor.

        Raises:
            RuntimeError: If the command string cannot be parsed or is empty.
        """
        self._editor: list[str] | None = None
        self.editor = editor

    @property
    def editor(self):
        """Return the configured editor command, or None for auto-detection."""
        return self._editor

    @editor.setter
    def editor(self, value: str | None):
        """Configure an explicit editor command or return to auto-detection."""
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
        """Parse an editor command from an environment variable."""
        try:
            return shlex.split(value)
        except ValueError as exc:
            raise RuntimeError(f"Invalid editor command: {value}") from exc

    def _editor_command(self) -> list[str]:
        """Return the first available editor command.

        Raises:
            RuntimeError: If no configured or auto-detected editor is available.
        """
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
        """Open the configured editor for an existing or new file path.

        Args:
            path: File path to open.

        Notes:
            The launcher does not create or open the file itself. A missing
            file is created only if the editor saves it.

        Returns:
            The expanded file path as a string after the editor exits.

        Raises:
            ValueError: If ``path`` is ``None``.
            Exception: If the editor cannot be launched or exits unsuccessfully.
        """
        if path is None:
            raise ValueError("Path not provided")
        abs_path = Path(path).expanduser()
        self._run([*self._editor_command(), str(abs_path)])
        return str(abs_path)

    @staticmethod
    def _run(command: list[str]):
        """Run a blocking editor command with the launcher's usual errors."""
        try:
            subprocess.run(command, check=True)
        except OSError as error:
            raise Exception(f"could not open text editor: {error}") from error  # noqa: TRY002 - preserve launcher error API
        except subprocess.CalledProcessError as error:
            raise Exception(f"text editor process failed: {error}") from error  # noqa: TRY002 - preserve launcher error API

    def _open_preloaded(self, path: Path, template: Path) -> bool:
        """Use native unsaved-buffer insertion, or return false for draft fallback.

        Only explicit Vim/Neovim executables are recognized; ``vi`` and custom
        commands use the fallback. Successful native launch returns true even
        when the user abandons the buffer. The caller checks the target itself.
        """
        command = self._editor_command()
        if Path(command[0]).name.lower() not in {"vim", "vim.exe", "nvim", "nvim.exe"}:
            return False
        # Vim single-quoted literals escape apostrophes by doubling them. Split
        # line breaks into expressions so paths cannot inject Ex commands.
        source = "'" + str(template.absolute()).replace("'", "''").replace(
            "\n", "' . nr2char(10) . '").replace("\r", "' . nr2char(13) . '") + "'"
        preload = (
            "if empty(getftype(expand('%:p'))) | "
            f"execute 'silent 0read ' . fnameescape({source}) | "
            "setlocal modified | call cursor(1, 1) | endif"
        )
        self._run([*command, "-c", preload, "--", str(path.absolute())])
        return True

    def read(self):
        """Open a temporary file and return its contents after editing.

        Returns:
            The text written by the editor.

        Raises:
            Exception: If the editor cannot be launched or exits unsuccessfully.
        """
        try:
            with tempfile.NamedTemporaryFile(
                mode="w+",
                encoding="utf-8",
            ) as message_file:
                subprocess.run([*self._editor_command(), message_file.name], check=True)
                message_file.seek(0)
                return message_file.read()
        except OSError as error:
            raise Exception(f"could not open text editor: {error}") from error  # noqa: TRY002 - preserve launcher error API
        except subprocess.CalledProcessError as error:
            raise Exception(f"text editor process failed: {error}") from error  # noqa: TRY002 - preserve launcher error API


def usage():
    editor = TextEditor()
    editor.open("~/.bashrc")
    return editor.read()
