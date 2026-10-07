// A classic script can report a rejected module import instead of presenting
// an apparently ready interface with no event handlers attached.
(() => {
  const status = document.getElementById('startup-status');
  const controls = document.querySelectorAll('#new-session, [data-browse], #create-form button[type="submit"]');
  for (const control of controls) control.disabled = true;
  const timer = setTimeout(() => {
    status.textContent = 'Flight Sync is taking longer than expected to start. Reload this page; if this persists, update and restart the app.';
  }, 15000);
  import('./app.js?v=9').then(() => {
    clearTimeout(timer);
    status.hidden = true;
    for (const control of controls) control.disabled = false;
  }).catch(error => {
    clearTimeout(timer);
    status.classList.add('error');
    status.textContent = `Flight Sync could not start. Update and restart the app, then refresh with Ctrl+F5. Details: ${error.message || String(error)}`;
    console.error('Flight Sync frontend startup failed:', error);
  });
})();
