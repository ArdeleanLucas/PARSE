/**
 * Media event bridge utilities
 *
 * Bridges HTMLMediaElement events to reactive state updates.
 * Provides a clean separation between imperative media API and reactive state.
 */
import type { WaveSurferActions } from '../state/wavesurfer-state.js';
/**
 * Bridge HTMLMediaElement events to WaveSurfer state actions
 *
 * This function sets up event listeners on a media element that automatically
 * update the reactive state through actions. It handles all standard media events
 * (play, pause, timeupdate, etc.) and keeps state in sync with media.
 *
 * @example
 * ```typescript
 * const { state, actions } = createWaveSurferState()
 * const media = document.createElement('audio')
 *
 * const cleanup = bridgeMediaEvents(media, actions)
 *
 * // Now media events automatically update state
 * media.play() // → actions.setPlaying(true)
 * ```
 *
 * @param media - HTMLMediaElement to listen to
 * @param actions - State actions to call on events
 * @returns Cleanup function that removes all listeners
 */
export declare function bridgeMediaEvents(media: HTMLMediaElement, actions: WaveSurferActions): () => void;
/**
 * Bridge HTMLMediaElement events with custom handler
 *
 * Similar to bridgeMediaEvents but allows custom state update logic.
 * Useful when you need more control over how events map to state.
 *
 * @example
 * ```typescript
 * const cleanup = bridgeMediaEventsWithHandler(media, (event, data) => {
 *   if (event === 'play') {
 *     actions.setPlaying(true)
 *     console.log('Started playing')
 *   }
 * })
 * ```
 *
 * @param media - HTMLMediaElement to listen to
 * @param handler - Custom handler function
 * @returns Cleanup function that removes all listeners
 */
export declare function bridgeMediaEventsWithHandler(media: HTMLMediaElement, handler: (event: string, data?: any) => void): () => void;
