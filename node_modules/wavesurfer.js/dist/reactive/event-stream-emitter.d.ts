/**
 * Event stream emitter - bridges EventEmitter to reactive streams
 *
 * Provides reactive stream API on top of traditional EventEmitter.
 * This allows users to choose between callback-based and stream-based APIs.
 */
import { type Signal } from './store.js';
import type EventEmitter from '../event-emitter.js';
/**
 * Convert an EventEmitter event to a reactive signal/stream
 *
 * Creates a signal that updates whenever the event is emitted.
 * Returns both the signal (for reading values) and cleanup function.
 *
 * @example
 * ```typescript
 * const { stream, cleanup } = toStream(wavesurfer, 'play')
 *
 * // Subscribe to play events
 * stream.subscribe(() => console.log('Playing!'))
 *
 * // Cleanup when done
 * cleanup()
 * ```
 *
 * @param emitter - EventEmitter instance
 * @param eventName - Name of the event to stream
 * @returns Object with stream signal and cleanup function
 */
export declare function toStream<T extends Record<string, any[]>, K extends keyof T>(emitter: EventEmitter<T>, eventName: K): {
    stream: Signal<T[K] | null>;
    cleanup: () => void;
};
/**
 * Create multiple event streams from an emitter
 *
 * Helper to create streams for multiple events at once.
 *
 * @example
 * ```typescript
 * const streams = toStreams(wavesurfer, ['play', 'pause', 'timeupdate'])
 *
 * streams.play.subscribe(() => console.log('Play'))
 * streams.pause.subscribe(() => console.log('Pause'))
 * streams.timeupdate.subscribe(([time]) => console.log('Time:', time))
 *
 * // Cleanup all
 * streams.cleanup()
 * ```
 *
 * @param emitter - EventEmitter instance
 * @param eventNames - Array of event names to stream
 * @returns Object with streams for each event and cleanup function
 */
export declare function toStreams<T extends Record<string, any[]>, K extends keyof T>(emitter: EventEmitter<T>, eventNames: K[]): {
    [P in K]: Signal<T[P] | null>;
} & {
    cleanup: () => void;
};
/**
 * Create a stream that combines multiple events into one
 *
 * Useful when you want to react to any of several events.
 *
 * @example
 * ```typescript
 * const { stream, cleanup } = mergeStreams(wavesurfer, ['play', 'pause'])
 *
 * stream.subscribe(({ event, args }) => {
 *   console.log(`Event ${event} fired with`, args)
 * })
 * ```
 *
 * @param emitter - EventEmitter instance
 * @param eventNames - Array of event names to merge
 * @returns Object with merged stream and cleanup function
 */
export declare function mergeStreams<T extends Record<string, any[]>, K extends keyof T>(emitter: EventEmitter<T>, eventNames: K[]): {
    stream: Signal<{
        event: K;
        args: T[K];
    } | null>;
    cleanup: () => void;
};
/**
 * Helper to map event stream values
 *
 * @example
 * ```typescript
 * const { stream: timeStream } = toStream(wavesurfer, 'timeupdate')
 * const seconds = mapStream(timeStream, ([time]) => Math.floor(time))
 * ```
 */
export declare function mapStream<T, U>(source: Signal<T>, mapper: (value: T) => U): Signal<U>;
/**
 * Helper to filter event stream values
 *
 * @example
 * ```typescript
 * const { stream: timeStream } = toStream(wavesurfer, 'timeupdate')
 * const afterTenSeconds = filterStream(timeStream, ([time]) => time > 10)
 * ```
 */
export declare function filterStream<T>(source: Signal<T>, predicate: (value: T) => boolean): Signal<T | null>;
