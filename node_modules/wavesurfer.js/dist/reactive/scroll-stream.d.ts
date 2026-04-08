/**
 * Reactive scroll stream utilities
 *
 * Provides declarative scroll handling using reactive streams.
 * Automatically handles scroll event optimization and cleanup.
 */
import { type Signal } from './store.js';
export interface ScrollData {
    /** Current scroll position in pixels */
    scrollLeft: number;
    /** Total scrollable width in pixels */
    scrollWidth: number;
    /** Visible viewport width in pixels */
    clientWidth: number;
}
export interface ScrollPercentages {
    /** Start position as percentage (0-1) */
    startX: number;
    /** End position as percentage (0-1) */
    endX: number;
}
/**
 * Calculate visible percentages from scroll data
 * Pure function - no side effects
 *
 * @param scrollData - Current scroll dimensions
 * @returns Start and end positions as percentages (0-1)
 */
export declare function calculateScrollPercentages(scrollData: ScrollData): ScrollPercentages;
/**
 * Calculate scroll bounds in pixels
 * Pure function - no side effects
 *
 * @param scrollData - Current scroll dimensions
 * @returns Left and right scroll bounds in pixels
 */
export declare function calculateScrollBounds(scrollData: ScrollData): {
    left: number;
    right: number;
};
export interface ScrollStream {
    /** Signal containing current scroll data */
    scrollData: Signal<ScrollData>;
    /** Computed signal with visible percentages */
    percentages: Signal<ScrollPercentages>;
    /** Computed signal with scroll bounds */
    bounds: Signal<{
        left: number;
        right: number;
    }>;
    /** Cleanup function to remove listeners */
    cleanup: () => void;
}
/**
 * Create a reactive scroll stream from an element
 *
 * Emits scroll data as the user scrolls the element.
 * Automatically computes derived values (percentages, bounds).
 *
 * @example
 * ```typescript
 * const scrollStream = createScrollStream(container)
 *
 * effect(() => {
 *   const { startX, endX } = scrollStream.percentages.value
 *   console.log('Visible:', startX, 'to', endX)
 * }, [scrollStream.percentages])
 *
 * scrollStream.cleanup()
 * ```
 *
 * @param element - Scrollable element
 * @returns Scroll stream with signals and cleanup
 */
export declare function createScrollStream(element: HTMLElement): ScrollStream;
/**
 * Create a scroll stream that automatically updates external state
 *
 * This is a convenience wrapper that connects scroll events to a state action.
 *
 * @example
 * ```typescript
 * const scrollStream = createScrollStreamWithAction(
 *   container,
 *   (scrollLeft) => actions.setScrollPosition(scrollLeft)
 * )
 * ```
 *
 * @param element - Scrollable element
 * @param onScrollChange - Action to call when scroll changes
 * @returns Scroll stream with signals and cleanup
 */
export declare function createScrollStreamWithAction(element: HTMLElement, onScrollChange: (scrollLeft: number) => void): ScrollStream;
