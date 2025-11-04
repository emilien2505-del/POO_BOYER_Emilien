document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.toast').forEach(t => setTimeout(()=> t.remove(), 3500));
});
