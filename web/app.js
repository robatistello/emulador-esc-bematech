let jobs = [],
  listTag = '',
  selected = null,
  downloadUrl = null,
  generation = 0,
  clearing = false,
  currentJob = null,
  lastSeen = null,
  listed = false;

const $ = (id) => document.getElementById(id);
const pageTitle = document.title;
const REASONS = {
  cut: 'Finalizado por corte',
  idle: 'Finalizado após 60 segundos sem dados',
  disconnect: 'Finalizado ao encerrar conexão',
};

function iconUrl(dot) {
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">' +
    '<rect x="3" y="3" width="122" height="122" rx="26" fill="#14263e"/>' +
    '<rect x="34" y="18" width="61" height="40" rx="4" fill="#f2f6fc"/>' +
    '<rect x="19" y="46" width="91" height="49" rx="8" fill="#64afff"/>' +
    '<circle cx="95" cy="61" r="4" fill="#14263e"/>' +
    '<rect x="34" y="76" width="61" height="35" fill="#f2f6fc"/>' +
    '<rect x="44" y="85" width="41" height="4" fill="#14263e"/>' +
    '<rect x="44" y="95" width="35" height="4" fill="#14263e"/>' +
    (dot ? '<circle cx="101" cy="27" r="22" fill="#e5484d" stroke="#fff" stroke-width="6"/>' : '') +
    '</svg>';
  return 'data:image/svg+xml,' + encodeURIComponent(svg);
}

function updateUnread() {
  const unread = lastSeen === null ? 0 : jobs.filter((job) => job.id > lastSeen).length;
  document.title = (unread ? `(${unread}) ` : '') + pageTitle;
  $('favicon').href = iconUrl(unread > 0);
}

function trackUnread() {
  const newest = jobs.length ? jobs[0].id : 0;
  if (lastSeen === null || !document.hidden) lastSeen = newest;
  // Limpar o histórico em outra aba faz os números recomeçarem do 1.
  else if (newest < lastSeen) lastSeen = 0;
  updateUnread();
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) trackUnread();
});

updateUnread();

function date(value) {
  return new Date(value).toLocaleString('pt-BR');
}

function fileName(job, extension) {
  const d = new Date(job.created_at),
    two = (n) => String(n).padStart(2, '0');
  const stamp = `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}_${two(d.getHours())}-${two(d.getMinutes())}-${two(d.getSeconds())}`;
  return `impressao-${job.id}_${stamp}.${extension}`;
}

function renderList() {
  $('list').replaceChildren();
  const query = $('search').value.toLocaleLowerCase(),
    number = /^\s*#\s*(\d+)\s*$/.exec(query);
  const matches = (job) =>
    number ? job.id === Number(number[1]) : (job.id + ' ' + job.preview).toLocaleLowerCase().includes(query);
  for (const job of jobs.filter(matches)) {
    const button = document.createElement('button');
    button.className = 'item' + (selected === job.id ? ' active' : '');
    const label = document.createElement('strong');
    label.textContent = 'Impressão #' + job.id + ' · ' + date(job.created_at);
    const preview = document.createElement('small');
    preview.textContent = job.preview || '(sem texto)';
    button.append(label, preview);
    button.onclick = () => show(job.id);
    $('list').append(button);
  }
  if (!$('list').children.length) {
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = 'Nenhuma impressão encontrada.';
    $('list').append(p);
  }
  $('count').textContent = 'Histórico (' + jobs.length + ')';
  $('clear').disabled = clearing || jobs.length === 0;
}

async function loadJob(id) {
  const response = await fetch('/api/jobs/' + id);
  if (!response.ok) throw Error('Falha ao carregar impressão');
  return response.json();
}

async function show(id, loaded) {
  const version = generation;
  selected = id;
  renderList();
  try {
    const job = loaded || (await loadJob(id));
    if (selected !== id || version !== generation) return;
    $('title').textContent = 'Impressão #' + id;
    $('meta').textContent = date(job.created_at) + ' · ' + (REASONS[job.reason] || REASONS.disconnect);
    currentJob = job;
    renderCurrent();
    if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    const bytes = Uint8Array.from(atob(job.raw_base64), (c) => c.charCodeAt(0));
    downloadUrl = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
    $('download').href = downloadUrl;
    $('download').download = fileName(job, 'bin');
    $('download').hidden = false;
  } catch (error) {
    $('status').textContent = error.message;
  }
}

function showEmpty(message) {
  $('title').textContent = 'Selecione uma impressão';
  const p = document.createElement('p');
  p.className = 'empty';
  p.textContent = message;
  $('paper').replaceChildren(p);
  $('paper-scroll').hidden = false;
}

async function refresh() {
  const version = generation;
  try {
    // Sem mudanças o servidor responde 304, sem corpo: não baixa nem recria a lista,
    // o que perderia foco, hover e rolagem a cada 2 segundos.
    const response = await fetch('/api/jobs', {
      headers: listTag ? { 'If-None-Match': listTag } : {},
    });
    if (response.status !== 304 && !response.ok) throw Error('HTTP ' + response.status);
    if (!clearing && version === generation) {
      if (response.status !== 304) {
        const previous = jobs.length ? jobs[0].id : 0;
        listTag = response.headers.get('ETag') || '';
        jobs = await response.json();
        renderList();
        trackUnread();
        const newest = jobs.length ? jobs[0].id : 0;
        if ($('follow').checked && listed) await followNewest(newest < previous ? 0 : previous);
        listed = true;
      }
      $('status').textContent = 'Conectado · atualização automática a cada 2 segundos';
      if (selected === null && jobs.length) await show(jobs[0].id);
      else if (!jobs.length && !$('paper').children.length)
        showEmpty(
          'Envie uma impressão para a porta TCP configurada. As impressões anteriores ficam salvas aqui, inclusive após reiniciar o servidor.',
        );
    }
  } catch (error) {
    $('status').textContent = 'Servidor indisponível. Tentando reconectar…';
  }
  setTimeout(refresh, 2000);
}

async function followNewest(after) {
  for (const summary of jobs.filter((job) => job.id > after)) {
    const job = await loadJob(summary.id);
    // Muitos sistemas mandam a abertura da gaveta logo depois do cupom, em outra
    // conexão; pular para ela esconderia a impressão que acabou de sair.
    if (job.lines.length || !job.events.length) {
      await show(summary.id, job);
      return;
    }
  }
}

async function clearHistory() {
  if (clearing || !jobs.length) return;
  if (!confirm('Apagar todas as impressões do histórico? Essa ação não pode ser desfeita.')) return;
  clearing = true;
  generation++;
  renderList();
  try {
    const response = await fetch('/api/jobs', { method: 'DELETE' });
    if (!response.ok) throw Error('Não foi possível limpar o histórico.');
    generation++;
    jobs = [];
    listTag = '';
    selected = null;
    currentJob = null;
    $('search').value = '';
    trackUnread();
    if (downloadUrl) {
      URL.revokeObjectURL(downloadUrl);
      downloadUrl = null;
    }
    $('download').hidden = true;
    $('download').removeAttribute('href');
    $('image').hidden = true;
    $('meta').textContent = '';
    $('warnings').textContent = '';
    $('events').replaceChildren();
    $('events').hidden = true;
    showEmpty('Histórico limpo. As próximas impressões aparecerão aqui.');
    $('status').textContent = 'Histórico apagado.';
  } catch (error) {
    $('status').textContent = error.message;
  } finally {
    clearing = false;
    renderList();
  }
}

$('clear').onclick = clearHistory;
$('image').onclick = async () => {
  try {
    const url = URL.createObjectURL(await paperPng($('paper')));
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName(currentJob, 'png');
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    $('status').textContent = error.message;
  }
};

function renderCurrent() {
  if (!currentJob) return;
  const events = currentJob.events;
  $('events').replaceChildren();
  $('events').hidden = events.length === 0;
  for (const event of events) {
    const p = document.createElement('p');
    p.textContent = event.description;
    $('events').append(p);
  }
  $('paper-scroll').hidden = events.length > 0 && currentJob.lines.length === 0;
  const qrWarnings = renderPaper($('paper'), currentJob.lines);
  $('image').hidden = currentJob.lines.length === 0;
  $('warnings').textContent = [...currentJob.warnings, ...qrWarnings].join('\n');
}

function updateThemeButton() {
  const label = document.documentElement.dataset.theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro';
  $('theme').title = label;
  $('theme').setAttribute('aria-label', label);
}

$('theme').onclick = () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem('tema', theme);
  } catch {}
  updateThemeButton();
};

systemDark.addEventListener('change', () => {
  applyTheme();
  updateThemeButton();
});

updateThemeButton();

// Barras clássicas ocupam espaço e as sobrepostas não; o recuo completa os 12px
// para os itens alinharem com a busca e o botão nos dois casos.
$('list').style.paddingRight = Math.max(0, 12 - ($('list').offsetWidth - $('list').clientWidth)) + 'px';
try {
  $('follow').checked = localStorage.getItem('mostrar-novas') === '1';
} catch {}
$('follow').onchange = () => {
  try {
    localStorage.setItem('mostrar-novas', $('follow').checked ? '1' : '0');
  } catch {}
  if ($('follow').checked)
    followNewest(0).catch((error) => {
      $('status').textContent = error.message;
    });
};

$('search').oninput = renderList;
refresh();
