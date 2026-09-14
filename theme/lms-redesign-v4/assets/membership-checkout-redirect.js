import { StandardEvents } from '@shopify/events';

/**
 * Skips the cart entirely for the membership product: as soon as the
 * theme's own "item added to cart" event fires (the same event
 * cart-drawer.js and cart-icon.js listen for), send the browser straight
 * to checkout instead of showing the cart drawer/page. Required
 * line-item properties (terms checkbox, birthday) already block this
 * event from firing until they're filled in, since dynamic checkout is
 * hidden on this template and the standard Add to Cart form enforces
 * native HTML5 validation.
 */
document.addEventListener(StandardEvents.cartLinesUpdate, () => {
  window.location.href = '/checkout';
});
