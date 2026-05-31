# Tender: Rebuild of the Orders Platform

## Background
Acme Logistics runs a 9-year-old monolith ("OrderHub") that handles quoting,
booking, tracking, and invoicing for freight. It is slow, hard to change, and
the original team has left. We are issuing this tender to rebuild it as a modern
application with a clean API.

## Scope
- Replace the monolith with a new application and a documented REST API.
- Migrate existing customers and historical order data with zero data loss.
- Preserve current business rules around quoting and surcharge calculation.

## Functional requirements
- Customers can request a quote, book a shipment, track it, and receive invoices.
- Operations staff can override quotes and manage exceptions.
- Finance can reconcile invoices against bookings.

## Non-functional requirements
- 99.9% availability; p95 API latency under 300ms.
- Auditable: every quote and override must be traceable.
- Must integrate with the existing SAP finance system.

## Constraints
- Hard regulatory requirement: data residency in-region.
- The new system must run alongside OrderHub during a phased cutover.
