"""Fixed NVIDIA extractor transport. Disabled until an explicit synthetic-only trial decision."""

import json
import os
from dataclasses import dataclass, field
from time import monotonic

import httpx

from jarvis.errors import ApplicationError, ErrorCode
from jarvis.extraction import ExtractionPacket, messages

MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
BUDGET_KEY = "s07-synthetic-v1"
MAX_REQUESTS = 32
MAX_TOTAL_TOKENS = 500_000
MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_BYTES = 60_000
MAX_RESPONSE_BYTES = 262_144


@dataclass(frozen=True)
class Completion:
    content: str = field(repr=False)
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_ms: int


class NvidiaExtractor:
    model = MODEL
    budget_key = BUDGET_KEY
    live = True

    def __init__(self, *, approved: bool = False, key: str = "", transport=None):
        self.enabled = approved
        self._key = key
        self._transport = transport

    @classmethod
    def from_env(cls):
        return cls(
            approved=os.environ.get("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED") == "true",
            key=os.environ.get("NEMOTRON_30B_API_KEY", ""),
        )

    def prepare(self, packet: ExtractionPacket, *, repair=False) -> tuple[dict, int]:
        if not self.enabled:
            raise ApplicationError(ErrorCode.PROVIDER_DISABLED)
        conversation = messages(packet, repair=repair)
        size = len(json.dumps(conversation, ensure_ascii=False).encode("utf-8"))
        if size > MAX_INPUT_BYTES:
            raise ApplicationError(ErrorCode.CONTEXT_LIMIT)
        return {
            "model": self.model,
            "messages": conversation,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }, size + MAX_OUTPUT_TOKENS + 512

    def complete(self, body: dict) -> Completion:
        if not self.enabled or not self._key:
            raise ApplicationError(ErrorCode.PROVIDER_DISABLED)
        started = monotonic()
        try:
            # No redirects, proxy inheritance, streaming publication, SDK retries or fallbacks.
            with (
                httpx.Client(
                    timeout=httpx.Timeout(90, connect=10),
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST",
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=body,
                ) as response,
            ):
                if response.status_code != 200:
                    raise ApplicationError(ErrorCode.PROVIDER_FAILED)
                data = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() - started > 90:
                        raise ApplicationError(ErrorCode.PROVIDER_FAILED)
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise ApplicationError(ErrorCode.PROVIDER_RESPONSE)
            value = json.loads(data)
            usage = value["usage"]
            input_tokens, output_tokens = usage["prompt_tokens"], usage["completion_tokens"]
            if any(type(n) is not int or n < 0 for n in (input_tokens, output_tokens)):
                raise ValueError()
            model = value["model"]
            choice = value["choices"][0]
            content = choice["message"]["content"]
            if (
                model != self.model
                or not isinstance(content, str)
                or choice["finish_reason"] != "stop"
            ):
                raise ValueError()
            return Completion(
                content, model, input_tokens, output_tokens, int((monotonic() - started) * 1000)
            )
        except ApplicationError:
            raise
        except (KeyError, IndexError, TypeError, ValueError):
            raise ApplicationError(ErrorCode.PROVIDER_RESPONSE) from None
        except Exception:
            raise ApplicationError(ErrorCode.PROVIDER_FAILED) from None
