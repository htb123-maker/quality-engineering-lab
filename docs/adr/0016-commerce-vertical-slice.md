# ADR-0016: Commerce Vertical Slice for Business Complexity Evidence

- Status: Accepted - initial slice implemented
- Date: 2026-11-22
- Owner: Quality Engineering Lab
- Schema migration: Approved and implemented in `003_commerce.sql`

## Context

The current SUT has a real catalog write path:

```text
workspace
+ auth / role
+ catalog item
+ PostgreSQL
+ Redis cache invalidation
+ Android UI
+ API verification
```

This is stronger than a standalone fixture because the mobile action crosses the
real API and the final state is read back from the real SUT. It proves that the
harness can carry a newly added feature through authentication, a write
endpoint, a database, a cache, and a mobile UI.

It does not prove the business correctness of a commerce product. The current
schema contains only `workspaces`, `users`, and `catalog_items`. There are no
orders, inventory reservations, payments, fulfillment records, refunds, or
compensation rules. A fixture cannot invent those invariants without becoming a
second, conflicting implementation of the product.

A fixture can validate:

- a UI control and page transition;
- a client-to-API contract;
- a permission boundary;
- a loading, timeout, and recovery state;
- that a test action reaches the intended real endpoint.

A fixture cannot independently prove:

- the order state machine;
- stock reservation and release;
- duplicate or concurrent payment handling;
- amount calculation;
- tenant and object-level authorization;
- database side effects and rollback;
- eventual consistency between PostgreSQL and Redis;
- compensating behavior after a partial failure.

No finite test suite proves every possible product behavior. The practical goal
is a representative vertical slice that exercises the highest-risk business
invariants, with evidence tied to one real traceable transaction.

## Decision

Add one narrow commerce vertical slice to the existing SUT rather than building
a larger fake application or a second fixture-owned business store.

The slice will use one catalog item as the product source and one real mobile
client action chain. PostgreSQL is the source of truth for orders, inventory,
reservations, payments, and fulfillment. Redis may hold a read model or cache,
but it cannot be the authoritative record.

### Domain boundary

The initial slice contains:

```text
real mobile client
-> login and role check
-> select catalog item
-> create order
-> reserve inventory
-> initiate payment
-> fulfill order
-> read PostgreSQL final state
-> verify Redis read model or cache
-> cancel or refund as a compensating path
```

The initial state machine is:

```text
CREATED
-> AWAITING_PAYMENT
-> PAID
-> FULFILLED

CREATED or AWAITING_PAYMENT -> CANCELLED
PAID or FULFILLED           -> REFUNDED
```

Payment attempts are separate from order state:

```text
PENDING -> SUCCEEDED | FAILED
SUCCEEDED -> REFUNDED
```

Inventory reservation is an explicit transaction:

```text
available -= quantity
reserved  += quantity

on success: reserved -= quantity
on cancel:   reserved  -= quantity
             available += quantity
on refund:   compensation follows the fulfillment policy
```

### Data and API shape

The implementation will add the smallest set of tables needed to model the
slice:

- `orders`
- `order_lines`
- `inventory`
- `inventory_reservations`
- `payments`
- `order_events`

The public API will be workspace-scoped and role-checked, for example:

```text
POST /api/v1/workspaces/{slug}/commerce/orders
POST /api/v1/workspaces/{slug}/commerce/orders/{order_id}/payments
POST /api/v1/workspaces/{slug}/commerce/orders/{order_id}/cancel
POST /api/v1/workspaces/{slug}/commerce/orders/{order_id}/refund
GET  /api/v1/workspaces/{slug}/commerce/orders/{order_id}
```

Every write will require an idempotency key scoped to the workspace and
operation. Database constraints and transactions, not UI state, enforce the
final invariants.

### Test harness responsibilities

The mobile test harness has three separate ports:

| Port | Responsibility | Allowed to decide business truth? |
| --- | --- | --- |
| Setup | Create namespace, item, balance, or an initial database state | No |
| Mobile | Drive the real client and record UI evidence | No |
| Verification | Read API, PostgreSQL, Redis, and request IDs | No |

The fixture may prepare a state. It may not return a fabricated "paid" status
that replaces the payment endpoint, database transaction, or final API state.

## Acceptance Scenarios

The slice is accepted only when these scenarios have real evidence:

1. Happy path: create, pay, fulfill, and verify the final order and inventory.
2. Insufficient stock: no permanent inventory deduction is left behind.
3. Duplicate payment: one idempotency key produces one successful settlement.
4. Concurrent payment: only one payment wins and the losing request is
   explained without double charging.
5. Timeout and retry: the client retries safely, and the final state is neither
   lost nor duplicated.
6. Cancel and release: the inventory reservation is released exactly once.
7. Refund: order, payment, inventory, and event state remain consistent.
8. RBAC and tenant boundary: another workspace or viewer cannot mutate the
   transaction.
9. Weak network: the real mobile path observes delay or a dropped packet and
   recovers to the correct server state.
10. Reconciliation: a read model or cache is compared with PostgreSQL after
    the write, and a stale read does not become a false pass.

## Evidence Contract

Every executed commerce case must attach:

- test ID and run ID;
- order ID and payment ID;
- API request ID;
- idempotency key;
- initial and final inventory quantities;
- PostgreSQL order, payment, reservation, and event rows;
- API read-back status;
- mobile UI final status;
- the failure or recovery timestamp where applicable.

The evidence must distinguish `PASS`, `PARTIAL`, `FAILED`, `NOT RUN`, `BLOCKED`,
and `DEFERRED`. A successful fixture setup is not a successful business result.

## Implementation Order

1. Add the schema migration and seed data after explicit human approval.
2. Implement the commerce endpoints and database invariants.
3. Add API and database tests for state transitions, idempotency, concurrency,
   rollback, and tenant isolation.
4. Add a real mobile commerce client and Android/iOS adapters.
5. Add the cross-layer acceptance journey and weak-network recovery case.
6. Add the commerce evidence bundle to CI and the weekly report.

## Non-Goals

This slice is not intended to be a full e-commerce platform. It will not add:

- a real payment provider integration;
- tax, multi-currency, promotions, or a shopping recommendation engine;
- a microservice split;
- every possible catalog, shipment, or customer-service workflow.

The purpose is to prove business invariants across real boundaries with a
scope that can be reviewed and maintained.

## Implementation Evidence

The initial Android slice was implemented and executed on 2026-11-22:

- PostgreSQL schema: inventory, orders, order lines, reservations, payments,
  and append-only order events.
- Real inventory row locking prevents overselling.
- Order creation reserves stock in the same transaction as order creation.
- Payment uses a database uniqueness constraint plus workspace-scoped
  idempotency records.
- Concurrent payments serialize on the order row; only one settlement wins.
- Fulfillment consumes the reservation and decrements on-hand stock.
- Cancellation releases an unpaid reservation.
- Refund releases a paid reservation or restores fulfilled stock.
- Redis stores a derived order read model, never the authoritative decision.
- Physical Android UI completed create, pay, and fulfill against the real SUT.
- Toxiproxy delayed a payment response; retry with the same key produced one
  settlement.

Local evidence:

```text
Unit tests:                    399 passed
Commerce focused tests:         16 passed
Integration tests:              46 passed
Full API tests:                254 passed
Physical Android commerce E2E:    1 passed
GitHub Actions run 45190276965: required jobs passed
```

The weekly report records environment, paths, and remaining `NOT RUN` items in
`reports/weekly/WEEK-33.md`.

## Consequences

- Existing Week 32 catalog evidence remains valid for its stated scope.
- The project does not claim that catalog coverage proves commerce complexity.
- The initial commerce vertical slice is now implemented and locally verified.
- CI is verified; iOS commerce remains pending.
- A full e-commerce platform is still outside the accepted scope.
