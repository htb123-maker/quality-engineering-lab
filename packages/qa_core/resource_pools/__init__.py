"""Lease-based resource pools that keep parallel test workers isolated."""

from qa_core.resource_pools.namespaces import (
    NamespaceLease,
    NamespacePool,
    NamespaceProvider,
)

__all__ = [
    "NamespaceLease",
    "NamespacePool",
    "NamespaceProvider",
]
