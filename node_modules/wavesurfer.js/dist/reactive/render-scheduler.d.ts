/**
 * RenderScheduler batches multiple render requests into a single frame using requestAnimationFrame.
 * This prevents multiple state changes from triggering redundant renders.
 */
export type RenderPriority = 'high' | 'normal' | 'low';
export declare class RenderScheduler {
    private pendingRender;
    private rafId;
    /**
     * Schedule a render to occur on the next animation frame.
     * If a render is already scheduled, this is a no-op.
     *
     * @param renderFn - The function to call to perform the render
     * @param priority - Render priority (high = immediate, normal/low = batched)
     *
     * @example
     * ```typescript
     * const scheduler = new RenderScheduler()
     *
     * // Multiple calls in same frame = single render
     * scheduler.scheduleRender(() => draw())
     * scheduler.scheduleRender(() => draw()) // no-op
     * scheduler.scheduleRender(() => draw()) // no-op
     * ```
     */
    scheduleRender(renderFn: () => void, priority?: RenderPriority): void;
    /**
     * Cancel any pending render request.
     * Useful when unmounting or destroying components.
     */
    cancelRender(): void;
    /**
     * Force an immediate synchronous render, canceling any pending batched render.
     * Use for high-priority updates like cursor during playback, or for testing.
     *
     * @param renderFn - The function to call to perform the render
     */
    flushRender(renderFn: () => void): void;
    /**
     * Check if a render is currently scheduled.
     */
    isPending(): boolean;
}
