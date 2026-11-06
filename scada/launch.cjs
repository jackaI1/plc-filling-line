/* Run upstream FUXA unchanged, with a project and assets in a local sandbox. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const pkg = path.dirname(require.resolve('@frangoteam/fuxa-min/package.json'));
// The published scoped package's plugin scanner expects an adjacent dependency directory.
// npm hoists these dependencies two directories up; expose that directory without copying.
if (!fs.existsSync(path.join(pkg, 'node_modules'))) fs.symlinkSync(path.resolve(pkg, '../..'), path.join(pkg, 'node_modules'), 'dir');
const root = path.resolve(process.env.FUXA_WORK || path.join(__dirname, '../.build/fuxa'));
const port = Number(process.env.FUXA_PORT || 1881);
const modbus = Number(process.env.MODBUS_PORT || 1502);
fs.mkdirSync(path.join(root, '_appdata', '_upload_files', 'operator'), {recursive:true});
for (const filename of ['index.html', 'operator.js', 'operator.css']) {
  fs.copyFileSync(path.join(__dirname, 'operator', filename), path.join(root, '_appdata', '_upload_files', 'operator', filename));
}
const settings = `const s = require(${JSON.stringify(path.join(pkg, 'settings.default.js'))});
module.exports = {...s, uiHost:'127.0.0.1', uiPort:${port}, broadcastAll:true,
logApiLevel:'none', nodeRedEnabled:false, secureEnabled:false, swaggerEnabled:false,
webcamSnapShotsCleanup:false, allowedOrigins:['http://127.0.0.1:${port}']};\n`;
fs.writeFileSync(path.join(root, '_appdata', 'settings.js'), settings);
process.argv = [process.argv[0], path.join(pkg, 'main.js'), '--userDir', root, '--port', String(port)];
require(path.join(pkg, 'main.js'));
process.on('SIGTERM', () => process.emit('SIGINT'));
(async () => {
  const project = JSON.parse(fs.readFileSync(path.join(__dirname, 'filling-line.fuxap')));
  project.devices.line.property.address = `127.0.0.1:${modbus}`;
  project.hmi.views[0].items['OXC_panel'].property.address = `http://127.0.0.1:${port}/resources/operator/index.html`;
  for (let attempt = 0; attempt < 150; attempt++) {
    try {
      const ready = await fetch(`http://127.0.0.1:${port}/api/project`);
      if (ready.ok) {
        const response = await fetch(`http://127.0.0.1:${port}/api/project`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(project)
        });
        if (!response.ok) throw new Error(`Project import returned ${response.status}: ${await response.text()}`);
        console.log(`Operator: http://127.0.0.1:${port}/resources/operator/index.html`);
        return;
      }
    } catch (error) {
      if (attempt === 149) { console.error(error.message); process.emit('SIGINT'); process.exitCode = 1; }
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
})();
