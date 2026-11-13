# Any OpenAI-compatible /chat/completions endpoint: OpenAI, OpenRouter, a local router (FreeLLMAPI, LiteLLM),
# vLLM, LM Studio, Ollama's /v1 ...  stdlib only.
import os, json, urllib.request, urllib.error
from .base import Provider, LLMError

class OpenAICompat(Provider):
    kind = "openai"

    def __init__(self, model, base_url="https://api.openai.com/v1", api_key_env="OPENAI_API_KEY",
                 max_tokens=4000, temperature=None, check_model=False, headers=None, **kw):
        super().__init__(model, **kw)
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key_env, self.max_tokens, self.temperature = api_key_env, max_tokens, temperature
        self.check_model = check_model      # routers may silently swap models; fail if the reply names another
        self.headers = headers or {}

    def complete(self, prompt):
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        h = {"Content-Type": "application/json", **self.headers}
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if not key:
                raise LLMError(f"env {self.api_key_env} is not set")
            h["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            raise LLMError(f"HTTP {e.code}: {e.read()[:200]!r}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise LLMError(repr(e)) from None
        if self.check_model and d.get("model") != self.model:
            raise LLMError(f"routed to {d.get('model')} instead of {self.model}")
        return d["choices"][0]["message"].get("content") or ""
