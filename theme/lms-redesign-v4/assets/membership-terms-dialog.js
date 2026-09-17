/**
 * Wires the membership terms link to open the terms dialog instead of
 * navigating away, keeping the customer's in-progress checkbox/birthday
 * entry on the product page intact. If this script fails to load, the
 * link is a real anchor (target="_blank") to the real terms page, so
 * nothing breaks — it just opens a new tab instead of a dialog.
 */
const trigger = document.querySelector('.membership-terms-trigger');
const dialog = document.getElementById('membership-terms-dialog');

if (trigger && dialog && typeof dialog.showDialog === 'function') {
  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    dialog.showDialog();
  });
}
