# Claude via the official Anthropic SDK (pip install anthropic). Key from ANTHROPIC_API_KEY by default.
import os
from .base import Provider, LLMError

class AnthropicAPI(Provider):
    kind = "anthropic"

    def __init__(self, model="claude-haiku-5-5", api_key_env="ANTHROPIC_API_KEY", base_url=None,
                 max_tokens=4000, **kw):
        super().__init__(model, **kw)
        try:
            import anthropic
        except ImportError:
            raise LLMError("provider 'anthropic' needs the SDK: pip install anthropic") from None
        if not os.environ.get(api_key_env):
            raise LLMError(f"env {api_key_env} is not set")
        self._errors = (anthropic.APIError,)
        self.client = anthropic.Anthropic(api_key=os.environ.get(api_key_env), base_url=base_url,
                                          timeout=self.timeout, max_retries=2)
        self.max_tokens = max_tokens

    def complete(self, prompt):
        try:
            msg = self.client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                              messages=[{"role": "user", "content": prompt}])
        except self._errors as e:
            raise LLMError(repr(e)[:200]) from None
        return "".join(b.text for b in msg.content if b.type == "text")
