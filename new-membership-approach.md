

# NEW MEMBERSHIP APPROACH

I am now trying to set up the new membership experience since we have moved away from super cycle. i will lay out the requirements, and then I will show you an approach another ai agent came up with that uses the Shopify subscription app. An alternative approach I was looking into was using the third party Shopify app appstle.


## Requirements
- A membership renews yearly, it costs $160. Customers can pause or cancel their renewals, and they will be notified over email when the subscription is about to renew
- memberships can be purchased online or in-store through Shopify POS
- in order to purchase a membership, a customer will have to read and accept the terms to a membership agreement. This only needs to be acknowledged with a checkbox or some other approach, but no actual signature. 
- the membership allows for a 10% discount on all purchases through the online store and POS
- at the moment, the customer's name and birthday needs to be captured for the membership, but this may extend to other fields
- my client can send an email blast out to all members 
- when a membership is created, we will create an associated membership account in the library service libib (called "patrons") using their rest api. the patron account will be created using the same data from the customer's checkout. 
- the libib api should return a barcode after the patron account is created, which we will add to the customers account in Shopify as a metafielcd 
- all rentals and emails about rentals will be handled through libib. 


## Shopify Subscription Approach
**Phase 1: Membership product setup**

1. Create a product called "Membership" (no variants needed unless you want tiers)

2. Install the Shopify Subscriptions app

3. Create a selling plan: yearly billing interval, $160/charge, auto-renew on

4. Attach the selling plan to the Membership product

5. Set the product to subscription-only (or allow one-time too, if you ever want non-renewing) -- decide this now since it affects checkout wording

6. Add a subscription cancellation policy in admin (required for POS eligibility)

**Phase 2: POS setup** 7. Confirm Shopify Payments is active (required for POS subscriptions) 8. Confirm POS app is v10.13+ on all devices 9. Add the Shopify Subscriptions tile to the POS smart grid 10. Write a short staff script/checklist: read the contract terms aloud (or hand over a printed copy), confirm verbal agreement, ask for birthday, type both into the POS order note field before completing sale 11. Post that checklist somewhere staff will actually see it at the register

**Phase 3: Theme edit (checkbox + birthday) -- online only** 12. Locate the product page template (or a snippet) for the Membership product specifically 13. Add: a required checkbox (with your contract text/link) and a date input for birthday, both as line-item properties, gated so "Add to cart" is disabled until the checkbox is checked 14. Test that both values show up correctly on the resulting order (Admin → Order → Additional details / line item properties) 15. Decide fallback behavior if JS fails (e.g., don't silently allow purchase -- fail closed)

**Phase 4: Member discount (10% off)** 16. In Shopify Flow, build: Trigger "Order created" → Condition: order contains the Membership product → Action: add tag "Member" to customer 17. Create a customer segment: customers tagged "Member" 18. Create an automatic discount (10% off, any product) restricted to that segment 19. Test with a dummy account: buy membership → confirm tag applied → confirm discount appears on next order

**Phase 5: Renewal reminder email** 20. In Shopify Subscriptions admin, customize the "upcoming payment/renewal" email template with your branding and a heads-up window (confirm how many days before renewal it sends, and whether that's adjustable) 21. Send yourself a test to check timing and content

**Phase 6: Email blasts to members** 22. Install/set up Shopify Email (if not already) 23. Build a segment (same "Member" tag from step 17, or a synced one) as your campaign audience 24. Set up a first test campaign to confirm segment targeting works

**Phase 7: Flow → API trigger structure** 25. Build a second Flow: Trigger "Order created" → Condition: contains Membership product → Action: "Send HTTP request" 26. Structure the payload now (customer name, email, birthday if pulled from line-item property, order ID, purchase date) even without a live endpoint -- point it at a placeholder/test URL (e.g., webhook.site) so you can verify the payload shape before you have a real destination 27. Swap in the real endpoint later without rebuilding the Flow

**Phase 8: End-to-end test** 28. Run one full test purchase online (checkbox + birthday + payment) and one at POS (manual note process), confirm: tag applied, discount active, renewal email scheduled, Flow fired with correct payload, order shows all captured info
