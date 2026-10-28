let jobs = [];
let listTag = '';
let selected = null;
let downloadUrl = null;
let generation = 0;
let clearing = false;
let currentJob = null;
let lastSeen = null;
let listed = false;

const byId = (id) => document.getElementById(id);
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
  byId('favicon').href = iconUrl(unread > 0);
}

function trackUnread() {
  const newest = jobs.length ? jobs[0].id : 0;

  if (lastSeen === null || !document.hidden) {
    lastSeen = newest;
  } else if (newest < lastSeen) {
    // Limpar o histórico em outra aba faz os números recomeçarem do 1.
    lastSeen = 0;
  }

  updateUnread();
}

function date(value) {
  return new Date(value).toLocaleString('pt-BR');
}

function fileName(job, extension) {
  const created = new Date(job.created_at);
  const pad = (value) => String(value).padStart(2, '0');
  const day = `${created.getFullYear()}-${pad(created.getMonth() + 1)}-${pad(created.getDate())}`;
  const time = `${pad(created.getHours())}-${pad(created.getMinutes())}-${pad(created.getSeconds())}`;

  return `impressao-${job.id}_${day}_${time}.${extension}`;
}

function renderList() {
  const query = byId('search').value.toLocaleLowerCase();
  const number = /^\s*#\s*(\d+)\s*$/.exec(query);
  const matches = (job) =>
    number ? job.id === Number(number[1]) : (job.id + ' ' + job.preview).toLocaleLowerCase().includes(query);

  byId('list').replaceChildren();

  for (const job of jobs.filter(matches)) {
    const label = document.createElement('strong');
    label.textContent = 'Impressão #' + job.id + ' · ' + date(job.created_at);

    const preview = document.createElement('small');
    preview.textContent = job.preview || '(sem texto)';

    const button = document.createElement('button');
    button.className = 'item' + (selected === job.id ? ' active' : '');
    button.append(label, preview);
    button.onclick = () => show(job.id);

    byId('list').append(button);
  }

  if (!byId('list').children.length) {
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = 'Nenhuma impressão encontrada.';
    byId('list').append(empty);
  }

  byId('count').textContent = 'Histórico (' + jobs.length + ')';
  byId('clear').disabled = clearing || jobs.length === 0;
}

async function loadJob(id) {
  const response = await fetch('/api/jobs/' + id);

  if (!response.ok) {
    throw Error('Falha ao carregar impressão');
  }

  return response.json();
}

async function show(id, loaded) {
  const version = generation;

  selected = id;
  renderList();

  try {
    const job = loaded || (await loadJob(id));

    if (selected !== id || version !== generation) {
      return;
    }

    byId('title').textContent = 'Impressão #' + id;
    byId('meta').textContent = date(job.created_at) + ' · ' + (REASONS[job.reason] || REASONS.disconnect);
    currentJob = job;
    renderCurrent();

    if (downloadUrl) {
      URL.revokeObjectURL(downloadUrl);
    }

    const bytes = Uint8Array.from(atob(job.raw_base64), (character) => character.charCodeAt(0));
    downloadUrl = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
    byId('download').href = downloadUrl;
    byId('download').download = fileName(job, 'bin');
    byId('download').hidden = false;
  } catch (error) {
    byId('status').textContent = error.message;
  }
}

function renderCurrent() {
  if (!currentJob) {
    return;
  }

  const events = currentJob.events;
  byId('events').replaceChildren();
  byId('events').hidden = events.length === 0;

  for (const event of events) {
    const description = document.createElement('p');
    description.textContent = event.description;
    byId('events').append(description);
  }

  byId('paper-scroll').hidden = events.length > 0 && currentJob.lines.length === 0;
  const qrWarnings = renderPaper(byId('paper'), currentJob.lines);
  byId('image').hidden = currentJob.lines.length === 0;
  byId('warnings').textContent = [...currentJob.warnings, ...qrWarnings].join('\n');
}

function showEmpty(message) {
  const empty = document.createElement('p');
  empty.className = 'empty';
  empty.textContent = message;

  byId('title').textContent = 'Selecione uma impressão';
  byId('paper').replaceChildren(empty);
  byId('paper-scroll').hidden = false;
}

async function refresh() {
  const version = generation;

  try {
    // Sem mudanças o servidor responde 304, sem corpo: não baixa nem recria a lista,
    // o que perderia foco, hover e rolagem a cada 2 segundos.
    const response = await fetch('/api/jobs', {
      headers: listTag ? { 'If-None-Match': listTag } : {},
    });

    if (response.status !== 304 && !response.ok) {
      throw Error('HTTP ' + response.status);
    }

    if (!clearing && version === generation) {
      if (response.status !== 304) {
        const previous = jobs.length ? jobs[0].id : 0;

        listTag = response.headers.get('ETag') || '';
        jobs = await response.json();
        renderList();
        trackUnread();

        const newest = jobs.length ? jobs[0].id : 0;
        if (byId('follow').checked && listed) {
          await followNewest(newest < previous ? 0 : previous);
        }
        listed = true;
      }

      byId('status').textContent = 'Conectado · atualização automática a cada 2 segundos';

      if (selected === null && jobs.length) {
        await show(jobs[0].id);
      } else if (!jobs.length && !byId('paper').children.length) {
        showEmpty(
          'Envie uma impressão para a porta TCP configurada. ' +
            'As impressões anteriores ficam salvas aqui, inclusive após reiniciar o servidor.',
        );
      }
    }
  } catch {
    byId('status').textContent = 'Servidor indisponível. Tentando reconectar…';
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
  if (clearing || !jobs.length) {
    return;
  }

  if (!confirm('Apagar todas as impressões do histórico? Essa ação não pode ser desfeita.')) {
    return;
  }

  clearing = true;
  generation++;
  renderList();

  try {
    const response = await fetch('/api/jobs', { method: 'DELETE' });

    if (!response.ok) {
      throw Error('Não foi possível limpar o histórico.');
    }

    generation++;
    jobs = [];
    listTag = '';
    selected = null;
    currentJob = null;
    byId('search').value = '';
    trackUnread();

    if (downloadUrl) {
      URL.revokeObjectURL(downloadUrl);
      downloadUrl = null;
    }

    byId('download').hidden = true;
    byId('download').removeAttribute('href');
    byId('image').hidden = true;
    byId('meta').textContent = '';
    byId('warnings').textContent = '';
    byId('events').replaceChildren();
    byId('events').hidden = true;

    showEmpty('Histórico limpo. As próximas impressões aparecerão aqui.');
    byId('status').textContent = 'Histórico apagado.';
  } catch (error) {
    byId('status').textContent = error.message;
  } finally {
    clearing = false;
    renderList();
  }
}

async function downloadImage() {
  try {
    const url = URL.createObjectURL(await paperPng(byId('paper')));

    const link = document.createElement('a');
    link.href = url;
    link.download = fileName(currentJob, 'png');
    link.click();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    byId('status').textContent = error.message;
  }
}

function updateThemeButton() {
  const label = document.documentElement.dataset.theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro';

  byId('theme').title = label;
  byId('theme').setAttribute('aria-label', label);
}

function toggleTheme() {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';

  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem('theme', theme);
  } catch {}

  updateThemeButton();
}

function toggleFollow() {
  try {
    localStorage.setItem('show-new-jobs', byId('follow').checked ? '1' : '0');
  } catch {}

  if (byId('follow').checked) {
    followNewest(0).catch((error) => {
      byId('status').textContent = error.message;
    });
  }
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    trackUnread();
  }
});

systemDark.addEventListener('change', () => {
  applyTheme();
  updateThemeButton();
});

byId('clear').onclick = clearHistory;
byId('image').onclick = downloadImage;
byId('theme').onclick = toggleTheme;
byId('follow').onchange = toggleFollow;
byId('search').oninput = renderList;

try {
  byId('follow').checked = localStorage.getItem('show-new-jobs') === '1';
} catch {}

// Barras clássicas ocupam espaço e as sobrepostas não; o recuo completa os 12px
// para os itens alinharem com a busca e o botão nos dois casos.
byId('list').style.paddingRight = Math.max(0, 12 - (byId('list').offsetWidth - byId('list').clientWidth)) + 'px';

updateUnread();
updateThemeButton();
refresh();
