// Shared placeholder for pages that are still being rebuilt in Web v3. Replace the page's module
// (views/<id>.js) with a real view that follows the contract in routes.js; nothing else needs to change.
import { h } from '../ui.js';
import { t } from '../i18n.js';

export function placeholder(titleKey, extra) {
  return function render(ctx) {
    const line = h('p', { class: 'status-line' });
    const node = h('div', { class: 'page' }, ctx.header({ title: t(titleKey) }), h('p', { class: 'ph-empty' }, t('ph.soon')), extra ? extra(ctx) : null, line);
    return {
      node,
      // shows the status contract in use; a real page renders its own state
      onStatus({ status, error }) {
        line.classList.toggle('off', !!error);
        line.textContent = error ? t('err.speaker') : status ? `${t('spk.label')}: ${status.speaker}` : '';
      },
    };
  };
}
