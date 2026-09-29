import os
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

_configured_name = None

def setup_tracing(service_name: str):
    global _configured_name
    if _configured_name is not None:
        if _configured_name != service_name:
            import logging
            logging.getLogger(__name__).warning(
                f"Tracing already configured as '{_configured_name}', ignoring request for '{service_name}'"
            )
        return trace.get_tracer(service_name)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger.tracing.svc.cluster.local:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    _configured_name = service_name
    return trace.get_tracer(service_name)

tracer = None