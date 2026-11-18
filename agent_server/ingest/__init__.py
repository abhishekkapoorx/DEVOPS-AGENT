"""Alert ingestion boundary."""

from .service import IngestResult, ingest_alerts

__all__ = ["IngestResult", "ingest_alerts"]
