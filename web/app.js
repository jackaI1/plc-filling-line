const $ = (selector) => document.querySelector(selector);
function setText(selector, value) {const node = $(selector); if (node.textContent !== value) node.textContent = value;}
let connected = false, lastOrders = '', lastEvents = '';
async function command(payload) {
  try {
    const response = await fetch('/api/command', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    $('#error').textContent = '';
    return true;
  } catch (error) { $('#error').textContent = error.message; return false; }
}
document.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', () => command({action: button.dataset.command})));
document.querySelectorAll('[data-fault]').forEach(input => input.addEventListener('change', async () => {
  if (!await command({action: 'fault', name: input.dataset.fault, value: input.hasAttribute('data-invert') ? !input.checked : input.checked})) input.checked = !input.checked;
}));
$('#order-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (await command({action: 'open_order', ...Object.fromEntries(new FormData(form))})) form.elements.issue.value = '';
});
function text(tag, value) { const node = document.createElement(tag); node.textContent = value; return node; }
function orders(rows) {
  const body = $('#orders'); body.replaceChildren();
  if (!rows.length) { const row = document.createElement('tr'), cell = text('td', 'No work orders yet. Inject a fault or add an inspection.'); cell.colSpan = 3; row.append(cell); body.append(row); }
  for (const order of rows) {
    const row = document.createElement('tr'), asset = text('td', `#${order.id} · ${order.asset}`);
    asset.append(text('small', `${order.kind} · ${order.opened_at}`));
    const issue = text('td', order.issue), status = document.createElement('td');
    if (order.status === 'closed') { status.append(text('strong', 'Closed'), text('small', order.resolution)); }
    else {
      const form = document.createElement('form'), input = document.createElement('input'), button = text('button', 'Close order');
      input.required = true; input.maxLength = 300; input.placeholder = 'Work performed'; input.setAttribute('aria-label', `Resolution for work order ${order.id}`);
      form.append(input, button); form.addEventListener('submit', event => {event.preventDefault(); command({action: 'close_order', id: order.id, resolution: input.value});}); status.append(form);
    }
    row.append(asset, issue, status); body.append(row);
  }
}
function render(state) {
  const out = state.outputs;
  setText('#status', out.Alarm ? 'Tripped — reset required' : out.BatchDone ? 'Batch complete' : out.Run ? 'Running' : 'Stopped');
  $('#status').className = out.Alarm ? 'alarm' : out.Run ? 'running' : '';
  setText('#fill-diagnostic', out.FillBlocked
    ? 'Fill position did not clear. Check for a jam or a sensor held on, then reset.'
    : 'No fill-position timeout.');
  $('#count').textContent = `${state.count} / 5`;
  $('#fill-time').textContent = `${(state.fill_ms / 1000).toFixed(2)} s`;
  $('#runtime').textContent = `${(state.plant.runtime_ms / 1000).toFixed(1)} s`;
  $('#start').disabled = !connected || out.Run || out.Alarm || out.BatchDone;
  $('#reset').disabled = !connected || out.Run;
  $('#stop').disabled = !connected;
  $('#service').disabled = !connected || out.Run;
  $('#bottle').setAttribute('transform', `translate(${60 + state.plant.position * 800} 0)`);
  $('#liquid').setAttribute('height', state.plant.level * 26);
  $('#liquid').setAttribute('y', 220 - state.plant.level * 26);
  $('#stream').setAttribute('visibility', out.Valve ? 'visible' : 'hidden');
  $('#valve').setAttribute('fill', out.Valve ? '#007d7a' : '#8498a8');
  $('#motor-label').textContent = `CV-01 · ${out.Conveyor ? 'running' : 'stopped'}`;
  $('#tank-label').textContent = state.inputs.TankOK ? 'Level healthy' : 'Low level';
  const io = $('#io'); io.replaceChildren();
  for (const [name, value] of Object.entries({...state.inputs, ...out})) {
    const item = text('span', name), lamp = document.createElement('i');
    lamp.className = `lamp ${value ? 'on' : ''}`; lamp.setAttribute('role', 'img'); lamp.setAttribute('aria-label', value ? 'true' : 'false'); item.prepend(lamp); io.append(item);
  }
  document.querySelectorAll('[data-fault]').forEach(input => {
    const value = ['jammed', 'fill_sensor_stuck'].includes(input.dataset.fault)
      ? state.plant[input.dataset.fault] : state.inputs[input.dataset.fault];
    if (document.activeElement !== input) input.checked = input.hasAttribute('data-invert') ? !value : value;
  });
  const key = JSON.stringify(state.orders); if (key !== lastOrders) {orders(state.orders); lastOrders = key;}
  const events = JSON.stringify(state.events);
  if (events !== lastEvents) {
    $('#events').replaceChildren(...state.events.map(event => {const li = text('li', event.message); li.prepend(text('time', event.at)); return li;}));
    if (!state.events.length) $('#events').append(text('li', 'No events yet. Start the line to run a batch.'));
    lastEvents = events;
  }
}
async function poll() {
  try {
    const response = await fetch('/api/state', {signal: AbortSignal.timeout(2500)});
    if (!response.ok) throw new Error('HMI connection unavailable');
    const state = await response.json(); connected = true;
    setText('#connection', 'Controller connected'); render(state);
  } catch (_) {
    connected = false; setText('#connection', 'Disconnected — controls unavailable');
    document.querySelectorAll('button, input, select').forEach(node => node.disabled = true);
  } finally {
    if (connected) document.querySelectorAll('[data-fault], #order-form input, #order-form select, #order-form button, #orders input, #orders button').forEach(node => node.disabled = false);
    setTimeout(poll, 200);
  }
}
poll();
