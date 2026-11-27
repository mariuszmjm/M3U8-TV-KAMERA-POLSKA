const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const W=require('./weather.js');
const dir=path.join(__dirname,'cards');
async function main(){
 const demo={temperature_2m:2.5,apparent_temperature:-1,relative_humidity_2m:85,weather_code:71,wind_speed_10m:12,pressure_msl:1014,is_day:0,time:'2000-01-01T12:00'};
 assert.equal(W.locations.length,5);assert.equal(W.find('WARSZAWA - Odolany').id,'odolany');assert.equal(W.find('Niechorze - widok na latarnię').id,'niechorze');assert.ok(W.render(W.locations[0],demo).includes('2,5°C'));assert.ok(W.render(W.locations[0],null).includes('Brak aktualnych danych'));
 if(process.argv.includes('--test')){console.log('Test generatora OK');return}
 await fs.mkdir(dir,{recursive:true});
 let failures=0;
 for(const l of W.locations){
  try{
   const c=await W.get(l),file=path.join(dir,l.id+'.svg');
   await fs.writeFile(file+'.tmp',W.render(l,c),'utf8');await fs.rename(file+'.tmp',file);
   console.log(l.name,c.time);
  }catch(e){failures++;console.error(l.name,e.message)}
 }
 if(failures)console.error('Nie odświeżono '+failures+' kart; zachowano ostatnie dane.');
 if(failures===W.locations.length)process.exitCode=1;
}
main().catch(e=>{console.error(e);process.exitCode=1});
