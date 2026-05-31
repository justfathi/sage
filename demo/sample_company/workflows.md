# How Acme Works Today (SOPs)

## Quoting workflow
1. Customer submits origin, destination, weight, and service level.
2. OrderHub calculates a base rate from the rate card.
3. Surcharges (fuel, remote-area, hazardous) are applied in a fixed order.
4. Operations may override the quote with a documented reason.

## Booking workflow
1. Customer accepts a quote, which locks the price for 48 hours.
2. A booking reference is generated and pushed to the carrier.
3. Tracking events flow back via carrier webhooks.

## Invoicing workflow
1. On delivery, an invoice draft is generated from the booking.
2. Finance reviews drafts daily and posts them to SAP.
3. Disputes are handled manually over email -- a known pain point.

## Known pain points
- The surcharge engine is undocumented; rules live in code only.
- Dispute handling has no system support and is slow.
- There is no audit trail for quote overrides.
