// Chat page. Logged-in users get multiple named sessions (sidebar, backed by
// the DB via /sessions); a guest gets a single ephemeral "global_user"
// conversation with no sidebar, matching the old behavior.
const API_ENDPOINT = "/chat";
const IMAGE_ENDPOINT = "/generate-image";

const log = document.getElementById('log');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const imageModeBtn = document.getElementById('imageModeBtn');
const statusText = document.getElementById('statusText');
const authArea = document.getElementById('authArea');
const sidebar = document.getElementById('sidebar');
const sessionListEl = document.getElementById('sessionList');
const newChatBtn = document.getElementById('newChatBtn');

let isSending = false;
let currentSessionId = null;
let sessions = [];
let imageMode = false;

function autoGrow(){
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 160) + 'px';
}
input.addEventListener('input', autoGrow);

function nowLabel(){
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function clearLog(){
  log.innerHTML = '';
}

function addMessage(role, text){
  const row = document.createElement('div');
  row.className = 'row ' + role;

  const wrap = document.createElement('div');
  wrap.className = 'bubble-wrap';

  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = (role === 'user' ? 'You' : 'Assistant') + ' · ' + nowLabel();

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;

  wrap.appendChild(meta);
  wrap.appendChild(bubble);
  row.appendChild(wrap);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
  return bubble;
}

function isImageUrl(content){
  return typeof content === 'string' && content.startsWith('/static/photos/');
}

function addImageMessage(role, url){
  const bubble = addMessage(role, '');
  const img = document.createElement('img');
  img.src = url;
  img.alt = 'Generated image';
  bubble.appendChild(img);
  return bubble;
}

function addTypingIndicator(){
  const row = document.createElement('div');
  row.className = 'row ai';
  row.id = 'typingRow';

  const wrap = document.createElement('div');
  wrap.className = 'bubble-wrap';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  wrap.appendChild(bubble);
  row.appendChild(wrap);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function removeTypingIndicator(){
  const row = document.getElementById('typingRow');
  if(row) row.remove();
}

function showGreeting(){
  clearLog();
  addMessage('ai', 'Hi! How can I help you today?');
}

async function sendToBackend(message){
  const payload = { message };
  if(currentSessionId !== null) payload.session_id = currentSessionId;

  const res = await authFetch(API_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if(!res.ok){
    throw new Error(extractErrorDetail(data) || ('Bad response from server: ' + res.status));
  }
  return data.response;
}

async function requestImage(prompt){
  const payload = { prompt };
  if(currentSessionId !== null) payload.session_id = currentSessionId;

  const res = await authFetch(IMAGE_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if(!res.ok){
    throw new Error(extractErrorDetail(data) || ('Bad response from server: ' + res.status));
  }
  return data;
}

function setImageMode(enabled){
  imageMode = enabled;
  imageModeBtn.setAttribute('aria-pressed', String(enabled));
  input.placeholder = enabled ? 'Describe the image you want...' : 'Type your message...';
}

imageModeBtn.addEventListener('click', () => setImageMode(!imageMode));

async function handleSend(){
  const text = input.value.trim();
  if(!text || isSending) return;

  isSending = true;
  sendBtn.disabled = true;
  statusText.textContent = imageMode ? 'Generating image...' : 'Thinking...';

  addMessage('user', text);
  input.value = '';
  autoGrow();

  addTypingIndicator();

  try{
    if(imageMode){
      const { image_url } = await requestImage(text);
      removeTypingIndicator();
      addImageMessage('ai', image_url);
    } else {
      const reply = await sendToBackend(text);
      removeTypingIndicator();
      addMessage('ai', reply);
    }
    statusText.textContent = 'Online';
    if(getToken()) await loadSessions();
  }catch(err){
    removeTypingIndicator();
    addMessage('ai', err.message || 'Could not reach the server.');
    statusText.textContent = 'Connection error';
    console.error(err);
  }finally{
    isSending = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

sendBtn.addEventListener('click', handleSend);
input.addEventListener('keydown', (e) => {
  if(e.key === 'Enter' && !e.shiftKey){
    e.preventDefault();
    handleSend();
  }
});

function renderSessionList(){
  sessionListEl.innerHTML = '';
  for(const s of sessions){
    const item = document.createElement('div');
    item.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');

    const titleSpan = document.createElement('span');
    titleSpan.className = 'session-item-title';
    titleSpan.textContent = s.title;

    const renameBtn = document.createElement('button');
    renameBtn.className = 'session-item-rename';
    renameBtn.setAttribute('aria-label', 'Rename chat');
    renameBtn.textContent = '✎';
    renameBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      renameSession(s.id, s.title);
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'session-item-delete';
    deleteBtn.setAttribute('aria-label', 'Delete chat');
    deleteBtn.textContent = '×';
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteSession(s.id);
    });

    item.appendChild(titleSpan);
    item.appendChild(renameBtn);
    item.appendChild(deleteBtn);
    item.addEventListener('click', () => selectSession(s.id));
    sessionListEl.appendChild(item);
  }
}

async function loadSessions(){
  const res = await authFetch('/sessions');
  if(!res.ok) return;
  sessions = await res.json();
  renderSessionList();
}

async function selectSession(sessionId){
  if(sessionId === currentSessionId) return;
  currentSessionId = sessionId;
  renderSessionList();

  const res = await authFetch(`/sessions/${sessionId}/messages`);
  clearLog();
  if(res.ok){
    const messages = await res.json();
    if(messages.length === 0){
      addMessage('ai', 'Hi! How can I help you today?');
    } else {
      for(const m of messages){
        const role = m.role === 'user' ? 'user' : 'ai';
        if(isImageUrl(m.content)){
          addImageMessage(role, m.content);
        } else {
          addMessage(role, m.content);
        }
      }
    }
  }
}

async function createNewSession(){
  const res = await authFetch('/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });
  if(!res.ok) return;
  const session = await res.json();
  sessions.unshift(session);
  currentSessionId = session.id;
  renderSessionList();
  showGreeting();
}

async function renameSession(sessionId, currentTitle){
  const newName = window.prompt('Rename chat', currentTitle);
  if(!newName || !newName.trim() || newName === currentTitle) return;

  const res = await authFetch(`/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_session_name: newName.trim() })
  });
  if(!res.ok) return;
  const updated = await res.json();
  const idx = sessions.findIndex((s) => s.id === sessionId);
  if(idx !== -1) sessions[idx] = updated;
  renderSessionList();
}

async function deleteSession(sessionId){
  const res = await authFetch(`/sessions/${sessionId}`, { method: 'DELETE' });
  if(!res.ok) return;
  sessions = sessions.filter((s) => s.id !== sessionId);

  if(sessionId === currentSessionId){
    if(sessions.length > 0){
      currentSessionId = null;
      await selectSession(sessions[0].id);
    } else {
      await createNewSession();
    }
  } else {
    renderSessionList();
  }
}

newChatBtn.addEventListener('click', createNewSession);

function renderAuthArea(){
  if(!authArea) return;
  if(getToken()){
    authArea.innerHTML = '<button id="logoutBtn" class="btn btn-ghost">Log out</button>';
    document.getElementById('logoutBtn').addEventListener('click', logout);
  } else {
    authArea.innerHTML = '<a class="btn btn-ghost" href="/login">Log in</a><a class="btn btn-primary" href="/signup">Sign up</a>';
  }
}

async function init(){
  renderAuthArea();

  if(!getToken()){
    sidebar.hidden = true;
    showGreeting();
    return;
  }

  sidebar.hidden = false;
  await loadSessions();

  if(sessions.length === 0){
    await createNewSession();
  } else {
    await selectSession(sessions[0].id);
  }
}

init();
