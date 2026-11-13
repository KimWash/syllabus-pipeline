# Any command-line model: the prompt goes to stdin (or into an argument containing {prompt}),
# the answer is read from stdout. {model} in the command is replaced by `model`.
#   claude -p --model {model}        gemini -m {model}        ollama run {model}        codex exec -m {model} -
import os, subprocess
from .base import Provider, LLMError

class CLI(Provider):
    kind = "cli"

    def __init__(self, command, model="", env=None, **kw):
        super().__init__(model, **kw)
        if not command:
            raise ValueError("provider 'cli' needs command = [...]")
        self.command, self.env = list(command), env or {}

    def complete(self, prompt):
        args = [a.replace("{model}", self.model) for a in self.command]
        use_stdin = not any("{prompt}" in a for a in args)
        args = [a.replace("{prompt}", prompt) for a in args]
        try:
            p = subprocess.run(args, input=prompt if use_stdin else None, capture_output=True, text=True,
                               timeout=self.timeout, env={**os.environ, **self.env})
        except FileNotFoundError:
            raise LLMError(f"command not found: {args[0]}") from None
        except subprocess.TimeoutExpired:
            raise LLMError(f"timeout after {self.timeout}s") from None
        if p.returncode != 0:
            raise LLMError(f"exit {p.returncode}: {(p.stderr or p.stdout)[-300:]}")
        return p.stdout
