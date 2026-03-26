(function () {
  'use strict';

  window.PARSE = window.PARSE || {};
  window.PARSE.modules = window.PARSE.modules || {};

  const P = window.PARSE;

  const END_EPSILON_SEC = 0.03;
  const FRAGMENT_DURATION_TOLERANCE_SEC = 0.35;

  const state = {
    initialized: false,
    playback: null,
    onAudioPlayEvent: null,
  };

  function dispatch(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  function normalizeTime(value, fallback) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return num;
  }

  function withMediaFragment(sourceWav, startSec, endSec) {
    const separator = sourceWav.indexOf('#') === -1 ? '#t=' : '&t=';
    return sourceWav + separator + startSec.toFixed(3) + ',' + endSec.toFixed(3);
  }

  function stopPlayback(emitDone) {
    if (!state.playback) {
      return;
    }

    const playback = state.playback;
    state.playback = null;

    playback.completed = true;

    playback.audio.removeEventListener('loadedmetadata', playback.handlers.loadedMetadata);
    playback.audio.removeEventListener('timeupdate', playback.handlers.timeUpdate);
    playback.audio.removeEventListener('ended', playback.handlers.ended);
    playback.audio.removeEventListener('error', playback.handlers.error);

    try {
      playback.audio.pause();
    } catch (_) {
      // Ignore pause errors.
    }

    playback.audio.src = '';
    playback.audio.load();

    if (emitDone) {
      dispatch('parse:audio-done', {
        sourceWav: playback.sourceWav,
        speaker: playback.speaker,
        conceptId: playback.conceptId,
      });
    }
  }

  function createPlayback(sourceWav, startSec, endSec, speaker, conceptId) {
    const audio = new Audio();
    const regionDuration = Math.max(0.001, endSec - startSec);
    const playback = {
      audio: audio,
      sourceWav: sourceWav,
      startSec: startSec,
      endSec: endSec,
      speaker: speaker,
      conceptId: conceptId,
      mode: 'fragment',
      completed: false,
      handlers: {
        loadedMetadata: null,
        timeUpdate: null,
        ended: null,
        error: null,
      },
      stopAtSec: endSec,
      regionDuration: regionDuration,
    };

    playback.handlers.loadedMetadata = function () {
      if (playback.completed || state.playback !== playback) {
        return;
      }

      const mediaDuration = normalizeTime(playback.audio.duration, NaN);
      const fragmentLikelySupported = Number.isFinite(mediaDuration) &&
        Math.abs(mediaDuration - playback.regionDuration) <= FRAGMENT_DURATION_TOLERANCE_SEC;

      if (fragmentLikelySupported) {
        playback.mode = 'fragment';
        playback.stopAtSec = Math.max(0.001, playback.regionDuration - END_EPSILON_SEC);
      } else {
        playback.mode = 'manual';
        playback.stopAtSec = playback.endSec - END_EPSILON_SEC;
        try {
          playback.audio.currentTime = playback.startSec;
        } catch (_) {
          // Some browsers throw if seek is not yet ready.
        }
      }

      const playPromise = playback.audio.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(function (error) {
          if (!playback.completed && state.playback === playback) {
            console.warn('[audio-player] Playback failed:', error);
            stopPlayback(false);
          }
        });
      }
    };

    playback.handlers.timeUpdate = function () {
      if (playback.completed || state.playback !== playback) {
        return;
      }

      const currentTime = normalizeTime(playback.audio.currentTime, 0);
      const shouldStop = playback.mode === 'fragment'
        ? currentTime >= playback.stopAtSec
        : currentTime >= playback.stopAtSec;

      if (shouldStop) {
        stopPlayback(true);
      }
    };

    playback.handlers.ended = function () {
      if (playback.completed || state.playback !== playback) {
        return;
      }

      stopPlayback(true);
    };

    playback.handlers.error = function () {
      if (playback.completed || state.playback !== playback) {
        return;
      }

      console.warn('[audio-player] Audio element emitted an error event.');
      stopPlayback(false);
    };

    audio.preload = 'auto';
    audio.src = withMediaFragment(sourceWav, startSec, endSec);

    audio.addEventListener('loadedmetadata', playback.handlers.loadedMetadata);
    audio.addEventListener('timeupdate', playback.handlers.timeUpdate);
    audio.addEventListener('ended', playback.handlers.ended);
    audio.addEventListener('error', playback.handlers.error);

    return playback;
  }

  function playInternal(sourceWav, startSec, endSec, speaker, conceptId) {
    if (!sourceWav || typeof sourceWav !== 'string') {
      return Promise.reject(new Error('sourceWav must be a non-empty string.'));
    }

    const safeStartSec = normalizeTime(startSec, NaN);
    const safeEndSec = normalizeTime(endSec, NaN);

    if (!Number.isFinite(safeStartSec) || !Number.isFinite(safeEndSec)) {
      return Promise.reject(new Error('startSec and endSec must be finite numbers.'));
    }

    if (safeEndSec <= safeStartSec) {
      return Promise.reject(new Error('endSec must be greater than startSec.'));
    }

    stopPlayback(false);

    const playback = createPlayback(
      sourceWav,
      safeStartSec,
      safeEndSec,
      speaker == null ? undefined : speaker,
      conceptId == null ? undefined : conceptId
    );
    state.playback = playback;

    playback.audio.load();
    return Promise.resolve();
  }

  function handleAudioPlayEvent(event) {
    const detail = event && event.detail ? event.detail : {};
    playInternal(
      detail.sourceWav,
      detail.startSec,
      detail.endSec,
      detail.speaker,
      detail.conceptId
    ).catch(function (error) {
      console.warn('[audio-player] Failed to handle parse:audio-play event:', error);
    });
  }

  /**
   * Initialize the shared audio player module.
   * @returns {object} Public audio player API.
   */
  function init() {
    if (state.initialized) {
      return P.modules.audioPlayer;
    }

    state.onAudioPlayEvent = handleAudioPlayEvent;
    document.addEventListener('parse:audio-play', state.onAudioPlayEvent);
    state.initialized = true;
    return P.modules.audioPlayer;
  }

  /**
   * Destroy the module and detach all listeners.
   */
  function destroy() {
    if (state.onAudioPlayEvent) {
      document.removeEventListener('parse:audio-play', state.onAudioPlayEvent);
      state.onAudioPlayEvent = null;
    }

    stopPlayback(false);
    state.initialized = false;
  }

  /**
   * Play a region in a WAV source file.
   * @param {string} sourceWav Source WAV URL or path.
   * @param {number} startSec Region start in seconds.
   * @param {number} endSec Region end in seconds.
   * @returns {Promise<void>} Resolves once playback has been scheduled.
   */
  function play(sourceWav, startSec, endSec) {
    return playInternal(sourceWav, startSec, endSec, undefined, undefined);
  }

  /**
   * Stop currently playing audio.
   */
  function stop() {
    stopPlayback(false);
  }

  /**
   * Check if an audio region is currently playing.
   * @returns {boolean} True while a playback session is active.
   */
  function isPlaying() {
    return !!state.playback;
  }

  P.modules.audioPlayer = {
    init: init,
    destroy: destroy,
    play: play,
    stop: stop,
    isPlaying: isPlaying,
  };
}());
