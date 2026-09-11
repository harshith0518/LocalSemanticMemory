"""Thin worker runner: all policy, evidence, accounting and SQL stay in Service."""

from threading import Event

from jarvis.errors import ApplicationError, ErrorCode
from jarvis.extraction import parse_proposal


def process_one(service, context, *, namespace=None):
    # A Private invocation must not inspect a queue, prepare a prompt, or reserve a call.
    service._provider_gate(context)
    packet = service.lease_next(context, namespace=namespace)
    if packet is None:
        return None
    try:
        for attempt in range(2):
            body, reservation = service.extractor.prepare(packet, repair=bool(attempt))
            call_id = service.reserve_call(context, packet, reservation)
            try:
                completion = service.extractor.complete(body)
            except ApplicationError as error:
                service.finish_call(context, call_id, error=error.code)
                raise
            except Exception:
                service.finish_call(context, call_id, error=ErrorCode.PROVIDER_FAILED)
                raise ApplicationError(ErrorCode.PROVIDER_FAILED) from None
            service.finish_call(context, call_id, completion)
            if completion.input_tokens + completion.output_tokens > reservation:
                raise ApplicationError(ErrorCode.BUDGET_EXHAUSTED)
            try:
                proposal = parse_proposal(completion.content)
                return service.commit_extraction(context, packet, proposal)
            except ApplicationError as error:
                service.finish_call(context, call_id, error=error.code)
                if attempt == 0 and error.code in {
                    ErrorCode.INVALID_INPUT,
                    ErrorCode.INVALID_PASSAGE,
                    ErrorCode.INVALID_TRANSITION,
                }:
                    continue
                raise
    except ApplicationError as error:
        service.fail_processing(context, packet, error.code)
        return {"status": "failed", "reason": error.code.value}
    except Exception:
        service.fail_processing(context, packet, ErrorCode.OPERATION_FAILED)
        return {"status": "failed", "reason": ErrorCode.OPERATION_FAILED.value}


def run_worker(service, stop: Event):
    context = service.identity.context("normal")
    while not stop.is_set():
        try:
            outcome = process_one(service, context)
        except Exception:
            outcome = None  # No input, exception bodies, request traces or persistent logs.
        if outcome is None:
            stop.wait(1)
