// Live suggestions
const q = document.getElementById('search-input');
const box = document.getElementById('suggestions');
if(q){
  q.addEventListener('input', async () => {
    const val = q.value.trim();
    if(!val){ box.style.display='none'; return; }
    const res = await fetch(`/api/suggest?q=${encodeURIComponent(val)}`);
    const data = await res.json();
    if(!data.length){ box.style.display='none'; return; }
    box.innerHTML = '';
    data.forEach(it => {
      const row = document.createElement('div');
      row.className = 'item';
      row.innerHTML = `<span>${it.name}</span><small>★ ${Number(it.avg_rating).toFixed(1)} • ${it.review_count} reviews</small>`;
      row.onclick = () => { q.value = it.name; box.style.display='none'; };
      box.appendChild(row);
    });
    box.style.display = 'block';
  });
  document.addEventListener('click', (e)=>{
    if(!box.contains(e.target) && e.target !== q) box.style.display='none';
  });
}
