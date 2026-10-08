// The interface preference belongs to this browser, not to the shared session.
let mode = 'simple';
export const isExpert = () => mode === 'expert';
export function installInterfaceMode(onChange) {
  const select = document.getElementById('interface-mode');
  try { mode = localStorage.getItem('flight-sync-interface') === 'expert' ? 'expert' : 'simple'; } catch {}
  function apply(value) {
    mode = value === 'expert' ? 'expert' : 'simple';
    select.value = mode;
    document.body.dataset.interface = mode;
    document.getElementById('interface-description').textContent = isExpert()
      ? 'Audio settings, split timelines and detailed review tools.'
      : 'Match, review and export with automatic settings.';
    try { localStorage.setItem('flight-sync-interface', mode); } catch {}
    onChange();
  }
  select.onchange = () => apply(select.value);
  apply(mode);
  return apply;
}
