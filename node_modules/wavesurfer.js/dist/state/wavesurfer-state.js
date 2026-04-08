/**
 * Centralized reactive state for WaveSurfer
 *
 * This module provides a single source of truth for all WaveSurfer state.
 * State is managed using reactive signals that automatically notify subscribers.
 */
import { signal, computed } from '../reactive/store.js';
/**
 * Create a new WaveSurfer state instance
 *
 * @param playerSignals - Optional signals from Player to compose with WaveSurfer state
 *
 * @example
 * ```typescript
 * // Without Player signals (standalone)
 * const { state, actions } = createWaveSurferState()
 *
 * // With Player signals (composed)
 * const { state, actions } = createWaveSurferState({
 *   isPlaying: player.isPlayingSignal,
 *   currentTime: player.currentTimeSignal,
 *   // ...
 * })
 *
 * // Read state
 * console.log(state.isPlaying.value)
 *
 * // Update state
 * actions.setPlaying(true)
 *
 * // Subscribe to changes
 * state.isPlaying.subscribe(playing => {
 *   console.log('Playing:', playing)
 * })
 * ```
 */
export function createWaveSurferState(playerSignals) {
    var _a, _b, _c, _d, _e, _f;
    // Use Player signals if provided, otherwise create new ones
    const currentTime = (_a = playerSignals === null || playerSignals === void 0 ? void 0 : playerSignals.currentTime) !== null && _a !== void 0 ? _a : signal(0);
    const duration = (_b = playerSignals === null || playerSignals === void 0 ? void 0 : playerSignals.duration) !== null && _b !== void 0 ? _b : signal(0);
    const isPlaying = (_c = playerSignals === null || playerSignals === void 0 ? void 0 : playerSignals.isPlaying) !== null && _c !== void 0 ? _c : signal(false);
    const isSeeking = (_d = playerSignals === null || playerSignals === void 0 ? void 0 : playerSignals.isSeeking) !== null && _d !== void 0 ? _d : signal(false);
    const volume = (_e = playerSignals === null || playerSignals === void 0 ? void 0 : playerSignals.volume) !== null && _e !== void 0 ? _e : signal(1);
    const playbackRate = (_f = playerSignals === null || playerSignals === void 0 ? void 0 : playerSignals.playbackRate) !== null && _f !== void 0 ? _f : signal(1);
    // WaveSurfer-specific signals (not in Player)
    const audioBuffer = signal(null);
    const peaks = signal(null);
    const url = signal('');
    const zoom = signal(0);
    const scrollPosition = signal(0);
    // Computed values (derived state)
    const isPaused = computed(() => !isPlaying.value, [isPlaying]);
    const canPlay = computed(() => audioBuffer.value !== null, [audioBuffer]);
    const isReady = computed(() => {
        return canPlay.value && duration.value > 0;
    }, [canPlay, duration]);
    const progress = computed(() => currentTime.value, [currentTime]);
    const progressPercent = computed(() => {
        return duration.value > 0 ? currentTime.value / duration.value : 0;
    }, [currentTime, duration]);
    // Public read-only state
    const state = {
        currentTime,
        duration,
        isPlaying,
        isPaused,
        isSeeking,
        volume,
        playbackRate,
        audioBuffer,
        peaks,
        url,
        zoom,
        scrollPosition,
        canPlay,
        isReady,
        progress,
        progressPercent,
    };
    // Actions that modify state
    const actions = {
        setCurrentTime: (time) => {
            const clampedTime = Math.max(0, Math.min(duration.value || Infinity, time));
            currentTime.set(clampedTime);
        },
        setDuration: (d) => {
            duration.set(Math.max(0, d));
        },
        setPlaying: (playing) => {
            isPlaying.set(playing);
        },
        setSeeking: (seeking) => {
            isSeeking.set(seeking);
        },
        setVolume: (v) => {
            const clampedVolume = Math.max(0, Math.min(1, v));
            volume.set(clampedVolume);
        },
        setPlaybackRate: (rate) => {
            const clampedRate = Math.max(0.1, Math.min(16, rate));
            playbackRate.set(clampedRate);
        },
        setAudioBuffer: (buffer) => {
            audioBuffer.set(buffer);
            if (buffer) {
                duration.set(buffer.duration);
            }
        },
        setPeaks: (p) => {
            peaks.set(p);
        },
        setUrl: (u) => {
            url.set(u);
        },
        setZoom: (z) => {
            zoom.set(Math.max(0, z));
        },
        setScrollPosition: (pos) => {
            scrollPosition.set(Math.max(0, pos));
        },
    };
    return { state, actions };
}
