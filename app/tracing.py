"""OpenTelemetry tracing setup exporting to local Jaeger (D5)."""

import os
import logging

log = logging.getLogger("tracing")

OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").lower() in ("1", "true", "yes")
JAEGER_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is not None:
        return _tracer

    if not OTEL_ENABLED:
        from opentelemetry.trace import NoOpTracer
        _tracer = NoOpTracer()
        return _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({"service.name": "motor-claim-triage"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=JAEGER_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("motor-claim-triage")
        log.info(f"OpenTelemetry tracing enabled -> {JAEGER_ENDPOINT}")
    except Exception as e:
        log.warning(f"Could not initialize OpenTelemetry exporter ({e}), using NoOpTracer.")
        from opentelemetry.trace import NoOpTracer
        _tracer = NoOpTracer()

    return _tracer
