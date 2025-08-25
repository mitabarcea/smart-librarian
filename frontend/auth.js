const API = location.origin;   // was "http://127.0.0.1:8000"

function show(el, msg, ok=true){
    el.textContent = msg;
    el.className = 'alert ' + (ok?'ok':'err');
    el.style.display = 'block';
}
function hide(el){el.style.display = 'none'}

async function post(url, body, auth=false){
    const headers = {'Content-Type':'application/json'};
    const tok = localStorage.getItem('access');
    if(auth && tok) headers['Authorization'] = 'Bearer ' + tok;
    const res = await fetch(API+url, {method:'POST', headers, body: JSON.stringify(body)});
    const data = await res.json().catch(()=>({ }));
    if(!res.ok) throw (data.detail || data.message || JSON.stringify(data));
    return data;
}
function saveToken(data){
    if(data && data.access_token) localStorage.setItem('access', data.access_token);
}
function goto(url){window.location.href = url; }
