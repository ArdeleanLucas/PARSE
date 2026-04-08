/**
 * Event stream emitter - bridges EventEmitter to reactive streams
 *
 * Provides reactive stream API on top of traditional EventEmitter.
 * This allows users to choose between callback-based and stream-based APIs.
 */
import { signal } from './store.js';
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
export function toStream(emitter, eventName) {
    const stream = signal(null);
    // Listen to event and update signal
    const handler = (...args) => {
        stream.set(args);
    };
    // @ts-expect-error - EventEmitter on() signature
    const unsubscribe = emitter.on(eventName, handler);
    return {
        stream,
        cleanup: unsubscribe,
    };
}
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
export function toStreams(emitter, eventNames) {
    const cleanups = [];
    const result = {};
    for (const eventName of eventNames) {
        const { stream, cleanup } = toStream(emitter, eventName);
        result[eventName] = stream;
        cleanups.push(cleanup);
    }
    // Add cleanup that removes all event listeners
    result.cleanup = () => {
        cleanups.forEach((cleanup) => cleanup());
    };
    return result;
}
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
export function mergeStreams(emitter, eventNames) {
    const stream = signal(null);
    const cleanups = [];
    for (const eventName of eventNames) {
        // @ts-expect-error - EventEmitter on() signature
        const unsubscribe = emitter.on(eventName, (...args) => {
            stream.set({ event: eventName, args });
        });
        cleanups.push(unsubscribe);
    }
    return {
        stream,
        cleanup: () => {
            cleanups.forEach((cleanup) => cleanup());
        },
    };
}
/**
 * Helper to map event stream values
 *
 * @example
 * ```typescript
 * const { stream: timeStream } = toStream(wavesurfer, 'timeupdate')
 * const seconds = mapStream(timeStream, ([time]) => Math.floor(time))
 * ```
 */
export function mapStream(source, mapper) {
    const result = signal(mapper(source.value));
    const unsubscribe = source.subscribe((value) => {
        result.set(mapper(value));
    });
    result._cleanup = unsubscribe;
    return result;
}
/**
 * Helper to filter event stream values
 *
 * @example
 * ```typescript
 * const { stream: timeStream } = toStream(wavesurfer, 'timeupdate')
 * const afterTenSeconds = filterStream(timeStream, ([time]) => time > 10)
 * ```
 */
export function filterStream(source, predicate) {
    const initialValue = predicate(source.value) ? source.value : null;
    const result = signal(initialValue);
    const unsubscribe = source.subscribe((value) => {
        if (predicate(value)) {
            result.set(value);
        }
        else {
            result.set(null);
        }
    });
    result._cleanup = unsubscribe;
    return result;
}
