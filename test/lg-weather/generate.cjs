const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const W=require('./weather.js'),{spawnSync}=require('node:child_process');
const dir=path.join(__dirname,'cards');
async function main(){
 const demo={temperature_2m:2.5,apparent_temperature:-1,relative_humidity_2m:85,weather_code:71,wind_speed_10m:12,pressure_msl:1014,is_day:0,time:'2000-01-01T12:00',timestamp:946728000000,daily:{time:['2000-01-01','2000-01-02','2000-01-03'],weather_code:[71,3,61],temperature_2m_min:[-2,0,1],temperature_2m_max:[3,5,7]}};
 assert.equal(W.locations.length,5);assert.equal(W.find('WARSZAWA - Odolany').id,'odolany');assert.equal(W.find('Niechorze - widok na latarnię').id,'niechorze');assert.ok(W.render(W.locations[0],demo).includes('2,5°C'));assert.ok(W.render(W.locations[0],null).includes('Brak aktualnych danych'));
 assert.equal(W.find('Praga').id,'praga');assert.equal(W.find('Praha').id,'praga');assert.equal(W.find('Prague').id,'praga');assert.equal(W.find('Warszawa - Praga'),undefined);
 const svg=W.render(W.locations[4],demo);assert.ok(svg.includes('Dziś'));assert.ok(svg.includes('Jutro'));assert.ok(svg.includes('↓ -2° ↑ 3°'));assert.ok(svg.includes('↓ 1° ↑ 7°'));assert.ok(svg.includes('data-weather-ts="946728000000"'));assert.ok(W.url(W.locations[4]).includes('forecast_days=3'));
 if(process.argv.includes('--test')){const t=spawnSync('python3',[path.join(__dirname,'locations.py'),'--test'],{stdio:'inherit'});assert.equal(t.status,0);console.log('Test generatora OK');return}
 await fs.mkdir(dir,{recursive:true});
 const task=spawnSync('python3',[path.join(__dirname,'locations.py')],{stdio:'inherit',timeout:110000});
 if(task.status!==0)console.error('Nie udało się odświeżyć indeksu lokalizacji – zachowano dotychczasowy.');
 let failures=0;
 for(const l of W.locations){
  try{
   const c=await W.get(l),file=path.join(dir,l.id+'.svg');
   await fs.writeFile(file+'.tmp',W.render(l,c),'utf8');await fs.rename(file+'.tmp',file);
   console.log(l.name,c.time);
  }catch(e){failures++;console.error(l.name,e.message)}
 }
 if(failures)console.error('Nie odświeżono '+failures+' kart; zachowano ostatnie dane.');
 let registry;
 try{registry=JSON.parse(await fs.readFile(path.join(dir,'locations.json'),'utf8'))}catch(e){console.error('Brak indeksu rozszerzonego:',e.message);process.exitCode=1;return}
 const due=[];
 for(const l of Object.values(registry.locations)){
  const file=path.join(dir,l.id+'.svg');
  let age=Infinity;
  try{const svg=await fs.readFile(file,'utf8');const m=svg.match(/data-weather-ts="(\d+)"/);if(m)age=Date.now()-Number(m[1])}catch(e){}
  if(age>=4*3600000)due.push({l,age,file})
 }
 due.sort((a,b)=>b.age-a.age);
 // Bound each run and use batches; do not replace the last valid card on errors.
 let updated=0;
 for(let i=0;i<Math.min(due.length,250);i+=20){
  const batch=due.slice(i,Math.min(i+20,250));
  try{
   const rows=await W.getMany(batch.map(x=>x.l));
   for(let j=0;j<batch.length;j++)if(rows[j]){
    const x=batch[j];await fs.writeFile(x.file+'.tmp',W.render(x.l,rows[j]),'utf8');await fs.rename(x.file+'.tmp',x.file);updated++;
   }
  }catch(e){console.error('Pakiet pogody:',e.message);if(/429/.test(e.message))break}
 }
 console.log('Rozszerzone karty: '+updated+' z '+due.length+' wymagających odświeżenia; lokalizacje: '+Object.keys(registry.locations).length);
 if(failures===W.locations.length&&updated===0)process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1});
