"""Week 27 monitoring configuration and low-cardinality metric contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import app as sut_app
import pytest
import yaml


def _load_observability_verifier() -> ModuleType:
    path = Path("scripts/verify_observability.py")
    spec = importlib.util.spec_from_file_location("verify_observability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_promql_run_id_is_escaped_as_a_string_literal() -> None:
    verifier = _load_observability_verifier()

    assert verifier._promql_string('run"\\next\nline') == 'run\\"\\\\next\\nline'


def test_finish_observation_ignores_idle_keepalive_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGauge:
        def __init__(self) -> None:
            self.decrements = 0

        def dec(self) -> None:
            self.decrements += 1

    gauge = FakeGauge()
    monkeypatch.setattr(sut_app, "HTTP_REQUESTS_IN_PROGRESS", gauge)
    handler = object.__new__(sut_app.SutRequestHandler)
    handler._request_started_at = None
    handler._request_span_token = None
    handler._request_counted_in_progress = False

    handler._finish_request_observation()

    assert gauge.decrements == 0


def test_dynamic_routes_collapse_to_stable_metric_labels() -> None:
    assert sut_app._metric_route("/api/v1/workspaces/qa-perf-week27/catalog") == (
        "/api/v1/workspaces/{slug}/catalog"
    )
    assert sut_app._metric_route("/api/v1/workspaces/qa-perf-week27/events") == (
        "/api/v1/workspaces/{slug}/events"
    )
    assert sut_app._metric_route("/api/v1/jobs/job-123") == (
        "/api/v1/jobs/{job_id}"
    )
    assert sut_app._metric_route("/not-a-route") == "unmatched"


def test_monitoring_profile_exposes_the_required_sources(
    project_root: Path,
) -> None:
    compose = yaml.safe_load(
        (project_root / "apps" / "compose" / "compose.yaml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    expected = {
        "prometheus",
        "grafana",
        "tempo",
        "postgres-exporter",
        "redis-exporter",
        "cadvisor",
    }

    assert expected.issubset(services)
    for service_name in expected:
        assert "monitoring" in services[service_name]["profiles"]
    assert services["api"]["environment"]["QA_OTEL_ENABLED"] == (
        "${QA_OTEL_ENABLED:-0}"
    )


def test_prometheus_scrapes_api_database_cache_and_containers(
    project_root: Path,
) -> None:
    config = yaml.safe_load(
        (
            project_root
            / "infra"
            / "monitoring"
            / "prometheus"
            / "prometheus.yml"
        ).read_text(encoding="utf-8")
    )
    jobs = {
        job["job_name"]: job["static_configs"][0]["targets"][0]
        for job in config["scrape_configs"]
    }

    assert jobs == {
        "sut-api": "api:8000",
        "postgres": "postgres-exporter:9187",
        "redis": "redis-exporter:9121",
        "cadvisor": "cadvisor:8080",
    }
    assert config["scrape_configs"][0]["metrics_path"] == "/metrics"


def test_grafana_provisions_prometheus_and_tempo_datasources(
    project_root: Path,
) -> None:
    monitoring = project_root / "infra" / "monitoring"
    datasources = yaml.safe_load(
        (
            monitoring
            / "grafana"
            / "provisioning"
            / "datasources"
            / "datasources.yml"
        ).read_text(encoding="utf-8")
    )
    by_uid = {item["uid"]: item for item in datasources["datasources"]}

    assert by_uid["prometheus"]["type"] == "prometheus"
    assert by_uid["prometheus"]["url"] == "http://prometheus:9090"
    assert by_uid["tempo"]["type"] == "tempo"
    assert by_uid["tempo"]["url"] == "http://tempo:3200"


def test_week27_dashboard_contains_sli_resource_and_trace_views(
    project_root: Path,
) -> None:
    dashboard = json.loads(
        (
            project_root
            / "infra"
            / "monitoring"
            / "grafana"
            / "dashboards"
            / "week27-overview.json"
        ).read_text(encoding="utf-8")
    )
    titles = {panel["title"] for panel in dashboard["panels"]}

    assert dashboard["uid"] == "week27-sut-overview"
    assert {
        "SUT request rate",
        "SUT request latency",
        "Server error ratio",
        "API CPU",
        "Container memory",
        "Database and cache sessions",
        "Recent SUT traces",
    }.issubset(titles)
