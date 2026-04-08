/**
 * Reactive primitives for managing state in WaveSurfer
 *
 * This module provides signal-based reactivity similar to SolidJS signals.
 * Signals are reactive values that notify subscribers when they change.
 */
/**
 * A reactive value that can be read and subscribed to
 */
export interface Signal<T> {
    /** Get the current value */
    get value(): T;
    /** Subscribe to changes. Returns an unsubscribe function. */
    subscribe(callback: (value: T) => void): () => void;
}
/**
 * A writable reactive value that can be updated
 */
export interface WritableSignal<T> extends Signal<T> {
    /** Set a new value. Only notifies if value changed. */
    set(value: T): void;
    /** Update value using a function. */
    update(fn: (current: T) => T): void;
}
/**
 * Create a reactive signal that notifies subscribers when its value changes
 *
 * @example
 * ```typescript
 * const count = signal(0)
 * count.subscribe(val => console.log('Count:', val))
 * count.set(5) // Logs: Count: 5
 * ```
 */
export declare function signal<T>(initialValue: T): WritableSignal<T>;
/**
 * Create a computed value that automatically updates when its dependencies change
 *
 * @example
 * ```typescript
 * const count = signal(0)
 * const doubled = computed(() => count.value * 2, [count])
 * console.log(doubled.value) // 0
 * count.set(5)
 * console.log(doubled.value) // 10
 * ```
 */
export declare function computed<T>(fn: () => T, dependencies: Signal<any>[]): Signal<T>;
/**
 * Run a side effect automatically when dependencies change
 *
 * @param fn - Effect function. Can return a cleanup function.
 * @param dependencies - Signals that trigger the effect when they change
 * @returns Unsubscribe function that stops the effect and runs cleanup
 *
 * @example
 * ```typescript
 * const count = signal(0)
 * effect(() => {
 *   console.log('Count is:', count.value)
 *   return () => console.log('Cleanup')
 * }, [count])
 * count.set(5) // Logs: Cleanup, Count is: 5
 * ```
 */
export declare function effect(fn: () => void | (() => void), dependencies: Signal<any>[]): () => void;
