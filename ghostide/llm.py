import json
import urllib.request


class LLMError(Exception):
    pass


class OpenAICompatible:
    """Any OpenAI-compatible chat API (OpenAI, OpenRouter, Ollama, vLLM...)."""

    def __init__(self, base_url, api_key, model, timeout=180):
        self.base_url, self.api_key, self.model, self.timeout = base_url, api_key, model, timeout

    def complete(self, system, user):
        if not self.api_key:
            raise LLMError("LLM_API_KEY is not configured")
        body = json.dumps({"model": self.model, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.base_url + "/chat/completions", body, {
            "Content-Type": "application/json", "Authorization": "Bearer " + self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMError("LLM request failed: %s" % type(e).__name__) from None
