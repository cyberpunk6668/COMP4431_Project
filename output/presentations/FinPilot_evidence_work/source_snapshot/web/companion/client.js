/* Local companion bridge. No model, broker, session-list or automatic chat calls. */
(() => {
  'use strict';
  const copy = value => value == null ? value : JSON.parse(JSON.stringify(value));
  async function request(path, options = {}) {
    const response = await fetch(path, {...options, headers:{'Content-Type':'application/json',...options.headers}});
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      const error = new Error(typeof detail === 'string' ? detail : detail?.message || `HTTP ${response.status}`);
      error.status = response.status; error.detail = detail; throw error;
    }
    return data;
  }
  function create(options = {}) {
    const surface = options.surface === 'desktop' ? 'desktop' : 'workspace';
    let connection = null, source = null, destroyed = false, online = false, syncSerial = 0;
    let lastEpoch = null, lastSequence = -1, syncTimer = null, connectionReadSerial = 0;
    const controllers = new Set();
    const retiredEpochs = new Set(), operationOrigins = new Map();
    const notify = (name, ...args) => { if (!destroyed) options[name]?.(...args); };
    const shouldSync = sid => Boolean(sid) && (options.shouldSync ? options.shouldSync(sid) : surface === 'desktop');
    function acceptConnection(next) {
      if (!next || typeof next !== 'object') return;
      if (retiredEpochs.has(next.epoch)) return;
      if (connection?.epoch === next.epoch && (next.seq < Math.max(connection.seq,lastEpoch===next.epoch?lastSequence:-1) || next.generation < connection.generation)) return;
      if(connection?.epoch && connection.epoch!==next.epoch)retiredEpochs.add(connection.epoch);
      if (connection?.epoch !== next.epoch || connection?.generation !== next.generation || connection?.session_id !== next.session_id) {
        syncSerial++; for (const controller of controllers) controller.abort(); controllers.clear();
      }
      connection = copy(next);
      notify('onConnection', copy(connection));
      notify('onActivity', copy(connection.activities || []), null);
    }
    async function sync() {
      clearTimeout(syncTimer);syncTimer = null;
      const sid = connection?.session_id;
      if (destroyed || !shouldSync(sid)) return null;
      const serial = ++syncSerial, generation = connection.generation, epoch = connection.epoch;
      const controller = new AbortController(); controllers.add(controller);
      try {
        const session = await request(`/api/sessions/${encodeURIComponent(sid)}`, {signal:controller.signal});
        if (destroyed || serial !== syncSerial || connection?.epoch !== epoch || connection?.generation !== generation || connection?.session_id !== sid || !shouldSync(sid)) return null;
        notify('onSession', session); return session;
      } catch (error) {
        if (error.name !== 'AbortError' && !destroyed && serial === syncSerial) notify('onStatus', {connected:online,error:error.message});
        return null;
      } finally { controllers.delete(controller); }
    }
    function queueSync() {
      clearTimeout(syncTimer);
      syncTimer = setTimeout(() => { syncTimer = null; sync(); }, 25);
    }
    async function readConnection() {
      const serial = ++connectionReadSerial;
      const next = await request('/api/companion/connection');
      if (!destroyed && serial === connectionReadSerial) acceptConnection(next);
      return next;
    }
    function eventReceived(event) {
      let envelope;
      try { envelope = JSON.parse(event.data); } catch { return; }
      if (!envelope || typeof envelope.epoch !== 'string' || !Number.isInteger(envelope.seq)) return;
      if (retiredEpochs.has(envelope.epoch)) return;
      if (envelope.epoch !== lastEpoch) { lastEpoch = envelope.epoch; lastSequence = -1; }
      if (envelope.seq < lastSequence) return;
      lastSequence = envelope.seq;
      const type = envelope.type || event.type;
      if (type === 'reset' || type === 'connection.changed') {
        if (envelope.payload?.connection) { connectionReadSerial++; acceptConnection(envelope.payload.connection); }
        else { readConnection().then(queueSync).catch(error => notify('onStatus',{connected:online,error:error.message})); return; }
        queueSync(); return;
      }
      if (!connection || envelope.epoch !== connection.epoch || envelope.generation !== connection.generation || envelope.session_id !== connection.session_id) return;
      connection.seq=Math.max(connection.seq,envelope.seq);
      if (type === 'activity') {
        if (Array.isArray(envelope.payload?.activities)) connection.activities = copy(envelope.payload.activities);
        else if (Array.isArray(envelope.payload?.connection?.activities)) connection.activities = copy(envelope.payload.connection.activities);
        notify('onActivity', copy(connection.activities || []), envelope); return;
      }
      if (['session.changed','analysis.changed','session.deleted'].includes(type)) {
        syncSerial++;for(const controller of controllers)controller.abort();controllers.clear();queueSync();
      }
    }
    function openEvents() {
      if (destroyed) return;
      source = new EventSource(`/api/companion/events?surface=${surface}`);
      for (const name of ['reset','connection.changed','activity','session.changed','analysis.changed','session.deleted']) source.addEventListener(name,eventReceived);
      source.onopen = () => {
        online = true; notify('onStatus',{connected:true,error:null});
        // Reconnection always reconciles the explicit binding, never scans chats.
        readConnection().then(queueSync).catch(error => notify('onStatus',{connected:true,error:error.message}));
      };
      source.onerror = () => { online = false; notify('onStatus',{connected:false,error:'connection_lost'}); };
    }
    const ready = readConnection().then(() => { openEvents(); queueSync(); return copy(connection); }).catch(error => {
      notify('onStatus',{connected:false,error:error.message}); openEvents(); return null;
    });
    async function connect(sessionId, preferences = {}) {
      const next = await request('/api/companion/connection',{method:'PUT',body:JSON.stringify({session_id:sessionId,...preferences})});
      if (!destroyed) { acceptConnection(next); await sync(); }
      return copy(next);
    }
    return {
      ready, getConnection:() => copy(connection),
      connect,
      async setPreferences(preferences) {
        if (!connection) await ready;
        return connect(connection?.session_id || null,{...preferences,expected_generation:connection?.generation});
      },
      disconnect:() => connect(null), sync,
      async publishActivity({operationId,kind,status,sessionId,phase} = {}) {
        const current = connection;
        if(status==='started'&&!operationOrigins.has(operationId))operationOrigins.set(operationId,{epoch:current?.epoch,generation:current?.generation,sessionId,accepted:Boolean(current?.session_id&&current.session_id===sessionId)});
        const origin=operationOrigins.get(operationId);
        if(status!=='started')operationOrigins.delete(operationId);
        if (destroyed || !origin?.accepted || !current?.session_id || current.session_id !== sessionId || origin.sessionId!==sessionId || origin.epoch!==current.epoch || origin.generation!==current.generation) return null;
        const data = {operation_id:operationId,kind,status,session_id:sessionId,generation:origin.generation};
        if (phase) data.phase = phase;
        try { return await request('/api/companion/activity',{method:'POST',body:JSON.stringify(data)}); }
        catch (error) { if (![404,409].includes(error.status)) notify('onStatus',{connected:online,error:error.message}); return null; }
      },
      getStatus:() => ({surface,connected:online,destroyed,epoch:connection?.epoch || null,generation:connection?.generation ?? null}),
      destroy() {
        if (destroyed) return;
        destroyed = true; syncSerial++; source?.close(); clearTimeout(syncTimer);
        for (const controller of controllers) controller.abort(); controllers.clear();
        operationOrigins.clear();retiredEpochs.clear();
      },
    };
  }
  window.FinPilotCompanionClient = Object.freeze({create,version:'15.0.0'});
})();
