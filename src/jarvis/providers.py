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
MAX_REQUESTS = 1100
MAX_TOTAL_TOKENS = 10_000_000
MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_BYTES = 60_000
MAX_RESPONSE_BYTES = 262_144
KIMI_MODEL = "moonshotai/kimi-k3"
LAGUNA_MODEL = "poolside/laguna-xs-2.1"
REVIEWER_ACK = "I_ACCEPT_NVIDIA_DATA_TERMS"


def unfamiliar_approved():
    return (
        os.environ.get("JARVIS_UNFAMILIAR_INFERENCE_APPROVED") == "true"
        and os.environ.get("JARVIS_UNFAMILIAR_DATA_POLICY_ACK") == REVIEWER_ACK
    )


def configured_limit(name, ceiling):
    try:
        value = int(os.environ.get(name, str(ceiling)))
        if not 1 <= value <= ceiling:
            raise ValueError()
        return value
    except ValueError:
        raise ApplicationError(ErrorCode.INVALID_INPUT) from None


@dataclass(frozen=True)
class Completion:
    content: str = field(repr=False)
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_ms: int


class NvidiaExtractor:
    model = MODEL
    endpoint = ENDPOINT
    provider_name = "nvidia"
    budget_key = BUDGET_KEY
    live = True
    timeout_seconds = 90

    def __init__(
        self,
        *,
        approved: bool = False,
        key: str = "",
        transport=None,
        unfamiliar=False,
        unfamiliar_questions=False,
    ):
        self.enabled = approved
        self._key = key
        self._transport = transport
        self.unfamiliar_mode = unfamiliar
        self.unfamiliar_questions = bool(unfamiliar_questions)
        self.max_requests = configured_limit("JARVIS_MAX_REQUESTS", MAX_REQUESTS)
        self.max_total_tokens = configured_limit("JARVIS_MAX_TOTAL_TOKENS", MAX_TOTAL_TOKENS)

    @classmethod
    def from_env(cls):
        if os.environ.get("JARVIS_INFERENCE_PROVIDER", "nvidia") != "nvidia":
            return FreeChatProvider.from_env(role="extractor")
        unfamiliar = unfamiliar_approved()
        return cls(
            approved=unfamiliar or os.environ.get("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED") == "true",
            key=os.environ.get("NVIDIA_API_KEY" if unfamiliar else "NEMOTRON_30B_API_KEY", ""),
            unfamiliar=unfamiliar,
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
                    timeout=httpx.Timeout(self.timeout_seconds, connect=10),
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST",
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=body,
                ) as response,
            ):
                self.last_http_status = response.status_code
                if response.status_code != 200:
                    if response.status_code == 429 and self.provider_name != "nvidia":
                        raise ApplicationError(ErrorCode.RATE_LIMITED)
                    raise ApplicationError(ErrorCode.PROVIDER_FAILED)
                data = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() - started > self.timeout_seconds:
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
                not self.accepts_model(model)
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

    def accepts_model(self, model):
        return model == self.model


class NvidiaResponder(NvidiaExtractor):
    """Same bounded transport/accounting, explicitly selected response model."""

    model = KIMI_MODEL
    # This always-thinking responder timed out at the extractor's 90-second limit.
    # Keep a bounded wait; token/call ceilings and the release guard are unchanged.
    timeout_seconds = 180

    def __init__(self, *, model=None, **kwargs):
        model = self.model if model is None else model
        if self.live and model not in {KIMI_MODEL, MODEL, LAGUNA_MODEL}:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        super().__init__(**kwargs)
        self.model = model
        self.timeout_seconds = 180 if model == KIMI_MODEL else 90

    @classmethod
    def from_env(cls):
        if os.environ.get("JARVIS_INFERENCE_PROVIDER", "nvidia") != "nvidia":
            return FreeChatProvider.from_env(role="responder")
        model = os.environ.get("JARVIS_RESPONSE_MODEL", KIMI_MODEL)
        unfamiliar = unfamiliar_approved()
        key_name = "KIMI_K3_API_KEY" if model == KIMI_MODEL else "NEMOTRON_30B_API_KEY"
        if model == LAGUNA_MODEL:
            key_name = "POOLSIDE_LAGUNA_XS_2P1"
        return cls(
            model=model,
            approved=unfamiliar or os.environ.get("JARVIS_S07_SYNTHETIC_TRIAL_APPROVED") == "true",
            key=os.environ.get("NVIDIA_API_KEY" if unfamiliar else key_name, ""),
            unfamiliar=unfamiliar,
        )

    def prepare(self, packet, *, repair=False):
        from jarvis.answers import answer_messages

        if not self.enabled:
            raise ApplicationError(ErrorCode.PROVIDER_DISABLED)
        conversation = answer_messages(packet, repair=repair)
        size = len(json.dumps(conversation, ensure_ascii=False).encode("utf-8"))
        if size > MAX_INPUT_BYTES:
            raise ApplicationError(ErrorCode.CONTEXT_LIMIT)
        output_tokens = 8192 if self.model == KIMI_MODEL else MAX_OUTPUT_TOKENS
        settings = (
            {"chat_template_kwargs": {"enable_thinking": False}}
            if self.model != KIMI_MODEL
            else {"seed": 0, "reasoning_effort": "low"}
        )
        return {
            "model": self.model,
            "messages": conversation,
            "max_tokens": output_tokens,
            "temperature": 0,
            **settings,
            "stream": False,
            "response_format": {"type": "json_object"},
        }, size + output_tokens + 512


class FreeChatProvider(NvidiaExtractor):
    """Explicit public-synthetic comparison routes; never unfamiliar/personal fallbacks."""

    timeout_seconds = 45
    routes = {
        "google": (
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "GOOGLE_API_KEY_FREE_TIER",
            ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"),
        ),
        "openrouter": (
            "https://openrouter.ai/api/v1/chat/completions",
            "OPEN_ROUTER_API_KEY",
            ("google/gemma-4-31b-it:free",),
        ),
    }

    def __init__(self, *, provider, role, model=None, **kwargs):
        if provider not in self.routes or role not in {"extractor", "responder"}:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        self.endpoint, _, models = self.routes[provider]
        self.model = model or models[0]
        if self.model not in models or kwargs.get("unfamiliar"):
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        self.provider_name, self.role = provider, role
        super().__init__(**kwargs)

    @classmethod
    def from_env(cls, *, role):
        provider = os.environ.get("JARVIS_INFERENCE_PROVIDER", "")
        if provider not in cls.routes:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        _, key_name, models = cls.routes[provider]
        enabled = (
            os.environ.get("JARVIS_FREE_SYNTHETIC_TRIAL_APPROVED") == "true"
            and os.environ.get("JARVIS_FREE_DATA_POLICY_ACK") == "I_ACCEPT_FREE_SYNTHETIC_DATA_TERMS"
            and not unfamiliar_approved()
        )
        return cls(
            provider=provider,
            role=role,
            model=os.environ.get(f"JARVIS_FREE_{role.upper()}_MODEL") or models[0],
            approved=enabled,
            key=os.environ.get(key_name, ""),
            unfamiliar_questions=(
                enabled and os.environ.get("JARVIS_FREE_SYNTHETIC_QUESTIONS_APPROVED") == "true"
            ),
        )

    def prepare(self, packet, *, repair=False):
        if self.role == "extractor":
            body, reserved = super().prepare(packet, repair=repair)
        else:
            reference = NvidiaResponder(model=MODEL, approved=self.enabled)
            body, reserved = reference.prepare(packet, repair=repair)
            body["model"] = self.model
        body.pop("chat_template_kwargs", None)
        if self.provider_name == "google":
            body["reasoning_effort"] = "low"
        else:
            body["provider"] = {
                "max_price": {"prompt": 0, "completion": 0, "request": 0},
                "allow_fallbacks": False,
                "require_parameters": True,
                "data_collection": "deny",
            }
            body["transforms"] = []
        return body, reserved

    def accepts_model(self, model):
        return model in {self.model, self.model.removesuffix(":free")}
