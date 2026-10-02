"""Engines: two ways to fill the Judgments contract.

JevEngine     asks a real jev endpoint. Works against the hosted API or a
              self-hosted deployment: TYPESAFE_BASE_URL points at the server
              (with or without the /v1/systemone path) and TYPESAFE_API_KEY is
              the key. No SDK required.
RecordedEngine replays canned answers so the demo runs with no key and no
              network. Its answers are hand-written stand-ins, not model output.
"""

import inspect
import json
import os
import time
import urllib.error
import urllib.request

from .config import settings
from .policy import Judgments
from .questions import QUESTIONS_DICT


def _to_judgments(answers: dict, source: str, reason: str) -> Judgments:
    risk = answers["risk"]
    return Judgments(
        risk=risk.get("choice", "unknown"),
        confidence=float(risk.get("confidence", 0.0)),
        data_loss=float(answers["data_loss"].get("noul", 0.0)),
        blast_radius=float(answers["blast_radius"].get("score", 0.0)),
        reason=reason,
        source=source,
    )


class JevError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def endpoint_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/systemone"):
        return base
    if base.endswith("/v1"):
        return f"{base}/systemone"
    return f"{base}/v1/systemone"


def chat_url(base_url: str) -> str:
    """Gateways such as LiteLLM expose jev on the OpenAI-shaped chat route."""

    base = base_url.rstrip("/")
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if base.endswith(suffix):
            return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")[:300]
        hint = ""
        if error.code in (401, 403):
            hint = " (check the key)"
        elif error.code == 404:
            hint = f" (check the path, posting to {url})"
        raise JevError(f"HTTP {error.code}{hint}: {body}", status=error.code) from error
    except urllib.error.URLError as error:
        raise JevError(f"cannot reach {url}: {error.reason}") from error


def _as_text(state) -> str:
    return state if isinstance(state, str) else json.dumps(state)


class HttpTransport:
    """stdlib POST to {state, model, questions}. No dependencies."""

    name = "http"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float):
        self.url = endpoint_url(base_url)
        self._model = model
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def system_one(self, state: dict, questions: dict) -> dict:
        body = _post_json(
            self.url,
            self._headers,
            {"model": self._model, "state": state, "questions": questions},
            self._timeout,
        )
        return body


class ChatTransport:
    """Gateway route: state as a user message, questions in response_format."""

    name = "chat"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float):
        self.url = chat_url(base_url)
        self._model = model
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def system_one(self, state: dict, questions: dict) -> dict:
        body = _post_json(
            self.url,
            self._headers,
            {
                "model": self._model,
                "messages": [{"role": "user", "content": _as_text(state)}],
                "response_format": {"type": "questions", "questions": questions},
            },
            self._timeout,
        )
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        return {
            "model": body.get("model"),
            "answers": json.loads(content) if isinstance(content, str) else content,
            "usage": {
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            },
        }


class AutoTransport:
    """Try the SystemOne route first, switch to the gateway route on 404/405."""

    def __init__(self, primary, fallback):
        self._primary = primary
        self._fallback = fallback
        self._current = primary

    @property
    def name(self) -> str:
        return self._current.name

    @property
    def url(self) -> str:
        return getattr(self._current, "url", "")

    def system_one(self, state: dict, questions: dict) -> dict:
        try:
            return self._current.system_one(state, questions)
        except JevError as error:
            if self._current is self._primary and error.status in (404, 405) and self._fallback:
                self._current = self._fallback
                return self._current.system_one(state, questions)
            raise


class SdkTransport:
    """Same envelope, via typesafe-sdk, when it is installed and supports base_url."""

    name = "sdk"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float):
        from typesafe_sdk import TypeSafeClient

        if api_key:
            os.environ["TYPESAFE_API_KEY"] = api_key

        kwargs = {"model": model, "timeout": timeout}
        accepted = inspect.signature(TypeSafeClient).parameters
        takes_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in accepted.values()
        )
        if base_url and ("base_url" in accepted or takes_kwargs):
            kwargs["base_url"] = base_url

        self._client = TypeSafeClient(**kwargs)

    def system_one(self, state: dict, questions: dict) -> dict:
        response = self._client.system_one(state=state, questions=questions)
        return {
            "model": response.model,
            "answers": {name: answer.model_dump() for name, answer in response.answers.items()},
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }


def build_transport(prefer: str, base_url: str, api_key: str, model: str, timeout: float):
    if prefer in ("auto", "sdk"):
        try:
            import typesafe_sdk  # noqa: F401
        except ImportError:
            if prefer == "sdk":
                raise SystemExit("typesafe-sdk is not installed; run: pip install -r requirements.txt")
        else:
            try:
                return SdkTransport(base_url, api_key, model, timeout)
            except (TypeError, JevError) as error:
                if prefer == "sdk":
                    raise SystemExit(f"could not use the SDK transport: {error}")
                print(f"! SDK transport unavailable ({error}); using the stdlib HTTP transport")
    if prefer == "chat":
        return ChatTransport(base_url, api_key, model, timeout)
    if prefer == "http":
        return HttpTransport(base_url, api_key, model, timeout)
    return AutoTransport(
        primary=HttpTransport(base_url, api_key, model, timeout),
        fallback=ChatTransport(base_url, api_key, model, timeout),
    )


class RecordedEngine:
    def __init__(self, path: str):
        with open(path, encoding="utf-8") as handle:
            self._answers = json.load(handle)

    @property
    def name(self) -> str:
        return "recorded"

    def judge(self, state: dict) -> Judgments:
        record = self._answers[state["id"]]
        return _to_judgments(record["answers"], self.name, record["reason"])


class JevEngine:
    def __init__(self, transport, decision_log: str):
        self._transport = transport
        self._decision_log = decision_log

    @property
    def name(self) -> str:
        return f"jev/{self._transport.name}"

    def judge(self, state: dict) -> Judgments:
        started = time.perf_counter()
        response = self._transport.system_one(state, QUESTIONS_DICT)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        answers = response["answers"]
        usage = response.get("usage", {})
        self._log(
            {
                "id": state["id"],
                "model": response.get("model"),
                "transport": self._transport.name,
                "latency_ms": latency_ms,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "answers": answers,
            }
        )

        risk = answers["risk"]
        probabilities = risk.get("probabilities") or {}
        reason = f"top={max(probabilities, key=probabilities.get)}" if probabilities else "no probabilities"
        return _to_judgments(answers, self.name, reason)

    def _log(self, record: dict) -> None:
        line = json.dumps(record)
        if self._decision_log == "-":
            print(line, flush=True)
            return
        with open(self._decision_log, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def get_engine(recorded_path: str, prefer: str, transport_prefer: str = "auto"):
    if prefer == "recorded":
        return RecordedEngine(recorded_path)

    base_url, api_key, model, timeout = settings()
    if not api_key:
        raise SystemExit("TYPESAFE_API_KEY is not set; use --engine recorded to run offline")

    transport = build_transport(transport_prefer, base_url, api_key, model, timeout)
    return JevEngine(
        transport=transport,
        decision_log=os.environ.get("JEV_DECISION_LOG", "decisions.jsonl"),
    )


def ping(prefer: str = "auto") -> None:
    """One cheap Noul to prove the endpoint, the key and the model name work."""

    base_url, api_key, model, timeout = settings()
    transport = build_transport(prefer, base_url, api_key, model, timeout)
    started = time.perf_counter()
    response = transport.system_one(
        "k3s cluster named prod, 2 nodes, all pods Ready",
        {"healthy": {"type": "noul", "instructions": "Does this cluster look healthy?"}},
    )
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    answer = response["answers"]["healthy"]
    print(f"ok  {getattr(transport, 'url', base_url)}")
    print(f"    via {transport.name} model={response.get('model')} noul={answer['noul']} latency={elapsed}ms")