/* Shared SVG renderer for LG browser and Node.js. */
(function(root){
'use strict';
var locations=[{"id":"chojnice","name":"Chojnice","match":"chojnice","lat":53.7,"lon":17.56},{"id":"odolany","name":"Warszawa – Odolany","match":"warszawa - odolany","lat":52.222,"lon":20.935},{"id":"zalewo","name":"Zalewo","match":"zalewo","lat":53.845,"lon":19.605},{"id":"niechorze","name":"Niechorze","match":"niechorze - widok na latarnie","lat":54.094,"lon":15.066},{"id":"praga","name":"Praga","match":"praga","lat":50.075,"lon":14.438}];
var fields='temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,pressure_msl,is_day';
function normalize(s){return s.toLowerCase().replace(/[–—]/g,'-').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ł/g,'l').trim()}
function find(name){return locations.find(function(l){return l.match===normalize(name)})}
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]})}
function num(n,dec){return typeof n==='number'&&isFinite(n)?n.toFixed(dec).replace('.',','):'—'}
function condition(n){if(n===0)return 'Bezchmurnie';if(n===1||n===2)return 'Małe zachmurzenie';if(n===3)return 'Pochmurno';if(n===45||n===48)return 'Mgła';if(n>=51&&n<=57)return 'Mżawka';if(n>=61&&n<=67)return 'Deszcz';if(n>=71&&n<=77)return 'Śnieg';if(n>=80&&n<=82)return 'Przelotny deszcz';if(n===85||n===86)return 'Przelotny śnieg';if(n>=95&&n<=99)return 'Burza';return 'Brak danych'}
function icon(c){
var n=c.weather_code, sun='<circle cx="35" cy="32" r="15" fill="#ffd36b"/><path d="M35 7v7M35 50v7M10 32h7M53 32h7M17 14l5 5M48 45l5 5M17 50l5-5M48 19l5-5" stroke="#ffd36b" stroke-width="3" stroke-linecap="round"/>', moon='<path d="M42 13a21 21 0 1 0 16 30A24 24 0 0 1 42 13" fill="#dce9ff"/>', cloud='<path d="M22 52a13 13 0 0 1 0-26 19 19 0 0 1 36-4 15 15 0 0 1 1 30Z" fill="#c8dbe9"/>';
if(n===0)return c.is_day?sun:moon;
if(n===1||n===2)return (c.is_day?sun:moon)+'<g transform="translate(12 12)">'+cloud+'</g>';
if(n===45||n===48)return cloud+'<path d="M14 60h56M20 68h44" stroke="#dce9ff" stroke-width="3" stroke-linecap="round"/>';
if((n>=71&&n<=77)||n===85||n===86)return cloud+'<g fill="#fff"><circle cx="28" cy="62" r="3"/><circle cx="47" cy="70" r="3"/><circle cx="63" cy="62" r="3"/></g>';
if(n>=95)return cloud+'<path d="M44 50l-12 19h11l-5 15 19-23H45l7-11" fill="#ffd36b"/>';
if(n>=51&&n<=82)return cloud+'<path d="M25 59l-5 11M43 59l-5 11M61 59l-5 11" stroke="#67c8ff" stroke-width="4" stroke-linecap="round"/>';
return cloud;
}
function render(l,c){
var valid=c&&typeof c.temperature_2m==='number'&&isFinite(c.temperature_2m)&&typeof c.time==='string';
if(!valid)return '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="228" viewBox="0 0 320 228"><rect width="320" height="228" rx="14" fill="#102436"/><g fill="#fff" font-family="Arial,sans-serif"><text x="16" y="35" font-size="20">'+esc(l.name)+'</text><text x="16" y="105" font-size="19">Brak aktualnych danych</text><text x="16" y="207" font-size="12">Źródło: Open-Meteo</text></g></svg>';
var dt=String(c.time).replace('T',' ').slice(0,16);
return '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="228" viewBox="0 0 320 228"><rect width="320" height="228" rx="14" fill="#102436"/><rect x="10" y="10" width="300" height="208" rx="10" fill="none" stroke="#41677e"/><g font-family="Arial,sans-serif" fill="#fff"><text x="20" y="34" font-size="19" font-weight="bold">'+esc(l.name)+'</text><g transform="translate(20 41)">'+icon(c)+'</g><text x="116" y="88" font-weight="bold" font-size="42">'+num(c.temperature_2m,1)+'°C</text><text x="20" y="119" font-size="18">'+esc(condition(c.weather_code))+'</text><path d="M20 132h280" stroke="#41677e"/><g font-size="15"><text x="20" y="153">Odczuwalna: '+num(c.apparent_temperature,1)+'°C</text><text x="20" y="175">Wiatr: '+num(c.wind_speed_10m,0)+' km/h</text><text x="170" y="153">Wilg.: '+num(c.relative_humidity_2m,0)+'%</text><text x="170" y="175">'+num(c.pressure_msl,0)+' hPa</text></g><text x="20" y="196" font-size="12" fill="#b9d6eb">Dane lokalne: '+esc(dt)+'</text><text x="20" y="211" font-size="11" fill="#b9d6eb">Open-Meteo • dane modelowe</text></g></svg>';
}
function url(l){return 'https://api.open-meteo.com/v1/forecast?latitude='+l.lat+'&longitude='+l.lon+'&current='+fields+'&timezone=auto&forecast_days=1'}
function get(l){return fetch(url(l),{cache:'no-store'}).then(function(r){if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(function(d){if(!d.current||typeof d.current.temperature_2m!=='number'||!isFinite(d.current.temperature_2m)||!d.current.time)throw Error('Brak danych');return d.current})}
var api={locations:locations,find:find,render:render,get:get,url:url};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.WeatherPilot=api;
})(typeof window!=='undefined'?window:this);
