/**
 * Event stream utilities for converting DOM events to reactive signals
 *
 * These utilities allow composing event handling using reactive primitives.
 */
import { type Signal, type WritableSignal } from './store.js';
/**
 * Convert DOM events to a reactive signal
 *
 * @example
 * ```typescript
 * const clicks = fromEvent(button, 'click')
 * clicks.subscribe(event => console.log('Clicked!', event))
 * ```
 */
export declare function fromEvent<K extends keyof HTMLElementEventMap>(element: HTMLElement, eventName: K): WritableSignal<HTMLElementEventMap[K] | null>;
/**
 * Transform stream values using a mapping function
 *
 * @example
 * ```typescript
 * const clicks = fromEvent(button, 'click')
 * const positions = map(clicks, e => e ? e.clientX : 0)
 * ```
 */
export declare function map<T, U>(source: Signal<T>, mapper: (value: T) => U): Signal<U>;
/**
 * Filter stream values based on a predicate
 *
 * @example
 * ```typescript
 * const numbers = signal(5)
 * const evenOnly = filter(numbers, n => n % 2 === 0)
 * ```
 */
export declare function filter<T>(source: Signal<T>, predicate: (value: T) => boolean): Signal<T | null>;
/**
 * Debounce stream updates - wait for quiet period before emitting
 *
 * @example
 * ```typescript
 * const input = fromEvent(textField, 'input')
 * const debounced = debounce(input, 300) // Wait 300ms after last input
 * ```
 */
export declare function debounce<T>(source: Signal<T>, delay: number): Signal<T>;
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
export declare function throttle<T>(source: Signal<T>, delay: number): Signal<T>;
/**
 * Cleanup a stream created with event stream utilities
 *
 * This removes event listeners and unsubscribes from sources.
 */
export declare function cleanup(stream: Signal<any>): void;
