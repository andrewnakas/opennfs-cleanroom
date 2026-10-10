// All sound is synthesised here with WebAudio: engine note, tyres, wind, impacts, signals and a
// small generative music loop. Nothing is sampled, so there is nothing to license.
'use strict';
var GameAudio = (function () {
  var ctx = null, master = null, sfx = null, musicBus = null;
  var eng = null, skid = null, wind = null;
  var muted = false, active = false, lastSpeed = 0, lastT = 0;
  var music = { timer: null, step: 0, next: 0 };
  try { muted = localStorage.getItem('or.mute') === '1'; } catch (e) { /* ignore */ }
  if (new URLSearchParams(location.search).has('mute')) muted = true;

  function noiseBuffer(seconds) {
    var buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate), d = buf.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return buf;
  }
  function loopNoise() {
    var n = ctx.createBufferSource();
    n.buffer = noiseBuffer(2);
    n.loop = true;
    n.start();
    return n;
  }
  function build() {
    master = ctx.createGain();
    master.gain.value = muted ? 0 : 0.9;
    var comp = ctx.createDynamicsCompressor();
    master.connect(comp); comp.connect(ctx.destination);
    sfx = ctx.createGain(); sfx.gain.value = 0; sfx.connect(master);
    musicBus = ctx.createGain(); musicBus.gain.value = 0.0; musicBus.connect(master);

    // engine: three detuned saw/square partials -> soft clip -> low-pass that opens with revs and throttle
    eng = { osc: [], gain: ctx.createGain(), filter: ctx.createBiquadFilter(), shaper: ctx.createWaveShaper() };
    var curve = new Float32Array(1024);
    for (var i = 0; i < 1024; i++) { var x = i / 512 - 1; curve[i] = Math.tanh(2.4 * x); }
    eng.shaper.curve = curve;
    eng.filter.type = 'lowpass'; eng.filter.frequency.value = 400; eng.filter.Q.value = 1.2;
    eng.gain.gain.value = 0;
    [['sawtooth', 1, 0.55], ['square', 0.5, 0.35], ['sawtooth', 2.01, 0.18]].forEach(function (p) {
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.type = p[0]; o.frequency.value = 40 * p[1]; g.gain.value = p[2];
      o.connect(g); g.connect(eng.shaper); o.start();
      eng.osc.push({ osc: o, mult: p[1] });
    });
    eng.shaper.connect(eng.filter); eng.filter.connect(eng.gain); eng.gain.connect(sfx);

    skid = { gain: ctx.createGain(), filter: ctx.createBiquadFilter() };
    skid.filter.type = 'bandpass'; skid.filter.frequency.value = 1150; skid.filter.Q.value = 5;
    skid.gain.gain.value = 0;
    var n1 = loopNoise(); n1.connect(skid.filter); skid.filter.connect(skid.gain); skid.gain.connect(sfx);

    wind = { gain: ctx.createGain(), filter: ctx.createBiquadFilter() };
    wind.filter.type = 'lowpass'; wind.filter.frequency.value = 500;
    wind.gain.gain.value = 0;
    var n2 = loopNoise(); n2.connect(wind.filter); wind.filter.connect(wind.gain); wind.gain.connect(sfx);
  }
  function unlock() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ctx = new AC();
      build();
    }
    if (ctx.state === 'suspended') ctx.resume();
  }
  function setActive(on) {
    active = on;
    if (!ctx) return;
    var t = ctx.currentTime;
    sfx.gain.setTargetAtTime(on ? 1 : 0, t, 0.08);
    musicBus.gain.setTargetAtTime(on ? 0.22 : 0.08, t, 0.3);
    if (on && !music.timer) startMusic();
  }
  function toggleMute() {
    muted = !muted;
    try { localStorage.setItem('or.mute', muted ? '1' : '0'); } catch (e) { /* ignore */ }
    if (ctx) master.gain.setTargetAtTime(muted ? 0 : 0.9, ctx.currentTime, 0.05);
    return !muted;
  }
  function update(s) {
    if (!ctx || !active) return;
    var t = ctx.currentTime;
    var f = Math.max(s.rpm, 900) / 60 * 2;                       // firing frequency of a four cylinder
    eng.osc.forEach(function (o) { o.osc.frequency.setTargetAtTime(f * o.mult, t, 0.05); });
    var load = s.thr ? 1 : 0.35;
    eng.filter.frequency.setTargetAtTime(260 + (s.rpm / 7000) * 2400 * load + (s.thr ? 500 : 0), t, 0.06);
    eng.gain.gain.setTargetAtTime(0.16 + 0.2 * load * (0.5 + s.rpm / 14000), t, 0.06);
    var slide = s.gnd > 0 ? Math.max(0, s.skid - 0.22) * Math.min(1, s.speed / 40) : 0;
    skid.gain.gain.setTargetAtTime(Math.min(0.5, slide * 0.9), t, 0.05);
    skid.filter.frequency.setTargetAtTime(950 + s.speed * 3, t, 0.1);
    var v = Math.min(1, s.speed / 260);
    wind.gain.gain.setTargetAtTime(v * v * 0.5, t, 0.2);
    wind.filter.frequency.setTargetAtTime(350 + v * 1400, t, 0.2);
    // impact: speed lost faster than the brakes could manage
    var now = performance.now(), dt = (now - lastT) / 1000;
    if (dt > 0 && dt < 0.2 && s.phase !== 0) {
      var decel = (lastSpeed - s.speed) / 3.6 / dt;                // m/s^2
      if (decel > 28) thud(Math.min(1, decel / 90));
    }
    lastSpeed = s.speed; lastT = now;
  }
  function thud(level) {
    var t = ctx.currentTime, src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    src.buffer = noiseBuffer(0.3);
    f.type = 'lowpass'; f.frequency.setValueAtTime(900, t); f.frequency.exponentialRampToValueAtTime(90, t + 0.25);
    g.gain.setValueAtTime(0.9 * level, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.28);
    src.connect(f); f.connect(g); g.connect(sfx); src.start(t);
  }
  function tone(freq, start, dur, type, level, bus) {
    var o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type || 'square'; o.frequency.value = freq;
    g.gain.setValueAtTime(0, start); g.gain.linearRampToValueAtTime(level || 0.2, start + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    o.connect(g); g.connect(bus || master); o.start(start); o.stop(start + dur + 0.05);
  }
  function beep(go) {
    if (!ctx) return;
    tone(go ? 880 : 440, ctx.currentTime, go ? 0.6 : 0.18, 'square', 0.16);
  }
  function fanfare(win) {
    if (!ctx) return;
    var t = ctx.currentTime, notes = win ? [523, 659, 784, 1047] : [392, 494, 587];
    notes.forEach(function (n, i) { tone(n, t + i * 0.14, 0.5, 'triangle', 0.2); });
  }

  // ---- music: 16-step loop over Am F C G, bass + plucked arpeggio + noise hat + kick
  var CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]];
  function hz(m) { return 440 * Math.pow(2, (m - 69) / 12); }
  function schedule() {
    var stepLen = 60 / 118 / 4;
    while (music.next < ctx.currentTime + 0.25) {
      var s = music.step, bar = Math.floor(s / 16) % 4, chord = CHORDS[bar], t = music.next;
      if (s % 4 === 0) {                                            // kick
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.setValueAtTime(130, t); o.frequency.exponentialRampToValueAtTime(42, t + 0.12);
        g.gain.setValueAtTime(0.9, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.2);
        o.connect(g); g.connect(musicBus); o.start(t); o.stop(t + 0.25);
      }
      if (s % 2 === 1) {                                            // hat
        var src = ctx.createBufferSource(), hf = ctx.createBiquadFilter(), hg = ctx.createGain();
        src.buffer = noiseBuffer(0.05); hf.type = 'highpass'; hf.frequency.value = 7000;
        hg.gain.setValueAtTime(0.18, t); hg.gain.exponentialRampToValueAtTime(0.001, t + 0.04);
        src.connect(hf); hf.connect(hg); hg.connect(musicBus); src.start(t);
      }
      if (s % 2 === 0) tone(hz(chord[0] - 24), t, stepLen * 1.8, 'sawtooth', 0.32, musicBus);   // bass
      var arp = [0, 1, 2, 1, 2, 1, 0, 2][s % 8];
      tone(hz(chord[arp] + (s % 16 >= 8 ? 12 : 0)), t, stepLen * 1.2, 'triangle', 0.22, musicBus);
      music.next += stepLen;
      music.step++;
    }
  }
  function startMusic() {
    music.next = ctx.currentTime + 0.1;
    music.timer = setInterval(function () { if (ctx.state === 'running') schedule(); }, 80);
  }

  return { unlock: unlock, setActive: setActive, toggleMute: toggleMute, update: update, beep: beep, fanfare: fanfare, isMuted: function () { return muted; } };
})();
