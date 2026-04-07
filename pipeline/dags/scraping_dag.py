# =============================================================
#  pipeline/dags/scraping_dag.py — DAG Airflow SmartWear
#
#  Structure :
#    scrape_mango ─┐
#    scrape_nike  ─┤
#    scrape_jules ─┼─→ run_pipeline → run_audit → run_check
#    scrape_lcs   ─┤
#    scrape_tac   ─┤
#    scrape_kappa ─┤
#    scrape_lotto ─┘
#
#  Déploiement :
#    Copier ce fichier (ou créer un symlink) dans le dossier
#    $AIRFLOW_HOME/dags/ pour qu'Airflow le détecte.
# =============================================================
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import List

# Airflow importe ce fichier depuis son propre process — on s'assure
# que la racine du projet est dans le path.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

# ── Paramètres du DAG ──────────────────────────────────────────────
DEFAULT_ARGS = {
    "owner":            "smartwear",
    "depends_on_past":  False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

SCRAPER_NAMES = [
    "mango", "nike", "jules", "lecoqsportif", "tacchini", "kappa", "lotto",
]


# ── Callables Python ───────────────────────────────────────────────

def _scrape(scraper_name: str, **context) -> str:
    """Lance un scraper individuel et pousse les résultats via XCom."""
    import pipeline.logging_config as lc
    lc.setup(level="INFO", run_id=context["run_id"])

    from pipeline.scrapers import (
        MangoScraper, NikeScraper, JulesScraper,
        LeCoqSportifScraper, TacchiniScraper, KappaScraper, LottoScraper,
    )
    SCRAPERS = {
        "mango":        MangoScraper,
        "nike":         NikeScraper,
        "jules":        JulesScraper,
        "lecoqsportif": LeCoqSportifScraper,
        "tacchini":     TacchiniScraper,
        "kappa":        KappaScraper,
        "lotto":        LottoScraper,
    }

    cls = SCRAPERS[scraper_name]
    products = cls().run()
    logger.info("[DAG] %s : %d produits", scraper_name, len(products))

    # Sérialise en JSON pour XCom (Airflow ne transporte pas d'objets Python)
    return json.dumps([p.to_dict() for p in products], ensure_ascii=False)


def _run_pipeline(**context) -> int:
    """Agrège tous les XCom scrapers → pipeline normalisation + JSON + MongoDB."""
    import pipeline.logging_config as lc
    lc.setup(level="INFO", run_id=context["run_id"])

    from pipeline.pipeline import SmartWearPipeline
    from pipeline.models import Product
    from dataclasses import fields as dc_fields

    ti = context["ti"]
    all_dicts = []
    for name in SCRAPER_NAMES:
        raw = ti.xcom_pull(task_ids=f"scrape_{name}")
        if raw:
            all_dicts.extend(json.loads(raw))

    logger.info("[DAG] Pipeline — %d produits agrégés", len(all_dicts))

    # Reconstruit des Product à partir des dicts pour repasser par validate_and_clean
    field_names = {f.name for f in dc_fields(Product)}
    products = [Product(**{k: v for k, v in d.items() if k in field_names}) for d in all_dicts]

    SmartWearPipeline().run(products)
    return len(products)


def _run_audit(**context):
    import pipeline.logging_config as lc
    lc.setup(level="INFO", run_id=context["run_id"])
    from pipeline.audit import run_audit
    stats = run_audit()
    logger.info("[DAG] Audit terminé : %s", stats)
    return stats


def _run_check(**context):
    import pipeline.logging_config as lc
    lc.setup(level="INFO", run_id=context["run_id"])
    from pipeline.check import run_check
    anomalies = run_check()
    if anomalies:
        logger.warning("[DAG] %d type(s) d'anomalies détectés", len(anomalies))
    else:
        logger.info("[DAG] Aucune anomalie.")
    return anomalies


# ── Définition du DAG ─────────────────────────────────────────────
with DAG(
    dag_id="smartwear_scraping",
    default_args=DEFAULT_ARGS,
    description="Scraping SmartWear — collecte, normalisation, audit",
    schedule="0 3 * * *",   # chaque nuit à 3h UTC
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["smartwear", "scraping"],
) as dag:

    scrape_tasks = []
    for name in SCRAPER_NAMES:
        t = PythonOperator(
            task_id=f"scrape_{name}",
            python_callable=_scrape,
            op_kwargs={"scraper_name": name},
        )
        scrape_tasks.append(t)

    pipeline_task = PythonOperator(
        task_id="run_pipeline",
        python_callable=_run_pipeline,
    )

    audit_task = PythonOperator(
        task_id="run_audit",
        python_callable=_run_audit,
    )

    check_task = PythonOperator(
        task_id="run_check",
        python_callable=_run_check,
    )

    # Tous les scrapers → pipeline → audit → check
    scrape_tasks >> pipeline_task >> audit_task >> check_task
