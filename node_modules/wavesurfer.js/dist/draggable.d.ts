/**
 * @deprecated Use createDragStream from './reactive/drag-stream.js' instead.
 * This function is maintained for backward compatibility but will be removed in a future version.
 */
export declare function makeDraggable(element: HTMLElement | null, onDrag: (dx: number, dy: number, x: number, y: number) => void, onStart?: (x: number, y: number) => void, onEnd?: (x: number, y: number) => void, threshold?: number, mouseButton?: number, touchDelay?: number): () => void;
