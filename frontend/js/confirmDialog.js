import { t } from './i18n.js';

let activeDialog = null;

/** App confirmation dialog. Resolves false when dismissed or navigating away. */
export function confirmDialog({ title, message, confirmLabel }) {
  if (activeDialog) return Promise.resolve(false);

  const previousFocus = document.activeElement;
  const dialog = document.createElement('dialog');
  dialog.className = 'confirm-dialog';
  dialog.setAttribute('aria-labelledby', 'confirm-dialog-title');
  dialog.setAttribute('aria-describedby', 'confirm-dialog-message');
  dialog.innerHTML = `
    <h2 id="confirm-dialog-title" class="confirm-dialog-title"></h2>
    <p id="confirm-dialog-message" class="confirm-dialog-message"></p>
    <form method="dialog" class="confirm-dialog-actions">
      <button type="submit" value="cancel" class="confirm-dialog-cancel" autofocus></button>
      <button type="submit" value="confirm" class="confirm-dialog-submit"></button>
    </form>`;
  dialog.querySelector('h2').textContent = title;
  dialog.querySelector('p').textContent = message;
  dialog.querySelector('[value="cancel"]').textContent = t('common.cancel');
  dialog.querySelector('[value="confirm"]').textContent = confirmLabel;
  activeDialog = dialog;
  document.body.append(dialog);

  return new Promise(resolve => {
    const dismiss = () => dialog.close('cancel');
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const cancel = dialog.querySelector('[value="cancel"]');
      const confirm = dialog.querySelector('[value="confirm"]');
      if (event.shiftKey && document.activeElement === cancel) {
        event.preventDefault();
        confirm.focus();
      } else if (!event.shiftKey && document.activeElement === confirm) {
        event.preventDefault();
        cancel.focus();
      }
    });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right
        || event.clientY < bounds.top || event.clientY > bounds.bottom) dismiss();
    });
    window.addEventListener('hashchange', dismiss);
    dialog.addEventListener('close', () => {
      window.removeEventListener('hashchange', dismiss);
      const confirmed = dialog.returnValue === 'confirm';
      dialog.remove();
      activeDialog = null;
      if (previousFocus?.isConnected) previousFocus.focus();
      resolve(confirmed);
    }, { once: true });
    dialog.showModal();
  });
}
