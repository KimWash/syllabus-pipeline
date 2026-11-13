class LLMError(RuntimeError):
    pass

class Provider:
    """One model behind one backend. Subclasses implement complete()."""
    kind = "base"

    def __init__(self, model="", concurrency=2, timeout=180):
        self.model, self.concurrency, self.timeout = model, concurrency, timeout

    @property
    def label(self):
        return f"{self.kind}:{self.model}" if self.model else self.kind

    def complete(self, prompt: str) -> str:
        """Send one user prompt, return the text answer. Raise LLMError on failure."""
        raise NotImplementedError
