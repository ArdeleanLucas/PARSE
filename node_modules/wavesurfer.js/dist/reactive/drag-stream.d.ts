/**
 * Reactive drag stream utilities
 *
 * Provides declarative drag handling using reactive streams.
 * Automatically handles mouseup cleanup and supports constraints.
 */
import { type Signal } from './store.js';
export interface DragEvent {
    type: 'start' | 'move' | 'end';
    x: number;
    y: number;
    deltaX?: number;
    deltaY?: number;
}
export interface DragStreamOptions {
    /** Minimum distance to move before dragging starts (default: 3) */
    threshold?: number;
    /** Mouse button to listen for (default: 0 = left button) */
    mouseButton?: number;
    /** Delay before touch drag starts in ms (default: 100) */
    touchDelay?: number;
}
/**
 * Create a reactive drag stream from an element
 *
 * Emits drag events (start, move, end) as the user drags the element.
 * Automatically handles pointer capture, multi-touch prevention, and cleanup.
 *
 * @example
 * ```typescript
 * const dragSignal = createDragStream(element)
 *
 * effect(() => {
 *   const drag = dragSignal.value
 *   if (drag?.type === 'move') {
 *     console.log('Dragging:', drag.deltaX, drag.deltaY)
 *   }
 * }, [dragSignal])
 * ```
 *
 * @param element - Element to make draggable
 * @param options - Drag configuration options
 * @returns Signal emitting drag events and cleanup function
 */
export declare function createDragStream(element: HTMLElement, options?: DragStreamOptions): {
    signal: Signal<DragEvent | null>;
    cleanup: () => void;
};
