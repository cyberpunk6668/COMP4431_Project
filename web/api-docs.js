'use strict';
async function loadSchema() {
  const schema = await (await fetch('/openapi.json')).json();
  const root = document.querySelector('#endpoints'); root.replaceChildren();
  for (const [path, methods] of Object.entries(schema.paths)) {
    for (const [method, operation] of Object.entries(methods)) {
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      const badge = document.createElement('strong'); badge.textContent = method.toUpperCase();
      summary.append(badge, document.createTextNode(path));
      const title = document.createElement('p'); title.textContent = operation.summary || '';
      const info = document.createElement('pre'); info.textContent = JSON.stringify(operation, null, 2);
      details.append(summary, title, info); root.append(details);
    }
  }
}
document.querySelector('#request-form').addEventListener('submit', async event => {
  event.preventDefault();
  const method = document.querySelector('#method').value;
  const path = document.querySelector('#path').value;
  const response = document.querySelector('#response');
  if (!path.startsWith('/api/') || path.includes('://') || path.includes('\\')) { response.textContent = 'Only local /api/ paths are accepted.'; return; }
  const button = document.querySelector('#run'); button.disabled = true;
  try {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (['POST', 'PUT'].includes(method)) options.body = JSON.stringify(JSON.parse(document.querySelector('#body').value));
    const result = await fetch(path, options);
    const data = await result.json();
    response.textContent = `HTTP ${result.status}\n${JSON.stringify(data, null, 2)}`;
  } catch (error) { response.textContent = error.message; }
  finally { button.disabled = false; }
});
loadSchema().catch(error => { document.querySelector('#endpoints').textContent = error.message; });
