const API='/api';

// ── Canvas Animated Background ──
(function(){const c=document.getElementById('bgCanvas');if(!c)return;const ctx=c.getContext('2d');let particles=[];let w,h;function resize(){w=c.width=window.innerWidth;h=c.height=window.innerHeight}resize();window.addEventListener('resize',resize)
class Particle{constructor(){this.reset()}
reset(){this.x=Math.random()*w;this.y=Math.random()*h;this.size=Math.random()*2.5+1;this.speedX=(Math.random()-.5)*.3;this.speedY=(Math.random()-.5)*.3;this.opacity=Math.random()*.25+.05;this.hue=Math.random()*60+230}
update(){this.x+=this.speedX;this.y+=this.speedY;if(this.x<0||this.x>w)this.speedX*=-1;if(this.y<0||this.y>h)this.speedY*=-1}
draw(){ctx.beginPath();ctx.arc(this.x,this.y,this.size,0,Math.PI*2);ctx.fillStyle=`hsla(${this.hue},70%,60%,${this.opacity})`;ctx.fill()}}
for(let i=0;i<50;i++)particles.push(new Particle())
function animate(){ctx.clearRect(0,0,w,h);particles.forEach(p=>{p.update();p.draw()});requestAnimationFrame(animate)}
animate()})()

function showCard(id){document.querySelectorAll('.auth-card').forEach(c=>{c.style.animation='none';c.style.display='none'});const card=document.getElementById(id);card.style.display='block';setTimeout(()=>{card.style.animation=''},10)}

document.getElementById('signupLink').addEventListener('click',e=>{e.preventDefault();showCard('signupCard')})
document.getElementById('signinLink').addEventListener('click',e=>{e.preventDefault();showCard('signinCard')})
document.getElementById('forgotLink').addEventListener('click',e=>{e.preventDefault();showCard('forgotCard')})
document.getElementById('backToSignin').addEventListener('click',e=>{e.preventDefault();showCard('signinCard')})

document.getElementById('signinForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;btn.textContent='Signing in...';const err=document.getElementById('loginError');err.style.display='none';try{const r=await fetch(`${API}/auth/signin`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identifier:document.getElementById('loginIdentifier').value.trim(),password:document.getElementById('loginPassword').value})});const d=await r.json();if(!r.ok){err.textContent=d.error;err.style.display='block';return}sessionStorage.setItem('token',d.token);sessionStorage.setItem('user',JSON.stringify(d.user));window.location.href='/dashboard'}catch(e){err.textContent='Connection error. Check if the server is running.';err.style.display='block'}finally{btn.disabled=false;btn.textContent='Sign In'}})

document.getElementById('signupForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;btn.textContent='Creating...';const err=document.getElementById('signupError');err.style.display='none';const pwd=document.getElementById('signupPassword').value;if(pwd.length<6){err.textContent='Password min 6 characters';err.style.display='block';btn.disabled=false;btn.textContent='Create Account';return}try{const r=await fetch(`${API}/auth/signup`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.getElementById('signupName').value.trim(),email:document.getElementById('signupEmail').value.trim(),phone:document.getElementById('signupPhone').value.trim(),password:pwd})});const d=await r.json();if(!r.ok){err.textContent=d.error;err.style.display='block';return}sessionStorage.setItem('token',d.token);sessionStorage.setItem('user',JSON.stringify(d.user));window.location.href='/dashboard'}catch(e){err.textContent='Connection error';err.style.display='block'}finally{btn.disabled=false;btn.textContent='Create Account'}})

document.getElementById('forgotForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.target.querySelector('button');btn.disabled=true;btn.textContent='Sending...';const err=document.getElementById('forgotError');const suc=document.getElementById('forgotSuccess');err.style.display='none';suc.style.display='none';try{const r=await fetch(`${API}/auth/forgot-password`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('forgotEmail').value.trim()})});const d=await r.json();suc.textContent=d.message||'Reset link sent! Check console in dev mode.';suc.style.display='block'}catch(e){err.textContent='Connection error';err.style.display='block'}finally{btn.disabled=false;btn.textContent='Send Reset Link'}})

if(sessionStorage.getItem('token'))window.location.href='/dashboard'
