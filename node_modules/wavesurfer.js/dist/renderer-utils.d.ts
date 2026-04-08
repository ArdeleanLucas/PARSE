import type { WaveSurferOptions } from './wavesurfer.js';
export type ChannelData = Array<Float32Array | number[]>;
export type BarSegment = {
    x: number;
    y: number;
    width: number;
    height: number;
};
export type LinePath = Array<{
    x: number;
    y: number;
}>;
export declare const DEFAULT_HEIGHT = 128;
export declare const MAX_CANVAS_WIDTH = 8000;
export declare const MAX_NODES = 10;
export declare function clampToUnit(value: number): number;
export declare function calculateBarRenderConfig({ width, height, length, options, pixelRatio, }: {
    width: number;
    height: number;
    length: number;
    options: WaveSurferOptions;
    pixelRatio: number;
}): {
    halfHeight: number;
    barWidth: number;
    barGap: number;
    barRadius: number;
    barMinHeight: number;
    barIndexScale: number;
    barSpacing: number;
};
export declare function calculateBarHeights({ maxTop, maxBottom, halfHeight, vScale, barMinHeight, barAlign, }: {
    maxTop: number;
    maxBottom: number;
    halfHeight: number;
    vScale: number;
    barMinHeight?: number;
    barAlign?: WaveSurferOptions['barAlign'];
}): {
    topHeight: number;
    totalHeight: number;
};
export declare function resolveBarYPosition({ barAlign, halfHeight, topHeight, totalHeight, canvasHeight, }: {
    barAlign: WaveSurferOptions['barAlign'];
    halfHeight: number;
    topHeight: number;
    totalHeight: number;
    canvasHeight: number;
}): number;
export declare function calculateBarSegments({ channelData, barIndexScale, barSpacing, barWidth, halfHeight, vScale, canvasHeight, barAlign, barMinHeight, }: {
    channelData: ChannelData;
    barIndexScale: number;
    barSpacing: number;
    barWidth: number;
    halfHeight: number;
    vScale: number;
    canvasHeight: number;
    barAlign: WaveSurferOptions['barAlign'];
    barMinHeight: number;
}): BarSegment[];
export declare function getRelativePointerPosition(rect: DOMRect, clientX: number, clientY: number): [number, number];
export declare function resolveChannelHeight({ optionsHeight, optionsSplitChannels, parentHeight, numberOfChannels, defaultHeight, }: {
    optionsHeight?: WaveSurferOptions['height'];
    optionsSplitChannels?: WaveSurferOptions['splitChannels'];
    parentHeight: number;
    numberOfChannels: number;
    defaultHeight?: number;
}): number;
export declare function getPixelRatio(devicePixelRatio?: number): number;
export declare function shouldRenderBars(options: WaveSurferOptions): boolean;
export declare function resolveColorValue(color: WaveSurferOptions['waveColor'], devicePixelRatio: number, canvasHeight?: number): string | CanvasGradient;
export declare function calculateWaveformLayout({ duration, minPxPerSec, parentWidth, fillParent, pixelRatio, }: {
    duration: number;
    minPxPerSec?: number;
    parentWidth: number;
    fillParent?: boolean;
    pixelRatio: number;
}): {
    scrollWidth: number;
    isScrollable: boolean;
    useParentWidth: boolean;
    width: number;
};
export declare function clampWidthToBarGrid(width: number, options: WaveSurferOptions): number;
export declare function calculateSingleCanvasWidth({ clientWidth, totalWidth, options, }: {
    clientWidth: number;
    totalWidth: number;
    options: WaveSurferOptions;
}): number;
export declare function sliceChannelData({ channelData, offset, clampedWidth, totalWidth, }: {
    channelData: ChannelData;
    offset: number;
    clampedWidth: number;
    totalWidth: number;
}): ChannelData;
export declare function shouldClearCanvases(currentNodeCount: number): boolean;
export declare function getLazyRenderRange({ scrollLeft, totalWidth, numCanvases, }: {
    scrollLeft: number;
    totalWidth: number;
    numCanvases: number;
}): number[];
export declare function calculateVerticalScale({ channelData, barHeight, normalize, maxPeak, }: {
    channelData: ChannelData;
    barHeight?: WaveSurferOptions['barHeight'];
    normalize?: WaveSurferOptions['normalize'];
    maxPeak?: WaveSurferOptions['maxPeak'];
}): number;
export declare function calculateLinePaths({ channelData, width, height, vScale, }: {
    channelData: ChannelData;
    width: number;
    height: number;
    vScale: number;
}): LinePath[];
/**
 * @deprecated Use calculateScrollPercentages from './reactive/scroll-stream.js' instead.
 * This function is maintained for backward compatibility but will be removed in a future version.
 */
export declare function calculateScrollPercentages({ scrollLeft, clientWidth, scrollWidth, }: {
    scrollLeft: number;
    clientWidth: number;
    scrollWidth: number;
}): {
    startX: number;
    endX: number;
};
export declare function roundToHalfAwayFromZero(value: number): number;
