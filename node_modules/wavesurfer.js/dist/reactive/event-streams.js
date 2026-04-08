/**
 * Event stream utilities for converting DOM events to reactive signals
 *
 * These utilities allow composing event handling using reactive primitives.
 */
import { signal } from './store.js';
/**
 * Convert DOM events to a reactive signal
 *
 * @example
 * ```typescript
 * const clicks = fromEvent(button, 'click')
 * clicks.subscribe(event => console.log('Clicked!', event))
 * ```
 */
export function fromEvent(element, eventName) {
    const stream = signal(null);
    const handler = (event) => {
        stream.set(event);
    };
    element.addEventListener(eventName, handler);
    stream._cleanup = () => {
        element.removeEventListener(eventName, handler);
    };
    return stream;
}
/**
 * Transform stream values using a mapping function
 *
 * @example
 * ```typescript
 * const clicks = fromEvent(button, 'click')
 * const positions = map(clicks, e => e ? e.clientX : 0)
 * ```
 */
export function map(source, mapper) {
    const result = signal(mapper(source.value));
    const unsubscribe = source.subscribe((value) => {
        ;
        result.set(mapper(value));
    });
    result._cleanup = unsubscribe;
    return result;
}
/**
 * Filter stream values based on a predicate
 *
 * @example
 * ```typescript
 * const numbers = signal(5)
 * const evenOnly = filter(numbers, n => n % 2 === 0)
 * ```
 */
export function filter(source, predicate) {
    const initialValue = predicate(source.value) ? source.value : null;
    const result = signal(initialValue);
    const unsubscribe = source.subscribe((value) => {
        if (predicate(value)) {
            ;
            result.set(value);
        }
        else {
            ;
            result.set(null);
        }
    });
    result._cleanup = unsubscribe;
    return result;
}
/**
 * Debounce stream updates - wait for quiet period before emitting
 *
 * @example
 * ```typescript
 * const input = fromEvent(textField, 'input')
 * const debounced = debounce(input, 300) // Wait 300ms after last input
 * ```
 */
export function debounce(source, delay) {
    const result = signal(source.value);
    let timeout;
    const unsubscribe = source.subscribe((value) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            ;
            result.set(value);
        }, delay);
    });
    result._cleanup = () => {
        clearTimeout(timeout);
        unsubscribe();
    };
    return result;
}
/**
 * Throttle stream updates - limit update frequency
 *
 * Emits immediately, then waits before allowing next emission.
 * Different from debounce which waits for quiet period.
 *
 * @example
 * ```typescript
 * const scroll = fromEvent(window, 'scroll')
 * const throttled = throttle(scroll, 100) // Max once per 100ms
 * ```
 */
export function throttle(source, delay) {
    const result = signal(source.value);
    let lastEmit = 0;
    let timeout;
    const unsubscribe = source.subscribe((value) => {
        const now = Date.now();
        const timeSinceLastEmit = now - lastEmit;
        if (timeSinceLastEmit >= delay) {
            // Enough time has passed, emit immediately
            ;
            result.set(value);
            lastEmit = now;
        }
        else {
            // Too soon, schedule for later
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                ;
                result.set(value);
                lastEmit = Date.now();
            }, delay - timeSinceLastEmit);
        }
    });
    result._cleanup = () => {
        clearTimeout(timeout);
        unsubscribe();
    };
    return result;
}
/**
 * Cleanup a stream created with event stream utilities
 *
 * This removes event listeners and unsubscribes from sources.
 */
export function cleanup(stream) {
    const cleanupFn = stream._cleanup;
    if (typeof cleanupFn === 'function') {
        cleanupFn();
    }
}
