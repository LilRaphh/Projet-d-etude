# =============================================================
#  pipeline/logging_config.py — Logging structuré JSON
#  Compatible Grafana/Loki, ELK (Elasticsearch/Logstash/Kibana),
#  Airflow task logs et tout dashboard qui consomme du JSON.
# =============================================================
import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime, timezone

from pipeline.config import LOG_DIR


class _JsonFormatter(logging.Formatter):
    """Formate chaque log en une ligne JSON — idéal pour Loki/ELK."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":       datetime.now(timezone.utc).isoformat(),
            "level":    record.levelname,
            "logger":   record.name,
            "scraper":  self._extract_scraper(record.name),
            "msg":      record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _extract_scraper(logger_name: str) -> str:
        """pipeline.scrapers.mango → mango   |   pipeline.pipeline → pipeline"""
        parts = logger_name.split(".")
        return parts[-1] if parts else logger_name


def setup(level: str = "INFO", run_id: str | None = None) -> None:
    """
    Configure le logging global du pipeline.

    Args:
        level:   Niveau de log ("DEBUG", "INFO", "WARNING", "ERROR").
        run_id:  Identifiant du run (ex: date ISO ou ID Airflow).
                 Si fourni, les logs sont aussi écrits dans un fichier dédié.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    json_fmt = _JsonFormatter()

    # ── Handler stdout (Airflow le capture nativement) ─────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(json_fmt)
    root.addHandler(stdout_handler)

    # ── Handler fichier rotatif (dashboard local / debug) ──────────
    log_file = os.path.join(
        LOG_DIR,
        f"pipeline_{run_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.jsonl",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(json_fmt)
    root.addHandler(file_handler)

    logging.getLogger(__name__).info(
        "[Logging] Initialisé — level=%s | fichier=%s", level, log_file
    )
