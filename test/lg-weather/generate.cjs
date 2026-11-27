const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const W=require('./weather.js');
const dir=path.join(__dirname,'cards');
async function main(){
 const demo={temperature_2m:2.5,apparent_temperature:-1,relative_humidity_2m:85,weather_code:71,wind_speed_10m:12,pressure_msl:1014,is_day:0,time:'2000-01-01T12:00',timestamp:946728000000,daily:{time:['2000-01-01','2000-01-02','2000-01-03'],weather_code:[71,3,61],temperature_2m_min:[-2,0,1],temperature_2m_max:[3,5,7]}};
 assert.equal(W.locations.length,5);assert.equal(W.find('WARSZAWA - Odolany').id,'odolany');assert.equal(W.find('Niechorze - widok na latarnię').id,'niechorze');assert.ok(W.render(W.locations[0],demo).includes('2,5°C'));assert.ok(W.render(W.locations[0],null).includes('Brak aktualnych danych'));
 assert.equal(W.find('Praga').id,'praga');assert.equal(W.find('Praha').id,'praga');assert.equal(W.find('Prague').id,'praga');assert.equal(W.find('Warszawa - Praga'),undefined);
 const svg=W.render(W.locations[4],demo);assert.ok(svg.includes('Dziś'));assert.ok(svg.includes('Jutro'));assert.ok(svg.includes('↓ -2° ↑ 3°'));assert.ok(svg.includes('↓ 1° ↑ 7°'));assert.ok(svg.includes('data-weather-ts="946728000000"'));assert.ok(W.url(W.locations[4]).includes('forecast_days=3'));
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
