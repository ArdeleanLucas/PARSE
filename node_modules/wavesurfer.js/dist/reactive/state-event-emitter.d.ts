/**
 * State-driven event emission utilities
 *
 * Automatically emit events when reactive state changes.
 * Ensures events are always in sync with state and removes manual emit() calls.
 */
import { type Signal } from './store.js';
import type { WaveSurferState } from '../state/wavesurfer-state.js';
export type EventEmitter = {
    emit(event: string, ...args: any[]): void;
};
/**
 * Setup automatic event emission from state changes
 *
 * This function subscribes to all relevant state signals and automatically
 * emits corresponding events when state changes. This ensures:
 * - Events are always in sync with state
 * - No manual emit() calls needed
 * - Can't forget to emit an event
 * - Clear event sources (state changes)
 *
 * @example
 * ```typescript
 * const { state } = createWaveSurferState()
 * const wavesurfer = new WaveSurfer()
 *
 * const cleanup = setupStateEventEmission(state, wavesurfer)
 *
 * // Now state changes automatically emit events
 * state.isPlaying.set(true) // → wavesurfer.emit('play')
 * ```
 *
 * @param state - Reactive state to observe
 * @param emitter - Event emitter to emit events on
 * @returns Cleanup function that removes all subscriptions
 */
export declare function setupStateEventEmission(state: WaveSurferState, emitter: EventEmitter): () => void;
/**
 * Setup custom event emission from signal changes
 *
 * This is a lower-level utility for setting up custom event emission
 * from any signal. Useful when you need more control over event emission logic.
 *
 * @example
 * ```typescript
 * const volumeSignal = signal(1)
 *
 * const cleanup = setupSignalEventEmission(
 *   volumeSignal,
 *   emitter,
 *   (volume) => ['volume', volume]
 * )
 * ```
 *
 * @param signal - Signal to observe
 * @param emitter - Event emitter
 * @param getEventData - Function that returns [eventName, ...args]
 * @returns Cleanup function
 */
export declare function setupSignalEventEmission<T>(signal: Signal<T>, emitter: EventEmitter, getEventData: (value: T) => [string, ...any[]]): () => void;
/**
 * Setup event emission with debouncing
 *
 * Useful for high-frequency events like scroll or timeupdate.
 *
 * @example
 * ```typescript
 * const cleanup = setupDebouncedEventEmission(
 *   state.scrollPosition,
 *   emitter,
 *   (pos) => ['scroll', pos],
 *   100 // debounce 100ms
 * )
 * ```
 *
 * @param signal - Signal to observe
 * @param emitter - Event emitter
 * @param getEventData - Function that returns [eventName, ...args]
 * @param debounceMs - Debounce delay in milliseconds
 * @returns Cleanup function
 */
export declare function setupDebouncedEventEmission<T>(signal: Signal<T>, emitter: EventEmitter, getEventData: (value: T) => [string, ...any[]], debounceMs: number): () => void;
/**
 * Setup conditional event emission
 *
 * Only emit events when a condition is met.
 *
 * @example
 * ```typescript
 * // Only emit finish event when playing stops at end
 * const cleanup = setupConditionalEventEmission(
 *   state.isPlaying,
 *   emitter,
 *   (isPlaying) => !isPlaying && state.currentTime.value >= state.duration.value,
 *   () => ['finish']
 * )
 * ```
 *
 * @param signal - Signal to observe
 * @param emitter - Event emitter
 * @param condition - Function that returns true when event should emit
 * @param getEventData - Function that returns [eventName, ...args]
 * @returns Cleanup function
 */
export declare function setupConditionalEventEmission<T>(signal: Signal<T>, emitter: EventEmitter, condition: (value: T) => boolean, getEventData: (value: T) => [string, ...any[]]): () => void;
