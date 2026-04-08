/**
 * Reactive scroll stream utilities
 *
 * Provides declarative scroll handling using reactive streams.
 * Automatically handles scroll event optimization and cleanup.
 */
import { signal, computed, effect } from './store.js';
import { cleanup } from './event-streams.js';
// ============================================================================
// Pure Scroll Calculation Functions
// ============================================================================
/**
 * Calculate visible percentages from scroll data
 * Pure function - no side effects
 *
 * @param scrollData - Current scroll dimensions
 * @returns Start and end positions as percentages (0-1)
 */
export function calculateScrollPercentages(scrollData) {
    const { scrollLeft, scrollWidth, clientWidth } = scrollData;
    if (scrollWidth === 0) {
        return { startX: 0, endX: 1 };
    }
    const startX = scrollLeft / scrollWidth;
    const endX = (scrollLeft + clientWidth) / scrollWidth;
    return {
        startX: Math.max(0, Math.min(1, startX)),
        endX: Math.max(0, Math.min(1, endX)),
    };
}
/**
 * Calculate scroll bounds in pixels
 * Pure function - no side effects
 *
 * @param scrollData - Current scroll dimensions
 * @returns Left and right scroll bounds in pixels
 */
export function calculateScrollBounds(scrollData) {
    return {
        left: scrollData.scrollLeft,
        right: scrollData.scrollLeft + scrollData.clientWidth,
    };
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
export function createScrollStream(element) {
    // Create signals
    const scrollData = signal({
        scrollLeft: element.scrollLeft,
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
    });
    // Computed derived values
    const percentages = computed(() => {
        return calculateScrollPercentages(scrollData.value);
    }, [scrollData]);
    const bounds = computed(() => {
        return calculateScrollBounds(scrollData.value);
    }, [scrollData]);
    // Update scroll data on scroll event
    const onScroll = () => {
        scrollData.set({
            scrollLeft: element.scrollLeft,
            scrollWidth: element.scrollWidth,
            clientWidth: element.clientWidth,
        });
    };
    // Attach scroll listener
    element.addEventListener('scroll', onScroll, { passive: true });
    // Cleanup function
    const cleanupFn = () => {
        element.removeEventListener('scroll', onScroll);
        cleanup(scrollData);
    };
    return {
        scrollData,
        percentages,
        bounds,
        cleanup: cleanupFn,
    };
}
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
export function createScrollStreamWithAction(element, onScrollChange) {
    const stream = createScrollStream(element);
    // Effect to update external state
    const unsubscribe = effect(() => {
        onScrollChange(stream.scrollData.value.scrollLeft);
    }, [stream.scrollData]);
    // Wrap cleanup to include effect cleanup
    const originalCleanup = stream.cleanup;
    stream.cleanup = () => {
        unsubscribe();
        originalCleanup();
    };
    return stream;
}
