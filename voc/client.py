"""A thin OpenAI Chat Completions client over the standard library.

The key is read from OPENAI_API_KEY and sent in a header, never in a URL.
Every call is counted so a run can stop at a fixed budget. Nothing is retried.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-mini"


class BudgetExceeded(RuntimeError):
    pass


def model_name() -> str:
    return os.environ.get("VOC_MODEL", DEFAULT_MODEL)


def _urllib_transport(body: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        raise RuntimeError(f"OpenAI API error {error.code}: {detail}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI API could not be reached: {error.reason}") from None


class OpenAIChatClient:
    """JSON answers through Chat Completions with a strict JSON schema.

    `transport` takes (body, headers, timeout) and returns the decoded response. The
    default one uses urllib. Tests pass a stub, so they never touch the network.
    """

    def __init__(self, max_calls: int, api_key: str | None = None, transport=None,
                 timeout: int = 180):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.max_calls, self.calls, self.timeout = max_calls, 0, timeout
        self.transport = transport or _urllib_transport

    def complete_json(self, model: str, system: str, user: str, schema: dict,
                      schema_name: str) -> dict:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} reached")
        self.calls += 1
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": schema_name, "strict": True, "schema": schema}},
        }
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.api_key}"}
        data = self.transport(body, headers, self.timeout)
        try:
            return json.loads(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError("the model response was not the expected JSON") from None
