/**
 * Centralized reactive state for WaveSurfer
 *
 * This module provides a single source of truth for all WaveSurfer state.
 * State is managed using reactive signals that automatically notify subscribers.
 */
import { type Signal, type WritableSignal } from '../reactive/store.js';
/**
 * Read-only reactive state for WaveSurfer
 */
export interface WaveSurferState {
    readonly currentTime: Signal<number>;
    readonly duration: Signal<number>;
    readonly isPlaying: Signal<boolean>;
    readonly isPaused: Signal<boolean>;
    readonly isSeeking: Signal<boolean>;
    readonly volume: Signal<number>;
    readonly playbackRate: Signal<number>;
    readonly audioBuffer: Signal<AudioBuffer | null>;
    readonly peaks: Signal<Array<Float32Array | number[]> | null>;
    readonly url: Signal<string>;
    readonly zoom: Signal<number>;
    readonly scrollPosition: Signal<number>;
    readonly canPlay: Signal<boolean>;
    readonly isReady: Signal<boolean>;
    readonly progress: Signal<number>;
    readonly progressPercent: Signal<number>;
}
/**
 * Actions for updating WaveSurfer state
 */
export interface WaveSurferActions {
    setCurrentTime: (time: number) => void;
    setDuration: (duration: number) => void;
    setPlaying: (playing: boolean) => void;
    setSeeking: (seeking: boolean) => void;
    setVolume: (volume: number) => void;
    setPlaybackRate: (rate: number) => void;
    setAudioBuffer: (buffer: AudioBuffer | null) => void;
    setPeaks: (peaks: Array<Float32Array | number[]> | null) => void;
    setUrl: (url: string) => void;
    setZoom: (zoom: number) => void;
    setScrollPosition: (position: number) => void;
}
/**
 * Optional Player signals to compose into WaveSurferState
 * When provided, these signals from Player are used directly instead of creating new ones
 * Note: Signals must be WritableSignal to allow state actions to update them
 */
export interface PlayerSignals {
    isPlaying?: WritableSignal<boolean>;
    currentTime?: WritableSignal<number>;
    duration?: WritableSignal<number>;
    volume?: WritableSignal<number>;
    playbackRate?: WritableSignal<number>;
    isSeeking?: WritableSignal<boolean>;
}
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
export declare function createWaveSurferState(playerSignals?: PlayerSignals): {
    state: WaveSurferState;
    actions: WaveSurferActions;
};
