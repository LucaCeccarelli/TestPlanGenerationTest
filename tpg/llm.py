"""The only module that talks to the network. Sends a JSON schema but never trusts the reply."""
import os
import re
from pathlib import Path
from typing import TypeVar, get_origin

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class TruncatedJSON(LLMError):
    pass


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def clean_json(text: str) -> str:
    """Return the first balanced JSON object or array in text. Braces inside strings are ignored."""
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        raise LLMError("no JSON object or array in reply")
    stack: list[str] = []
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or ch != stack.pop():
                raise LLMError("unbalanced JSON in reply")
            if not stack:
                return text[start : i + 1]
    raise TruncatedJSON("unterminated JSON in reply")


def salvage_json_array(text: str, key: str) -> str | None:
    """Recover the complete elements of a truncated `"key": [...]` array as a JSON object, or None if none closed."""
    m = re.search(r'"%s"\s*:\s*\[' % re.escape(key), text)
    if not m:
        return None
    pos, items = m.end(), []
    while True:
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text) or text[pos] not in "{[":
            break
        try:
            item = clean_json(text[pos:])
        except LLMError:
            break
        items.append(item)
        pos += len(item)
    return '{"%s": [%s]}' % (key, ", ".join(items)) if items else None


class OllamaLLM:
    def __init__(
        self,
        model: str,
        host: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ):
        self.model = model
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        key = api_key if api_key is not None else os.environ.get("OLLAMA_API_KEY")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.timeout = timeout if timeout is not None else float(os.environ.get("OLLAMA_TIMEOUT", 120))
        self._client = None

    def _get_client(self):
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.host, headers=self.headers, timeout=self.timeout)
        return self._client

    def check(self) -> None:
        try:
            names = {m.model for m in self._get_client().list().models}
        except Exception as e:  # connection refused, 401, DNS...
            raise LLMError(f"cannot reach Ollama at {self.host}: {e}") from e
        if self.model not in names and f"{self.model}:latest" not in names:
            raise LLMError(f"model {self.model!r} not available at {self.host}")

    def _chat(self, prompt: str, schema: type[BaseModel]) -> str:
        resp = self._get_client().chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format=schema.model_json_schema(),
            think=False,
            options={"temperature": 0},
        )
        return resp.message.content or ""

    def complete(self, prompt: str, schema: type[T]) -> T:
        try:
            raw = self._chat(prompt, schema)
        except Exception as e:
            raise LLMError(f"LLM call failed: {e}") from e
        try:
            try:
                cleaned = clean_json(raw)
            except TruncatedJSON:
                lists = [n for n, f in schema.model_fields.items() if get_origin(f.annotation) is list]
                cleaned = salvage_json_array(raw, lists[0]) if len(lists) == 1 else None
                if cleaned is None:
                    raise
            return schema.model_validate_json(cleaned)
        except ValidationError as e:
            raise LLMError(f"reply did not match schema: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}") from e
        except ValueError as e:
            raise LLMError(f"reply is not valid JSON: {e}") from e
