/**
 * waveform-controller.js — Source Explorer Waveform Module
 *
 * Responsibilities:
 *  - Create/destroy a WaveSurfer v7 instance (MediaElement backend) per panel-open
 *  - Load pre-generated peaks JSON for large-file waveform rendering
 *  - Manage ONE active draggable region via RegionsPlugin
 *  - Emit parse:playback-position, parse:playback-state, parse:region-updated
 *  - Listen for parse:panel-open, parse:panel-close, parse:seek
 *  - Keyboard shortcuts: Space, Left/Right (±1s), Shift+Left/Right (±5s)
 *  - Expose skip(±5s), jump(±30s), init(), destroy()
 *
 * Assumes wavesurfer.js v7 is loaded globally:
 *   window.WaveSurfer, window.WaveSurfer.Regions, window.WaveSurfer.Timeline
 *
 * Renders into: #parse-waveform
 * Attaches to:  window.PARSE.modules.waveform
 */
(function () {
  'use strict';

  // ─── Module state ─────────────────────────────────────────────────────────────

  /** @type {HTMLElement|null} */
  let containerEl = null;

  /** @type {WaveSurfer|null} */
  let wavesurfer = null;

  /** @type {object|null} WaveSurfer Regions plugin instance */
  let regionsPlugin = null;

  /** @type {object|null} WaveSurfer Timeline plugin instance */
  let timelinePlugin = null;

  /** @type {object|null} The single active draggable region */
  let activeRegion = null;

  /** @type {AbortController|null} Cancels in-flight peaks fetch on rapid speaker switching */
  let abortController = null;

  /** @type {string|null} Speaker ID currently loaded */
  let currentSpeaker = null;

  /** @type {boolean} Tracks whether keydown listener is attached */
  let keyboardActive = false;

  /** @type {number} Monotonic token used to fence async panel-open work */
  let currentLoadToken = 0;

  // ─── Utility ──────────────────────────────────────────────────────────────────

  /**
   * Dispatch a CustomEvent on document.
   * @param {string} name
   * @param {object} detail
   */
  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail }));
  }

  /**
   * Clamp a number between min and max.
   */
  function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
  }

  /**
   * Advance the active load token, invalidating stale async work.
   * @returns {number}
   */
  function invalidateLoadToken() {
    currentLoadToken += 1;
    return currentLoadToken;
  }

  /**
   * @param {number} loadToken
   * @returns {boolean}
   */
  function isLoadCurrent(loadToken) {
    return loadToken === currentLoadToken;
  }

  /**
   * @param {WaveSurfer|null} ws
   * @param {number} loadToken
   * @returns {boolean}
   */
  function isActiveWaveSurfer(ws, loadToken) {
    return !!ws && wavesurfer === ws && isLoadCurrent(loadToken);
  }

  /**
   * Return the filename stem (last path segment, no extension).
   * @param {string} path
   * @returns {string}
   */
  function getFileStem(path) {
    if (typeof path !== 'string' || !path) return '';
    const normalized = path.replace(/\\/g, '/');
    const basename = normalized.split('/').pop() || '';
    const dotIndex = basename.lastIndexOf('.');
    return dotIndex >= 0 ? basename.slice(0, dotIndex) : basename;
  }

  /**
   * Resolve the peaks JSON URL for the selected WAV.
   * For multi-WAV speakers we derive `peaks/<Speaker>_<stem>.json` so the
   * waveform never reuses the primary recording's peaks for a different file.
   *
   * @param {string} speaker
   * @param {object} speakerInfo
   * @param {object} wavEntry
   * @returns {string|null}
   */
  function resolvePeaksUrl(speaker, speakerInfo, wavEntry) {
    const defaultPeaksUrl = speakerInfo && typeof speakerInfo.peaks_file === 'string'
      ? speakerInfo.peaks_file
      : null;

    if (!wavEntry) return defaultPeaksUrl;

    const sourceWavs = speakerInfo && Array.isArray(speakerInfo.source_wavs)
      ? speakerInfo.source_wavs
      : [];

    if (sourceWavs.length <= 1 || wavEntry.is_primary) {
      return defaultPeaksUrl;
    }

    const stem = getFileStem(wavEntry.filename);
    if (!stem) return null;

    const lastSlash = defaultPeaksUrl ? defaultPeaksUrl.lastIndexOf('/') : -1;
    const dir = lastSlash >= 0 ? defaultPeaksUrl.slice(0, lastSlash + 1) : 'peaks/';
    return dir + speaker + '_' + stem + '.json';
  }

  /**
   * Normalize peaks payload into WaveSurfer channelData.
   * Mono payloads are passed through as `[data]`.
   * Structured multi-channel payloads are supported when `data` is already one
   * array/typed-array per channel; otherwise we refuse the payload instead of
   * silently rendering mismatched peaks.
   *
   * @param {object|null} peaksData
   * @returns {Array<Array<number>|ArrayLike<number>>|undefined}
   */
  function getChannelDataFromPeaks(peaksData) {
    if (!peaksData || peaksData.data == null) return undefined;

    const channels = Number(peaksData.channels);
    const data = peaksData.data;

    if (!Number.isFinite(channels) || channels <= 1) {
      return [data];
    }

    if (
      Array.isArray(data) &&
      data.length === channels &&
      data.every(function (channel) {
        return Array.isArray(channel) || ArrayBuffer.isView(channel);
      })
    ) {
      return data;
    }

    console.warn(
      '[waveform-controller] Unsupported multi-channel peaks payload; rendering without peaks instead of using mismatched channel data.'
    );
    return undefined;
  }

  /**
   * Returns the WaveSurfer v7 UMD plugin global, with legacy fallback names.
   * @param {'Regions'|'Timeline'} pluginName
   * @returns {object|null}
   */
  function getPluginGlobal(pluginName) {
    if (!window.WaveSurfer) return null;
    return window.WaveSurfer[pluginName]
      || window.WaveSurfer[pluginName + 'Plugin']
      || null;
  }

  /**
   * Focus the waveform container so document-level shortcuts stay scoped to the panel.
   */
  function focusWaveformContainer() {
    if (!containerEl || typeof containerEl.focus !== 'function') return;
    if (!containerEl.hasAttribute('tabindex')) {
      containerEl.tabIndex = 0;
    }
    try {
      containerEl.focus({ preventScroll: true });
    } catch (_) {
      containerEl.focus();
    }
  }

  /**
   * Return whether the given element should suppress waveform keyboard shortcuts.
   * @param {EventTarget|null} target
   * @returns {boolean}
   */
  function isInteractiveElement(target) {
    if (!(target instanceof Element)) return false;
    if (target.isContentEditable) return true;

    return !!target.closest(
      'input, textarea, select, button, a[href], summary, details,' +
      ' [contenteditable], [role="button"], [role="link"], [role="textbox"],' +
      ' [role="searchbox"], [role="spinbutton"], [role="slider"], [role="menuitem"],' +
      ' [role="option"], [role="checkbox"], [role="radio"], [role="switch"],' +
      ' [role="tab"], [role="combobox"], [role="listbox"]'
    );
  }

  /**
   * Return whether an element is inside the active Source Explorer surface.
   * @param {Element|null} el
   * @returns {boolean}
   */
  function isInShortcutScope(el) {
    if (!(el instanceof Element)) return false;

    const panel = document.getElementById('parse-panel');
    const overlay = document.getElementById('parse-fullscreen-overlay');

    return !!(
      (panel && panel.contains(el)) ||
      (overlay && overlay.contains(el))
    );
  }

  // ─── Seeking ──────────────────────────────────────────────────────────────────

  /**
   * Seek the waveform to an absolute time in seconds.
   * WaveSurfer.seekTo() requires a 0–1 fraction.
   * @param {WaveSurfer|null} ws
   * @param {number} timeSec
   */
  function seekWaveSurferToSec(ws, timeSec) {
    if (!ws) return;
    const duration = ws.getDuration();
    if (!duration || duration <= 0) return;
    ws.seekTo(clamp(timeSec / duration, 0, 1));
  }

  /**
   * Seek the active waveform to an absolute time in seconds.
   * @param {number} timeSec
   */
  function seekToSec(timeSec) {
    seekWaveSurferToSec(wavesurfer, timeSec);
  }

  // ─── Region management ────────────────────────────────────────────────────────

  /**
   * Remove the current active region from the waveform.
   */
  function clearActiveRegion() {
    if (activeRegion) {
      try {
        activeRegion.remove();
      } catch (_) { /* already removed */ }
      activeRegion = null;
      emit('parse:region-updated', { startSec: null, endSec: null });
    }
  }

  /**
   * Create (or replace) the single active region.
   * @param {number} startSec  Region start in seconds
   * @param {number} [durationSec=3.0]  Region duration in seconds
   */
  function createRegion(startSec, durationSec) {
    if (!regionsPlugin || !wavesurfer) return;

    const duration = wavesurfer.getDuration() || 0;
    if (!Number.isFinite(startSec) || startSec < 0) return;

    clearActiveRegion();

    let endSec = startSec + (durationSec != null ? durationSec : 3.0);
    if (!Number.isFinite(endSec) || endSec <= startSec) return;

    if (duration > 0) {
      startSec = clamp(startSec, 0, duration);
      endSec = clamp(endSec, 0, duration);
      if (endSec <= startSec) return;
    }

    activeRegion = regionsPlugin.addRegion({
      start: startSec,
      end: endSec,
      color: 'rgba(255, 165, 0, 0.22)',
      drag: true,
      resize: true,
    });
    emit('parse:region-updated', { startSec: activeRegion.start, endSec: activeRegion.end });
  }

  // ─── Keyboard shortcuts ───────────────────────────────────────────────────────

  /**
   * Keydown handler — active only while a waveform is loaded.
   * Space        → play/pause
   * Left/Right   → ±1 s
   * Shift+Left/R → ±5 s
   */
  function onKeyDown(e) {
    if (!wavesurfer) return;

    const target = e.target instanceof Element ? e.target : null;
    const active = document.activeElement instanceof Element ? document.activeElement : null;
    const scopeEl = target || active;

    if (!isInShortcutScope(scopeEl)) {
      return;
    }
    if (isInteractiveElement(target) || isInteractiveElement(active)) {
      return;
    }

    switch (e.key) {
      case ' ':
        e.preventDefault();
        wavesurfer.playPause();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        seekToSec(wavesurfer.getCurrentTime() - (e.shiftKey ? 5 : 1));
        break;
      case 'ArrowRight':
        e.preventDefault();
        seekToSec(wavesurfer.getCurrentTime() + (e.shiftKey ? 5 : 1));
        break;
      default:
        break;
    }
  }

  function enableKeyboardShortcuts() {
    if (!keyboardActive) {
      document.addEventListener('keydown', onKeyDown);
      keyboardActive = true;
    }
  }

  function disableKeyboardShortcuts() {
    if (keyboardActive) {
      document.removeEventListener('keydown', onKeyDown);
      keyboardActive = false;
    }
  }

  function bindContainerFocus() {
    if (!containerEl) return;
    if (!containerEl.hasAttribute('tabindex')) {
      containerEl.tabIndex = 0;
    }
    containerEl.removeEventListener('pointerdown', focusWaveformContainer);
    containerEl.addEventListener('pointerdown', focusWaveformContainer);
  }

  function unbindContainerFocus() {
    if (!containerEl) return;
    containerEl.removeEventListener('pointerdown', focusWaveformContainer);
  }

  // ─── WaveSurfer lifecycle ─────────────────────────────────────────────────────

  /**
   * Tear down the WaveSurfer instance and free all resources.
   */
  function destroyWavesurfer() {
    disableKeyboardShortcuts();
    clearActiveRegion();

    if (wavesurfer) {
      try { wavesurfer.destroy(); } catch (_) {}
      wavesurfer = null;
    }

    regionsPlugin = null;
    timelinePlugin = null;
    currentSpeaker = null;

    // Remove the timeline sub-div if it was created
    if (containerEl) {
      const timelineDiv = containerEl.querySelector('.se-waveform-timeline');
      if (timelineDiv) timelineDiv.remove();
    }
  }

  /**
   * Initialise a WaveSurfer instance, load audio + peaks, and seek to startSec.
   *
   * @param {string} audioUrl       Relative URL served by thesis_server.py
   * @param {object|null} peaksData Parsed peaks JSON (or null to render without peaks)
   * @param {number} durationSec    Total audio duration in seconds
   * @param {number} startSec       Position to seek to after load
   * @param {number} loadToken      Token fencing this async load
   */
  async function createWavesurfer(audioUrl, peaksData, durationSec, startSec, loadToken) {
    if (!isLoadCurrent(loadToken)) return;

    // Resolve container
    if (!containerEl) {
      containerEl = document.getElementById('parse-waveform');
    }
    if (!containerEl) {
      console.error('[waveform-controller] #parse-waveform container not found');
      return;
    }

    if (!window.WaveSurfer || typeof window.WaveSurfer.create !== 'function') {
      console.error('[waveform-controller] WaveSurfer v7 global is missing');
      return;
    }

    const Regions = getPluginGlobal('Regions');
    const Timeline = getPluginGlobal('Timeline');
    if (!Regions || typeof Regions.create !== 'function' || !Timeline || typeof Timeline.create !== 'function') {
      console.error('[waveform-controller] Required WaveSurfer v7 UMD plugins are missing (expected WaveSurfer.Regions and WaveSurfer.Timeline)');
      return;
    }

    // Create a dedicated sub-div for the Timeline plugin so it doesn't overlap the waveform
    let timelineDiv = containerEl.querySelector('.se-waveform-timeline');
    if (!timelineDiv) {
      timelineDiv = document.createElement('div');
      timelineDiv.className = 'se-waveform-timeline';
      containerEl.appendChild(timelineDiv);
    }

    const localRegionsPlugin = Regions.create();
    const localTimelinePlugin = Timeline.create({
      container: timelineDiv,
    });

    const ws = window.WaveSurfer.create({
      container: containerEl,
      backend: 'MediaElement',
      waveColor: '#4a9eff',
      progressColor: '#1a5fbd',
      cursorColor: '#ff6b35',
      height: 80,
      normalize: true,
      interact: true,
      plugins: [localRegionsPlugin, localTimelinePlugin],
    });

    wavesurfer = ws;
    regionsPlugin = localRegionsPlugin;
    timelinePlugin = localTimelinePlugin;

    let initialSeekDone = false;

    function applyInitialSeek() {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      if (!initialSeekDone && startSec > 0) {
        initialSeekDone = true;
        seekWaveSurferToSec(ws, startSec);
      }
    }

    // ── Wire playback events ─────────────────────────────────────────────────
    ws.on('timeupdate', function (currentTime) {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      emit('parse:playback-position', { timeSec: currentTime });
    });

    ws.on('play', function () {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      emit('parse:playback-state', { playing: true });
    });

    ws.on('pause', function () {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      emit('parse:playback-state', { playing: false });
    });

    ws.on('finish', function () {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      emit('parse:playback-state', { playing: false });
    });

    ws.on('error', function (err) {
      if (!isLoadCurrent(loadToken)) return;
      console.error('[waveform-controller] WaveSurfer error:', err);
    });

    ws.on('ready', function () {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      applyInitialSeek();
      enableKeyboardShortcuts();
      focusWaveformContainer();
    });

    // ── Wire region events ───────────────────────────────────────────────────
    localRegionsPlugin.on('region-created', function (region) {
      if (!isActiveWaveSurfer(ws, loadToken)) {
        try { region.remove(); } catch (_) {}
        return;
      }
      if (activeRegion && activeRegion !== region) {
        try { activeRegion.remove(); } catch (_) {}
      }
      activeRegion = region;
      emit('parse:region-updated', { startSec: region.start, endSec: region.end });
    });

    localRegionsPlugin.on('region-updated', function (region) {
      if (!isActiveWaveSurfer(ws, loadToken)) return;
      activeRegion = region;
      emit('parse:region-updated', { startSec: region.start, endSec: region.end });
    });

    const channelData = getChannelDataFromPeaks(peaksData);

    try {
      await ws.load(audioUrl, channelData, durationSec);

      if (!isActiveWaveSurfer(ws, loadToken)) {
        try { ws.destroy(); } catch (_) {}
        return;
      }

      applyInitialSeek();
    } catch (err) {
      if (!isLoadCurrent(loadToken)) return;
      console.error('[waveform-controller] Failed to load audio:', err);
    }
  }

  // ─── Document event handlers ──────────────────────────────────────────────────

  /**
   * parse:panel-open
   * { speaker, conceptId, sourceWav, lexiconStartSec }
   */
  async function onPanelOpen(e) {
    const detail = e && e.detail ? e.detail : {};
    const speaker = detail.speaker;
    const sourceWav = detail.sourceWav;
    const lexiconStartSec = detail.lexiconStartSec;

    const loadToken = invalidateLoadToken();
    currentSpeaker = speaker;

    const SE = window.PARSE;
    const speakerInfo = SE && SE.sourceIndex && SE.sourceIndex.speakers
      ? SE.sourceIndex.speakers[speaker]
      : null;

    if (!speakerInfo) {
      console.error('[waveform-controller] Speaker not found in sourceIndex:', speaker);
      return;
    }

    const sourceWavs = Array.isArray(speakerInfo.source_wavs) ? speakerInfo.source_wavs : [];
    const wavEntry =
      (sourceWav && sourceWavs.find(function (w) { return w.filename === sourceWav; })) ||
      sourceWavs.find(function (w) { return w.is_primary; }) ||
      sourceWavs[0];

    if (!wavEntry) {
      console.error('[waveform-controller] No source WAV entry for speaker:', speaker);
      return;
    }

    const audioUrl = wavEntry.filename;
    const durationSec = wavEntry.duration_sec;
    const peaksUrl = resolvePeaksUrl(speaker, speakerInfo, wavEntry);
    const startSec = lexiconStartSec != null
      ? lexiconStartSec
      : (wavEntry.lexicon_start_sec != null ? wavEntry.lexicon_start_sec : 0);

    if (abortController) {
      abortController.abort();
    }
    abortController = new AbortController();
    const signal = abortController.signal;

    destroyWavesurfer();

    let peaksData = null;
    if (peaksUrl) {
      try {
        const resp = await fetch(peaksUrl, { signal: signal });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        peaksData = await resp.json();
      } catch (err) {
        if (err.name === 'AbortError') {
          return;
        }
        console.warn('[waveform-controller] Peaks fetch failed (rendering without peaks):', err);
        peaksData = null;
      }
    }

    if (signal.aborted || !isLoadCurrent(loadToken)) return;

    await createWavesurfer(audioUrl, peaksData, durationSec, startSec, loadToken);
  }

  /**
   * parse:panel-close
   * { speaker }
   */
  function onPanelClose(/* e */) {
    invalidateLoadToken();
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    destroyWavesurfer();
  }

  /**
   * parse:seek
   * { timeSec, createRegion?, regionDurationSec? }
   */
  function onSeek(e) {
    const detail = e && e.detail ? e.detail : {};
    const timeSec = detail.timeSec;
    const doCreateRegion = detail.createRegion;
    const regionDurationSec = detail.regionDurationSec;

    seekToSec(timeSec);

    if (doCreateRegion) {
      createRegion(timeSec, regionDurationSec);
    }
  }

  // ─── Public navigation helpers ────────────────────────────────────────────────

  /**
   * Skip forward or backward by a small increment (intended for ±5 s buttons).
   * @param {number} deltaSec  Positive or negative seconds
   */
  function skip(deltaSec) {
    if (!wavesurfer) return;
    seekToSec(wavesurfer.getCurrentTime() + deltaSec);
  }

  /**
   * Jump forward or backward by a large increment (intended for ±30 s buttons).
   * @param {number} deltaSec  Positive or negative seconds
   */
  function jump(deltaSec) {
    if (!wavesurfer) return;
    seekToSec(wavesurfer.getCurrentTime() + deltaSec);
  }

  // ─── Init / Destroy ───────────────────────────────────────────────────────────

  /**
   * Initialise the module.
   * @param {HTMLElement} [el]  Container element. Defaults to #parse-waveform.
   * @returns {object}  Public API
   */
  function init(el) {
    containerEl = el || document.getElementById('parse-waveform');
    bindContainerFocus();

    document.addEventListener('parse:panel-open', onPanelOpen);
    document.addEventListener('parse:panel-close', onPanelClose);
    document.addEventListener('parse:seek', onSeek);

    return {
      skip: skip,
      jump: jump,
      seekToSec: seekToSec,
      playPause: function () {
        if (wavesurfer) wavesurfer.playPause();
      },
      playRegion: function () {
        if (!wavesurfer) return;
        if (activeRegion) {
          activeRegion.play();
        } else {
          wavesurfer.play();
        }
      },
      clearActiveRegion: clearActiveRegion,
      createRegion: createRegion,
      getWaveSurfer: function () { return wavesurfer; },
      getActiveRegion: function () { return activeRegion; },
      getCurrentTime: function () {
        return wavesurfer ? wavesurfer.getCurrentTime() : 0;
      },
    };
  }

  /**
   * Teardown: remove all event listeners and destroy WaveSurfer.
   */
  function destroy() {
    document.removeEventListener('parse:panel-open', onPanelOpen);
    document.removeEventListener('parse:panel-close', onPanelClose);
    document.removeEventListener('parse:seek', onSeek);

    invalidateLoadToken();
    if (abortController) {
      abortController.abort();
      abortController = null;
    }

    destroyWavesurfer();
    unbindContainerFocus();
    containerEl = null;
  }

  // ─── Register module ──────────────────────────────────────────────────────────

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};
  window.PARSE.modules.waveform = {
    init: init,
    destroy: destroy,
    skip: skip,
    jump: jump,
  };

}());
