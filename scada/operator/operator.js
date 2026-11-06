'use strict';
const $ = id => document.getElementById(id);
const socket = io({transports:['websocket']});
const tags = {};
const samples = [];
let lastSeen = 0;
let activeAlarm = null;
let disposed = false;
const buttons = ['start','stop','reset','hold'];
function write(id, value) {
  if (Date.now() - lastSeen > 3000) return;
  socket.emit('device-values',{cmd:'set',var:{source:'line',id,value}});
}
$('start').onclick=()=>write('StartCommand',1);
$('stop').onclick=()=>write('StopCommand',1);
$('reset').onclick=()=>write('ResetCommand',1);
$('hold').onchange=()=>write('HoldFillSensor',Number($('hold').checked));
$('ack').onclick=async()=>{
  if (!activeAlarm) return;
  try {
    const response=await fetch('/api/alarmack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({params:activeAlarm.name})});
    if (!response.ok) throw new Error('Alarm acknowledgement failed. Try again.');
    await alarms();
  } catch(error) { $('error').textContent=error.message; }
};
function draw(){
  $('motor').setAttribute('class',tags.Conveyor?'running':'');
  $('conveyor').setAttribute('class',tags.Conveyor?'running':'');
  $('valve').setAttribute('class',tags.Valve?'open':'');
  $('flow').setAttribute('class',tags.Valve?'open':'');
  $('flow').setAttribute('visibility',tags.Valve?'visible':'hidden');
  $('motor-state').textContent=tags.Conveyor?'Running':'Stopped';
  $('valve-state').textContent=tags.Valve?'Open':'Closed';
  $('count').textContent=tags.BatchCount??0;
  $('bottle').setAttribute('transform',`translate(${60+(tags.BottlePosition??0)*.68} 0)`);
  const height=(tags.BottleLevel??0)*.044;
  $('bottle-fill').setAttribute('height',height);
  $('bottle-fill').setAttribute('y',224-height);
  if (document.activeElement!==$('hold')) $('hold').checked=Boolean(tags.HoldFillSensor);
  for (const [name,value] of Object.entries(tags)) {
    if (name.endsWith('Command')) continue;
    let cell=$(`tag-${name}`);
    if(!cell){const row=document.createElement('tr');const label=document.createElement('td');label.textContent=name;cell=document.createElement('td');cell.id=`tag-${name}`;row.append(label,cell);$('tags').append(row);}
    cell.textContent=value;
  }
}
socket.on('connect',()=>{socket.emit('device-values','get');socket.emit('alarms-status','get');});
socket.on('device-values',message=>{
  if(message.id!=='line') return;
  let fresh = false;
  for(const tag of Object.values(message.values||{})) {
    if(tag.id==='BottlePosition' && tag.value!==null && tag.value!==undefined) fresh=true;
    if(tag.value!==null && tag.value!==undefined) tags[tag.id]=Number(tag.value);
  }
  if(fresh){lastSeen=Date.now();draw();}
});
socket.on('disconnect',()=>{lastSeen=0;sample();});
socket.on('device-status',message=>{if(message.id==='line' && ['connect-error','connect-off','connect-failed'].includes(message.status)){lastSeen=0;sample();}});
async function alarms(){
  try{
    const response=await fetch('/api/alarms');
    if(!response.ok) return;
    const list=await response.json();
    activeAlarm=list.find(alarm=>alarm.name.startsWith('FillBlocked'))||null;
    const blocked=Boolean(tags.FillBlocked);
    $('alarm').dataset.state=activeAlarm?(activeAlarm.acktime?'acknowledged':'unacknowledged'):'clear';
    $('alarm-text').textContent=blocked?'Fill position did not clear':activeAlarm?'Fill fault cleared; acknowledgement required':'No active filling-station alarm';
    $('alarm-detail').textContent=activeAlarm?(activeAlarm.acktime?'Acknowledged. Clear the cause and reset before restarting.':'Acknowledge the warning, release the held sensor, then reset.'):'Start a batch to watch the line.';
    $('ack').disabled=!activeAlarm||activeAlarm.toack!==1;
  }catch(error){$('error').textContent='Cannot read alarm status. Check the local FUXA server.';}
}
function sample(){
  const online=Date.now()-lastSeen<3000;
  $('connection').textContent=online?'Controller connected':'Controller disconnected';
  $('connection').className=online?'online':'';
  buttons.forEach(id=>$(id).disabled=!online);
  if(!online){$('motor').setAttribute('class','');$('conveyor').setAttribute('class','');$('valve').setAttribute('class','');$('flow').setAttribute('class','');$('flow').setAttribute('visibility','hidden');$('motor-state').textContent='Unknown';$('valve-state').textContent='Unknown';return;}
  const now=Date.now();samples.push([now,tags.BatchCount??0]);
  while(samples.length && samples[0][0]<now-60000) samples.shift();
  if(samples.length>121) samples.shift();
  $('trend-line').setAttribute('points',samples.map(([ts,count])=>`${980-(now-ts)/60000*950},${150-count*27}`).join(' '));
  $('trend').dataset.lastCount=tags.BatchCount??0;
}
const interval=setInterval(()=>{sample();alarms();},500);
window.addEventListener('pagehide',()=>{if(!disposed){disposed=true;clearInterval(interval);socket.close();}});
