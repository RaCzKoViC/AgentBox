const form = document.getElementById('login');
const err = document.getElementById('err');
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  err.hidden = true;
  const token = document.getElementById('token').value.trim();
  try {
    const r = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token}),
    });
    if (!r.ok) throw new Error('Invalid token');
    sessionStorage.setItem('ab_token', token);
    location.href = '/';
  } catch (ex) {
    err.textContent = ex.message || 'Login failed';
    err.hidden = false;
  }
});
