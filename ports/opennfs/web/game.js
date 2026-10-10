// Page glue: menu, loader, input injection (touch, tests), HUD, results.
// Dev hooks: ?autostart ?dump=5,10 ?keys=2:accel:6,4:left:1 ?hb=1 ?car=wdg1 ?colour=2 ?opponents=3 ?laps=2 ?debug=1 ?mute=1
'use strict';
var Q = new URLSearchParams(location.search);
var $ = function (id) { return document.getElementById(id); };
var BIT = { accel: 1, brake: 2, left: 4, right: 8, hand: 16, reset: 32, lights: 64, camera: 128, pause: 256, up: 512, down: 1024 };
var held = {};          // source name -> mask
var game = { loaded: false, ready: false, state: null, t0: 0, menuOpen: true, lastPhase: -1, lastCount: 9, finishedShown: false };
var choice = {
  track: Q.get('track') || localStorage.getItem('or.track') || '',
  car: Q.get('car') || localStorage.getItem('or.car') || 'cgt1',
  colour: +(Q.get('colour') || localStorage.getItem('or.colour') || 0),
  opponents: +(Q.get('opponents') || localStorage.getItem('or.opponents') || 3),
  laps: +(Q.get('laps') || localStorage.getItem('or.laps') || 3)
};
var catalogue = { cars: [], colours: [], tracks: [] };

// ---------------------------------------------------------------- input
function pushInput() {
  var mask = 0;
  for (var k in held) mask |= held[k];
  if (game.menuOpen) mask = 0;
  if (window.Module && Module._web_set_input) Module._web_set_input(mask, 0);
}
function hold(source, bit, on) {
  held[source] = on ? ((held[source] || 0) | bit) : ((held[source] || 0) & ~bit);
  pushInput();
}
function setupTouch() {
  var touchUi = $('touch');
  document.querySelectorAll('.tbtn').forEach(function (btn) {
    var bit = BIT[btn.dataset.bit];
    function down(e) { e.preventDefault(); btn.classList.add('on'); hold('touch-' + btn.id, bit, true); }
    function up(e) { e.preventDefault(); btn.classList.remove('on'); hold('touch-' + btn.id, bit, false); }
    btn.addEventListener('pointerdown', function (e) { btn.setPointerCapture(e.pointerId); down(e); });
    btn.addEventListener('pointerup', up);
    btn.addEventListener('pointercancel', up);
    btn.addEventListener('lostpointercapture', up);
  });
  function enable() { touchUi.classList.remove('hidden'); $('stage').classList.add('touch-on'); }
  if (matchMedia('(pointer: coarse)').matches || Q.has('touch')) enable();
  window.addEventListener('touchstart', enable, { once: true, passive: true });
}

// ---------------------------------------------------------------- menu
function buildChoices(id, items, current, render, onPick) {
  var box = $(id);
  box.textContent = '';
  items.forEach(function (item, i) {
    var b = document.createElement('button');
    b.className = 'choice' + (item.value === current ? ' sel' : '');
    render(b, item, i);
    b.addEventListener('click', function () {
      box.querySelectorAll('.choice').forEach(function (n) { n.classList.remove('sel'); });
      b.classList.add('sel');
      onPick(item.value);
    });
    box.appendChild(b);
  });
}
function buildMenu() {
  buildChoices('tracks', catalogue.tracks.map(function (t) { return { value: t.id, track: t }; }), choice.track, function (b, item) {
    var title = document.createElement('b'); title.textContent = item.track.name; b.appendChild(title);
    var sub = document.createElement('small');
    sub.textContent = (item.track.length_m ? (item.track.length_m / 1000).toFixed(1) + ' km. ' : '') + (item.track.blurb || '');
    b.appendChild(sub);
  }, function (v) { choice.track = v; });
  buildChoices('cars', catalogue.cars.map(function (c) { return { value: c.id, car: c }; }), choice.car, function (b, item) {
    var c = item.car, s = c.stats;
    var title = document.createElement('b'); title.textContent = c.name; b.appendChild(title);
    var sub = document.createElement('small'); sub.textContent = c.top + ' km/h, ' + c.mass + ' kg'; b.appendChild(sub);
    var bars = document.createElement('div'); bars.className = 'bars';
    [['speed', s.speed], ['accel', s.accel], ['grip', s.handling]].forEach(function (row) {
      var l = document.createElement('span'); l.textContent = row[0];
      var bar = document.createElement('i'); var fill = document.createElement('u'); fill.style.width = (row[1] * 5) + '%'; bar.appendChild(fill);
      bars.appendChild(l); bars.appendChild(bar);
    });
    b.appendChild(bars);
  }, function (v) { choice.car = v; });
  buildChoices('colours', catalogue.colours.map(function (c, i) { return { value: i, colour: c }; }), choice.colour, function (b, item) {
    b.classList.add('swatch'); b.style.background = item.colour.rgb; b.title = item.colour.name; b.setAttribute('aria-label', item.colour.name);
  }, function (v) { choice.colour = v; });
  buildChoices('opponents', [0, 1, 3, 5, 7].map(function (n) { return { value: n }; }), choice.opponents, function (b, item) {
    b.textContent = item.value === 0 ? 'Solo' : String(item.value);
  }, function (v) { choice.opponents = v; });
  buildChoices('laps', [1, 2, 3, 5].map(function (n) { return { value: n }; }), choice.laps, function (b, item) { b.textContent = String(item.value); },
    function (v) { choice.laps = v; });
}
function saveChoice() {
  try {
    localStorage.setItem('or.track', choice.track);
    localStorage.setItem('or.car', choice.car); localStorage.setItem('or.colour', choice.colour);
    localStorage.setItem('or.opponents', choice.opponents); localStorage.setItem('or.laps', choice.laps);
  } catch (e) { /* private mode */ }
}
function setPaused(p) {
  if (window.Module && Module._web_set_flag) Module._web_set_flag(1, p ? 1 : 0);
}
function openMenu() {
  if (!game.loaded) return;
  game.menuOpen = true;
  $('menu').classList.remove('hidden');
  $('resume').classList.remove('hidden');
  $('results').classList.add('hidden');
  setPaused(true);
  pushInput();
  if (window.GameAudio) GameAudio.setActive(false);
}
function closeMenu() {
  game.menuOpen = false;
  $('menu').classList.add('hidden');
  setPaused(false);
  pushInput();
  if (window.GameAudio) GameAudio.setActive(true);
  Module.canvas.focus();
}
function startRace() {
  saveChoice();
  if (window.GameAudio) GameAudio.unlock();
  if (!game.loaded) { boot(); return; }
  game.finishedShown = false;
  $('results').classList.add('hidden');
  $('banner').classList.add('hidden');
  // tracks are downloaded the first time they are raced
  $('go').disabled = true;
  ensureTrack(choice.track).then(function () {
    $('go').disabled = false;
    $('loading').classList.add('hidden');
    Module.ccall('web_race', null, ['string', 'number', 'number', 'number', 'string'],
      [choice.car, choice.colour, choice.opponents, choice.laps, choice.track]);
    closeMenu();
  }).catch(function (e) { $('go').disabled = false; showError(String(e)); });
}

// ---------------------------------------------------------------- track packs
var TRACK_DIR = '/game/resources/NFS_3/gamedata/tracks/';
var trackPacks = {};   // id -> Promise of the unpacked file list
function fetchTrack(id) {
  if (!trackPacks[id]) {
    $('loading').classList.remove('hidden');
    trackPacks[id] = fetchPackage('tracks/' + id + '.bin').then(function (buffer) {
      // container: "ORPK", u32 count, then per file: u16 name length, name, u32 size, bytes
      var view = new DataView(buffer), bytes = new Uint8Array(buffer), pos = 8, files = [];
      if (String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]) !== 'ORPK') throw new Error('bad track pack ' + id);
      for (var n = view.getUint32(4, true); n > 0; n--) {
        var len = view.getUint16(pos, true); pos += 2;
        var name = new TextDecoder().decode(bytes.subarray(pos, pos + len)); pos += len;
        var size = view.getUint32(pos, true); pos += 4;
        files.push({ name: name, data: bytes.subarray(pos, pos + size) }); pos += size;
      }
      return files;
    });
    trackPacks[id].catch(function () { delete trackPacks[id]; });
  }
  return trackPacks[id];
}
function writeTrack(id, files) {
  var FS = Module.FS;
  FS.mkdirTree(TRACK_DIR + id);
  files.forEach(function (f) { FS.writeFile(TRACK_DIR + id + '/' + f.name, f.data); });
}
var tracksOnDisk = {};
function ensureTrack(id) {
  if (tracksOnDisk[id]) return Promise.resolve();
  return fetchTrack(id).then(function (files) { writeTrack(id, files); tracksOnDisk[id] = true; });
}

// ---------------------------------------------------------------- HUD
function fmt(t) {
  if (!(t > 0)) return '-:--.--';
  var m = Math.floor(t / 60), s = t - m * 60;
  return m + ':' + (s < 10 ? '0' : '') + s.toFixed(2);
}
function showBanner(text, ms) {
  var b = $('banner');
  b.textContent = text;
  b.classList.remove('hidden');
  clearTimeout(showBanner.timer);
  if (ms) showBanner.timer = setTimeout(function () { b.classList.add('hidden'); }, ms);
}
function onState(s) {
  $('pos').textContent = s.pos; $('pos-of').textContent = '/' + s.n;
  $('lap').textContent = s.lap; $('lap-of').textContent = '/' + s.laps;
  $('time').textContent = s.phase === 0 ? '0:00.00' : fmt(s.finish > 0 ? s.finish : s.time).replace('-:--.--', '0:00.00');
  $('laptime').textContent = s.phase === 0 ? '0:00.00' : fmt(s.lapTime).replace('-:--.--', '0:00.00');
  $('best').textContent = fmt(s.best);
  $('speed').textContent = Math.round(s.speed);
  $('gear').textContent = s.gear === 0 ? 'R' : (s.speed < 1 && !s.thr ? 'N' : s.gear);
  $('rev-fill').style.width = Math.max(0, Math.min(100, (s.rpm - 900) / 61)).toFixed(0) + '%';
  $('hud-pos').classList.toggle('hidden', s.n < 2);
  $('notice').classList.toggle('hidden', !s.wrong);
  if (s.wrong) $('notice').textContent = 'WRONG WAY';

  if (s.phase === 0) {
    var c = Math.ceil(s.count - 0.5);
    if (c !== game.lastCount && c >= 1 && c <= 3) { showBanner(String(c)); if (window.GameAudio) GameAudio.beep(false); }
    game.lastCount = c;
  } else if (game.lastPhase === 0) {
    showBanner('GO!', 900);
    if (window.GameAudio) GameAudio.beep(true);
    game.lastCount = 9;
  }
  if (s.phase === 2 && !game.finishedShown) {
    game.finishedShown = true;
    showBanner(s.n > 1 ? ['1ST', '2ND', '3RD'][s.pos - 1] || (s.pos + 'TH') : 'FINISH', 2600);
    if (window.GameAudio) GameAudio.fanfare(s.pos === 1);
    setTimeout(function () { showResults(); }, 2800);
  }
  if (s.phase === 2 && !$('results').classList.contains('hidden')) fillResults(s);
  game.lastPhase = s.phase;
  if (window.GameAudio) GameAudio.update(s);
}
function fillResults(s) {
  var t = $('results-table');
  t.textContent = '';
  s.results.forEach(function (r, i) {
    var tr = document.createElement('tr');
    if (r.me) tr.className = 'me';
    [[String(i + 1), 'num'], [r.name, ''], [r.t > 0 ? fmt(r.t) : 'racing', 'num'], [r.best > 0 ? 'best ' + fmt(r.best) : '', 'num']].forEach(function (cell) {
      var td = document.createElement('td'); td.textContent = cell[0]; td.className = cell[1]; tr.appendChild(td);
    });
    t.appendChild(tr);
  });
}
function showResults() {
  if (!game.state || game.state.phase !== 2 || game.menuOpen) return;
  fillResults(game.state);
  $('results').classList.remove('hidden');
}

// ---------------------------------------------------------------- engine module
var Module = {
  canvas: $('canvas'),
  arguments: [],
  print: function (t) { console.log(t); },
  printErr: function (t) { console.log(t); if (/^FATAL|Aborted\(|Assertion/.test(t)) showError(t); },
  setStatus: function (t) {
    var m = /\((\d+(?:\.\d+)?)\/(\d+)\)/.exec(t || '');
    if (m) document.querySelector('#bar i').style.width = (100 * m[1] / m[2]).toFixed(1) + '%';
    $('status').textContent = (t || 'Building the track').replace(/\s*\(.*\)/, '');
  },
  onRuntimeInitialized: function () {
    // before main(): race options that are not command line arguments
    Module._web_preset(choice.colour, choice.laps);
    if (Q.has('debug')) Module._web_set_flag(0, 1);
    if (Q.has('glcheck')) Module.glCheckVerbose = true;
    if (Q.has('ff')) Module._web_set_flag(2, +Q.get('ff'));          // test fast-forward
    if (Q.has('noshadow')) Module._web_set_flag(3, 0);
    if (Q.has('autopilot')) Module._web_set_flag(4, 1);
    if (Q.has('startvr')) Module._web_set_flag(5, +Q.get('startvr'));
  },
  onGameReady: function () {
    game.ready = true;
    $('loading').classList.add('hidden');
    $('hud').classList.remove('hidden');
    $('topbar').classList.remove('hidden');
    console.log('GAME READY ' + Math.round(performance.now() - game.t0) + ' ms');
    if (Q.has('grow')) {   // dev: does the wasm memory grow when asked for a big block?
      try { var block = Module._malloc(+Q.get('grow') << 20); console.log('GROW ok ptr=' + block + ' memory=' + (Module.HEAP8 ? Module.HEAP8.length : -1)); }
      catch (e) { console.log('GROW failed: ' + e); }
    }
    pushInput();
  },
  onGameState: function (json) {
    try { game.state = JSON.parse(json); } catch (e) { return; }
    onState(game.state);
    watchPerformance();
  },
  onGameFatal: function (what) { showError('The game stopped: ' + what); },
  onAbort: function (what) { showError('The game stopped: ' + what); }
};
// Slow device? The engine reports its state every second frame: if that drops under ~24 frames a second for a while,
// switch the shadow maps off (the single most expensive part of the frame).
var perf = { count: 0, since: 0, slow: 0, shadows: !Q.has('noshadow') };
function watchPerformance() {
  if (!perf.shadows || game.menuOpen || Q.has('ff')) { perf.count = 0; perf.since = 0; return; }
  var now = performance.now();
  if (!perf.since) { perf.since = now; perf.count = 0; return; }
  perf.count++;
  if (now - perf.since < 3000) return;
  var fps = perf.count * 2 * 1000 / (now - perf.since);
  perf.since = now; perf.count = 0;
  perf.slow = fps < 24 ? perf.slow + 1 : 0;
  if (perf.slow >= 2) {
    perf.shadows = false;
    Module._web_set_flag(3, 0);
    console.log('PERF shadows off at ' + fps.toFixed(0) + ' fps');
  }
}
function showError(t) {
  $('loading').classList.remove('hidden');
  $('status').textContent = 'Something went wrong';
  $('err').textContent = ($('err').textContent + '\n' + t).slice(-1500);
}
window.addEventListener('error', function (e) { console.log('JSERROR ' + e.message + ' @' + e.filename + ':' + e.lineno); });

function loadScript(src) {
  return new Promise(function (ok, bad) {
    var s = document.createElement('script');
    s.src = src; s.onload = ok; s.onerror = function () { bad(new Error('failed to load ' + src)); };
    document.body.appendChild(s);
  });
}

// The asset pack is shipped gzip-compressed (static hosts do not compress unknown binary types)
function fetchPackage(url) {
  if (typeof DecompressionStream === 'undefined') return Promise.reject(new Error('This browser is too old (no DecompressionStream).'));
  return fetch(url).then(function (r) {
    if (!r.ok) throw new Error('failed to load ' + url + ' (' + r.status + ')');
    var total = +r.headers.get('Content-Length') || 0, got = 0;
    var counted = r.body.pipeThrough(new TransformStream({
      transform: function (chunk, controller) {
        got += chunk.length;
        if (total) document.querySelector('#bar i').style.width = Math.min(100, 100 * got / total).toFixed(1) + '%';
        $('status').textContent = 'Downloading ' + (got / 1048576).toFixed(1) + ' MB';
        controller.enqueue(chunk);
      }
    }));
    return new Response(counted.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  });
}

function devHooks(t0) {
  if (Q.has('hb')) setInterval(function () { console.log('hb ' + Math.round(performance.now() - t0) + ' ' + JSON.stringify(game.state)); }, 1000);
  var dumps = (Q.get('dump') || '').split(',').filter(Boolean).map(Number);
  dumps.forEach(function (s, k) {
    setTimeout(function () {
      var done = false;
      function dump() {
        if (done) return; done = true;
        var url = Module.canvas.toDataURL('image/png');
        for (var i = 0; i < url.length; i += 4000) console.log('PW64PNG:' + k + ':' + url.slice(i, i + 4000));
        console.log('PW64PNG:' + k + ':END');
      }
      requestAnimationFrame(dump);
      setTimeout(dump, 300);
    }, s * 1000);
  });
  // ?switch=20:trk101:hat1 starts another race (track, optional car) after 20 s: tests in-session reloads
  (Q.get('switch') || '').split(',').filter(Boolean).forEach(function (e) {
    var p = e.split(':');
    setTimeout(function () { choice.track = p[1]; if (p[2]) choice.car = p[2]; startRace(); }, +p[0] * 1000);
  });
  // ?keys=t:name:duration,... with names from BIT (accel, brake, left, right, hand, reset, camera, ...)
  (Q.get('keys') || '').split(',').filter(Boolean).forEach(function (e, i) {
    var p = e.split(':'), t = +p[0], bit = BIT[p[1]] || 0, d = +(p[2] || 0.15);
    setTimeout(function () { hold('test' + i, bit, true); }, t * 1000);
    setTimeout(function () { hold('test' + i, bit, false); }, (t + d) * 1000);
  });
}

function boot() {
  game.loaded = true;
  game.menuOpen = false;
  $('menu').classList.add('hidden');
  $('loading').classList.remove('hidden');
  game.t0 = performance.now();
  Module.arguments = ['--car', choice.car, '--track', choice.track, '--nracers', String(choice.opponents)];
  if (Q.has('dump')) {   // keep frames readable for toDataURL
    var gc = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (t, o) { o = o || {}; o.preserveDrawingBuffer = true; return gc.call(this, t, o); };
  }
  devHooks(game.t0);
  var firstTrack = choice.track;
  Promise.all([fetchPackage('assets.bin'), fetchTrack(firstTrack)]).then(function (got) {
    // hand the unpacked data to emscripten's file packager instead of letting it download assets.data
    Module.getPreloadedPackage = function () { return got[0]; };
    Module.preRun = Module.preRun || [];
    Module.preRun.push(function () { writeTrack(firstTrack, got[1]); tracksOnDisk[firstTrack] = true; });
    return loadScript('assets.js');
  }).then(function () { return loadScript('opennfs.js'); }).catch(function (e) { showError(String(e)); });
  if (window.GameAudio) GameAudio.setActive(true);
  Module.canvas.focus();
}

// ---------------------------------------------------------------- wiring
$('go').addEventListener('click', startRace);
$('resume').addEventListener('click', closeMenu);
$('again').addEventListener('click', startRace);
$('to-menu').addEventListener('click', openMenu);
$('btn-menu').addEventListener('click', openMenu);
$('btn-full').addEventListener('click', function () {
  if (document.fullscreenElement) document.exitFullscreen(); else if ($('stage').requestFullscreen) $('stage').requestFullscreen();
});
$('btn-sound').addEventListener('click', toggleSound);
function toggleSound() {
  if (!window.GameAudio) return;
  var on = GameAudio.toggleMute();
  $('btn-sound').classList.toggle('off', !on);
}
window.addEventListener('keydown', function (e) {
  if (e.code === 'Escape' && game.ready) { if (game.menuOpen) closeMenu(); else openMenu(); }
  if (e.code === 'KeyM') toggleSound();
  if (e.code === 'Enter' && game.ready && game.state && game.state.phase === 2 && !game.menuOpen) startRace();
  // keep arrow keys and space from scrolling or re-clicking focused buttons while racing
  if (!game.menuOpen && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].indexOf(e.code) >= 0) e.preventDefault();
});
document.addEventListener('visibilitychange', function () { if (document.hidden && game.ready && !game.menuOpen) openMenu(); });
setupTouch();

fetch('cars.json').then(function (r) { return r.json(); }).then(function (data) {
  catalogue = data;
  if (!catalogue.cars.some(function (c) { return c.id === choice.car; })) choice.car = catalogue.cars[0].id;
  if (!catalogue.tracks.some(function (t) { return t.id === choice.track; })) choice.track = catalogue.tracks[0].id;
  buildMenu();
}).catch(function () { /* menu falls back to defaults */ }).then(function () {
  if (Q.has('autostart') || Q.has('dump')) startRace();
});

// a trap inside the engine: tell the player, and print the stack for bug reports
window.addEventListener('unhandledrejection', function (e) { showError('The game stopped unexpectedly. Reload the page to try again.'); console.log('REJECT ' + String(e.reason && e.reason.stack ? e.reason.stack : e.reason).split(String.fromCharCode(10)).join(' | ')); });
