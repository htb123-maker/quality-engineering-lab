"""Background job semantics: queue depth, worker execution, and failure records."""

# mypy: disable-error-code="untyped-decorator,no-untyped-call"

from __future__ import annotations

import allure
import pytest
from qa_core.auth import AuthClient
from qa_core.cache import CatalogCacheProbe
from qa_core.config.settings import Settings
from qa_core.data_factories import NamespaceFactory, NamespaceIdentity
from qa_core.jobs import JobClient, job_path, wait_for_final_record


@allure.epic("Quality Engineering Lab")
@allure.feature("Background jobs")
@allure.story("Delayed work")
@pytest.mark.integration
def test_delayed_refresh_job_is_queued_first_and_completes_on_the_worker(
    settings: Settings,
    db_namespace: NamespaceIdentity,
) -> None:
    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=db_namespace.slug,
    )
    probe.purge()
    try:
        with AuthClient.from_settings(settings) as auth:
            auth.login(db_namespace.owner_email, settings.auth_test_password)
            jobs = JobClient.from_auth(auth)

            before = jobs.queue_stats()
            accepted = jobs.refresh_catalog_cache(db_namespace.slug, delay_seconds=1.0)
            queued = jobs.get(accepted.job_id)
            waiting = jobs.queue_stats()
            cached_while_queued = probe.entry()

            finished = jobs.wait(accepted.job_id, timeout=20.0)
            after = jobs.queue_stats()

        entry = probe.entry()
        allure.attach(
            "\n".join(
                [
                    f"status right after 202: {queued.status}",
                    f"queue stats while delayed: {waiting}",
                    f"final status: {finished.status}",
                    f"result: {finished.result}",
                    f"queue stats after: {after}",
                    f"cache TTL written by the worker: "
                    f"{entry.ttl_seconds if entry else None}",
                ]
            ),
            name="delayed job evidence",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert accepted.status == "queued"
        assert queued.status == "queued"
        assert queued.started_at is None
        assert waiting.delayed >= 1, "a delayed job must not be popped immediately"
        assert waiting.processed == before.processed
        assert cached_while_queued is None, "queued work must not warm the cache"

        assert finished.status == "succeeded"
        assert finished.started_at is not None
        assert finished.finished_at is not None
        assert finished.result is not None
        assert finished.result["workspace_slug"] == db_namespace.slug
        assert finished.result["items"] == 2
        assert finished.result["ttl_seconds"] == settings.catalog_cache_ttl_seconds

        assert after.processed == before.processed + 1
        assert after.failed == before.failed
        assert after.delayed == 0
        assert after.queued == 0
        assert after.worker_enabled == settings.job_worker_enabled

        assert entry is not None
        assert entry.payload["count"] == 2
        assert 0 < entry.ttl_seconds <= settings.catalog_cache_ttl_seconds
    finally:
        probe.purge()


@allure.epic("Quality Engineering Lab")
@allure.feature("Background jobs")
@allure.story("Failure path")
@pytest.mark.integration
def test_job_for_a_deleted_workspace_fails_with_a_readable_error(
    settings: Settings,
    namespace_factory: NamespaceFactory,
) -> None:
    identity = namespace_factory.create(tag="jobfail", items=1)
    probe = CatalogCacheProbe(
        redis_url=str(settings.redis_url),
        workspace_slug=identity.slug,
    )
    probe.purge()
    try:
        with AuthClient.from_settings(settings) as owner:
            owner.login(identity.owner_email, settings.auth_test_password)
            accepted = JobClient.from_auth(owner).refresh_catalog_cache(
                identity.slug,
                delay_seconds=1.0,
            )

        # The seeded atlas owner survives the purge, so the queue counters and
        # the workspace-scoped read can still be checked afterwards.
        with AuthClient.from_settings(settings) as auditor:
            auditor.login(settings.auth_test_username, settings.auth_test_password)
            jobs = JobClient.from_auth(auditor)
            before = jobs.queue_stats()

            namespace_factory.purge(identity)
            record = wait_for_final_record(
                str(settings.redis_url),
                accepted.job_id,
                timeout=20.0,
            )
            after = jobs.queue_stats()
            foreign_read = auditor.get(job_path(accepted.job_id))

        assert record is not None
        allure.attach(
            "\n".join(
                [
                    f"status: {record.get('status')}",
                    f"error: {record.get('error')}",
                    f"failed counter: {before.failed} -> {after.failed}",
                    f"API read after the purge: {foreign_read.status_code}",
                ]
            ),
            name="failed job evidence",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert accepted.status == "queued"
        assert record["status"] == "failed"
        assert record["error"] is not None
        assert "workspace_not_found" in record["error"]
        assert record["result"] is None
        assert record["finished_at"] is not None
        assert after.failed == before.failed + 1
        assert after.processed == before.processed
        assert foreign_read.status_code == 403
        assert foreign_read.json()["error"] == "permission_denied"
        assert probe.entry() is None
    finally:
        namespace_factory.purge(identity)
        probe.purge()
