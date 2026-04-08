var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __rest = (this && this.__rest) || function (s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
        t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function")
        for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
            if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
        }
    return t;
};
import EventEmitter from './event-emitter.js';
import * as utils from './renderer-utils.js';
import { createDragStream } from './reactive/drag-stream.js';
import { createScrollStream } from './reactive/scroll-stream.js';
import { effect } from './reactive/store.js';
const SMOOTH_SCROLL_FPS = 60;
const SMOOTH_SCROLL_MAX_DELTA = 10;
const LOW_ZOOM_PIXELS_PER_SECOND_THRESHOLD = SMOOTH_SCROLL_MAX_DELTA * SMOOTH_SCROLL_FPS;
class Renderer extends EventEmitter {
    constructor(options, audioElement) {
        super();
        this.timeouts = [];
        this.isScrollable = false;
        this.audioData = null;
        this.resizeObserver = null;
        this.lastContainerWidth = 0;
        this.isDragging = false;
        this.subscriptions = [];
        this.unsubscribeOnScroll = [];
        this.dragStream = null;
        this.scrollStream = null;
        this.subscriptions = [];
        this.options = options;
        const parent = this.parentFromOptionsContainer(options.container);
        this.parent = parent;
        const [div, shadow] = this.initHtml();
        parent.appendChild(div);
        this.container = div;
        this.scrollContainer = shadow.querySelector('.scroll');
        this.wrapper = shadow.querySelector('.wrapper');
        this.canvasWrapper = shadow.querySelector('.canvases');
        this.progressWrapper = shadow.querySelector('.progress');
        this.cursor = shadow.querySelector('.cursor');
        if (audioElement) {
            shadow.appendChild(audioElement);
        }
        this.initEvents();
    }
    parentFromOptionsContainer(container) {
        let parent;
        if (typeof container === 'string') {
            parent = document.querySelector(container);
        }
        else if (container instanceof HTMLElement) {
            parent = container;
        }
        if (!parent) {
            throw new Error('Container not found');
        }
        return parent;
    }
    initEvents() {
        // Add a click listener
        this.wrapper.addEventListener('click', (e) => {
            const rect = this.wrapper.getBoundingClientRect();
            const [x, y] = utils.getRelativePointerPosition(rect, e.clientX, e.clientY);
            this.emit('click', x, y);
        });
        // Add a double click listener
        this.wrapper.addEventListener('dblclick', (e) => {
            const rect = this.wrapper.getBoundingClientRect();
            const [x, y] = utils.getRelativePointerPosition(rect, e.clientX, e.clientY);
            this.emit('dblclick', x, y);
        });
        // Drag
        if (this.options.dragToSeek === true || typeof this.options.dragToSeek === 'object') {
            this.initDrag();
        }
        // Add a scroll listener using reactive stream
        this.scrollStream = createScrollStream(this.scrollContainer);
        const unsubscribeScroll = effect(() => {
            const { startX, endX } = this.scrollStream.percentages.value;
            const { left, right } = this.scrollStream.bounds.value;
            this.emit('scroll', startX, endX, left, right);
        }, [this.scrollStream.percentages, this.scrollStream.bounds]);
        this.subscriptions.push(unsubscribeScroll);
        // Re-render the waveform on container resize
        if (typeof ResizeObserver === 'function') {
            const delay = this.createDelay(100);
            this.resizeObserver = new ResizeObserver(() => {
                delay()
                    .then(() => this.onContainerResize())
                    .catch(() => undefined);
            });
            this.resizeObserver.observe(this.scrollContainer);
        }
    }
    onContainerResize() {
        const width = this.parent.clientWidth;
        if (width === this.lastContainerWidth && this.options.height !== 'auto')
            return;
        this.lastContainerWidth = width;
        this.reRender();
        this.emit('resize');
    }
    initDrag() {
        // Don't initialize drag if it's already set up
        if (this.dragStream)
            return;
        this.dragStream = createDragStream(this.wrapper);
        const unsubscribeDrag = effect(() => {
            const drag = this.dragStream.signal.value;
            if (!drag)
                return;
            const width = this.wrapper.getBoundingClientRect().width;
            const relX = utils.clampToUnit(drag.x / width);
            if (drag.type === 'start') {
                this.isDragging = true;
                this.emit('dragstart', relX);
            }
            else if (drag.type === 'move') {
                this.emit('drag', relX);
            }
            else if (drag.type === 'end') {
                this.isDragging = false;
                this.emit('dragend', relX);
            }
        }, [this.dragStream.signal]);
        this.subscriptions.push(unsubscribeDrag);
    }
    initHtml() {
        const div = document.createElement('div');
        const shadow = div.attachShadow({ mode: 'open' });
        const cspNonce = this.options.cspNonce && typeof this.options.cspNonce === 'string' ? this.options.cspNonce.replace(/"/g, '') : '';
        shadow.innerHTML = `
      <style${cspNonce ? ` nonce="${cspNonce}"` : ''}>
        :host {
          user-select: none;
          min-width: 1px;
        }
        :host audio {
          display: block;
          width: 100%;
        }
        :host .scroll {
          overflow-x: auto;
          overflow-y: hidden;
          width: 100%;
          position: relative;
        }
        :host .noScrollbar {
          scrollbar-color: transparent;
          scrollbar-width: none;
        }
        :host .noScrollbar::-webkit-scrollbar {
          display: none;
          -webkit-appearance: none;
        }
        :host .wrapper {
          position: relative;
          overflow: visible;
          z-index: 2;
        }
        :host .canvases {
          min-height: ${this.getHeight(this.options.height, this.options.splitChannels)}px;
          pointer-events: none;
        }
        :host .canvases > div {
          position: relative;
        }
        :host canvas {
          display: block;
          position: absolute;
          top: 0;
          image-rendering: pixelated;
        }
        :host .progress {
          pointer-events: none;
          position: absolute;
          z-index: 2;
          top: 0;
          left: 0;
          width: 0;
          height: 100%;
          overflow: hidden;
        }
        :host .progress > div {
          position: relative;
        }
        :host .cursor {
          pointer-events: none;
          position: absolute;
          z-index: 5;
          top: 0;
          left: 0;
          height: 100%;
          border-radius: 2px;
        }
      </style>

      <div class="scroll" part="scroll">
        <div class="wrapper" part="wrapper">
          <div class="canvases" part="canvases"></div>
          <div class="progress" part="progress"></div>
          <div class="cursor" part="cursor"></div>
        </div>
      </div>
    `;
        return [div, shadow];
    }
    /** Wavesurfer itself calls this method. Do not call it manually. */
    setOptions(options) {
        var _a;
        if (this.options.container !== options.container) {
            const newParent = this.parentFromOptionsContainer(options.container);
            newParent.appendChild(this.container);
            this.parent = newParent;
        }
        if (options.dragToSeek === true || typeof this.options.dragToSeek === 'object') {
            this.initDrag();
        }
        else {
            (_a = this.dragStream) === null || _a === void 0 ? void 0 : _a.cleanup();
            this.dragStream = null;
        }
        this.options = options;
        // Re-render the waveform
        this.reRender();
    }
    getWrapper() {
        return this.wrapper;
    }
    getWidth() {
        return this.scrollContainer.clientWidth;
    }
    getScroll() {
        return this.scrollContainer.scrollLeft;
    }
    setScroll(pixels) {
        this.scrollContainer.scrollLeft = pixels;
    }
    setScrollPercentage(percent) {
        const { scrollWidth } = this.scrollContainer;
        const scrollStart = scrollWidth * percent;
        this.setScroll(scrollStart);
    }
    destroy() {
        var _a;
        this.subscriptions.forEach((unsubscribe) => unsubscribe());
        this.container.remove();
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        (_a = this.unsubscribeOnScroll) === null || _a === void 0 ? void 0 : _a.forEach((unsubscribe) => unsubscribe());
        this.unsubscribeOnScroll = [];
        if (this.dragStream) {
            this.dragStream.cleanup();
            this.dragStream = null;
        }
        if (this.scrollStream) {
            this.scrollStream.cleanup();
            this.scrollStream = null;
        }
    }
    createDelay(delayMs = 10) {
        let timeout;
        let rejectFn;
        const onClear = () => {
            if (timeout) {
                clearTimeout(timeout);
                timeout = undefined;
            }
            if (rejectFn) {
                rejectFn();
                rejectFn = undefined;
            }
        };
        this.timeouts.push(onClear);
        return () => {
            return new Promise((resolve, reject) => {
                // Clear any pending delay
                onClear();
                // Store reject function for cleanup
                rejectFn = reject;
                // Set new timeout
                timeout = setTimeout(() => {
                    timeout = undefined;
                    rejectFn = undefined;
                    resolve();
                }, delayMs);
            });
        };
    }
    getHeight(optionsHeight, optionsSplitChannel) {
        var _a;
        const numberOfChannels = ((_a = this.audioData) === null || _a === void 0 ? void 0 : _a.numberOfChannels) || 1;
        return utils.resolveChannelHeight({
            optionsHeight,
            optionsSplitChannels: optionsSplitChannel,
            parentHeight: this.parent.clientHeight,
            numberOfChannels,
            defaultHeight: utils.DEFAULT_HEIGHT,
        });
    }
    convertColorValues(color, ctx) {
        return utils.resolveColorValue(color, this.getPixelRatio(), ctx === null || ctx === void 0 ? void 0 : ctx.canvas.height);
    }
    getPixelRatio() {
        return utils.getPixelRatio(window.devicePixelRatio);
    }
    renderBarWaveform(channelData, options, ctx, vScale) {
        const { width, height } = ctx.canvas;
        const { halfHeight, barWidth, barRadius, barIndexScale, barSpacing, barMinHeight } = utils.calculateBarRenderConfig({
            width,
            height,
            length: (channelData[0] || []).length,
            options,
            pixelRatio: this.getPixelRatio(),
        });
        const segments = utils.calculateBarSegments({
            channelData,
            barIndexScale,
            barSpacing,
            barWidth,
            halfHeight,
            vScale,
            canvasHeight: height,
            barAlign: options.barAlign,
            barMinHeight,
        });
        ctx.beginPath();
        for (const segment of segments) {
            if (barRadius && 'roundRect' in ctx) {
                ;
                ctx.roundRect(segment.x, segment.y, segment.width, segment.height, barRadius);
            }
            else {
                ctx.rect(segment.x, segment.y, segment.width, segment.height);
            }
        }
        ctx.fill();
        ctx.closePath();
    }
    renderLineWaveform(channelData, _options, ctx, vScale) {
        const { width, height } = ctx.canvas;
        const paths = utils.calculateLinePaths({ channelData, width, height, vScale });
        ctx.beginPath();
        for (const path of paths) {
            if (!path.length)
                continue;
            ctx.moveTo(path[0].x, path[0].y);
            for (let i = 1; i < path.length; i++) {
                const point = path[i];
                ctx.lineTo(point.x, point.y);
            }
        }
        ctx.fill();
        ctx.closePath();
    }
    renderWaveform(channelData, options, ctx) {
        ctx.fillStyle = this.convertColorValues(options.waveColor, ctx);
        if (options.renderFunction) {
            options.renderFunction(channelData, ctx);
            return;
        }
        const vScale = utils.calculateVerticalScale({
            channelData,
            barHeight: options.barHeight,
            normalize: options.normalize,
            maxPeak: options.maxPeak,
        });
        if (utils.shouldRenderBars(options)) {
            this.renderBarWaveform(channelData, options, ctx, vScale);
            return;
        }
        this.renderLineWaveform(channelData, options, ctx, vScale);
    }
    renderSingleCanvas(data, options, width, height, offset, canvasContainer, progressContainer) {
        const pixelRatio = this.getPixelRatio();
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(width * pixelRatio);
        canvas.height = Math.round(height * pixelRatio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        canvas.style.left = `${Math.round(offset)}px`;
        canvasContainer.appendChild(canvas);
        const ctx = canvas.getContext('2d');
        if (options.renderFunction) {
            ctx.fillStyle = this.convertColorValues(options.waveColor, ctx);
            options.renderFunction(data, ctx);
        }
        else {
            this.renderWaveform(data, options, ctx);
        }
        // Draw a progress canvas
        if (canvas.width > 0 && canvas.height > 0) {
            const progressCanvas = canvas.cloneNode();
            const progressCtx = progressCanvas.getContext('2d');
            progressCtx.drawImage(canvas, 0, 0);
            // Set the composition method to draw only where the waveform is drawn
            progressCtx.globalCompositeOperation = 'source-in';
            progressCtx.fillStyle = this.convertColorValues(options.progressColor, progressCtx);
            // This rectangle acts as a mask thanks to the composition method
            progressCtx.fillRect(0, 0, canvas.width, canvas.height);
            progressContainer.appendChild(progressCanvas);
        }
    }
    renderMultiCanvas(channelData, options, width, height, canvasContainer, progressContainer) {
        const pixelRatio = this.getPixelRatio();
        const { clientWidth } = this.scrollContainer;
        const totalWidth = width / pixelRatio;
        const singleCanvasWidth = utils.calculateSingleCanvasWidth({ clientWidth, totalWidth, options });
        let drawnIndexes = {};
        // Nothing to render
        if (singleCanvasWidth === 0)
            return;
        // Draw a single canvas
        const draw = (index) => {
            if (index < 0 || index >= numCanvases)
                return;
            if (drawnIndexes[index])
                return;
            drawnIndexes[index] = true;
            const offset = index * singleCanvasWidth;
            let clampedWidth = Math.min(totalWidth - offset, singleCanvasWidth);
            // Clamp the width to the bar grid to avoid empty canvases at the end
            clampedWidth = utils.clampWidthToBarGrid(clampedWidth, options);
            if (clampedWidth <= 0)
                return;
            const data = utils.sliceChannelData({ channelData, offset, clampedWidth, totalWidth });
            this.renderSingleCanvas(data, options, clampedWidth, height, offset, canvasContainer, progressContainer);
        };
        // Clear canvases to avoid too many DOM nodes
        const clearCanvases = () => {
            if (utils.shouldClearCanvases(Object.keys(drawnIndexes).length)) {
                canvasContainer.innerHTML = '';
                progressContainer.innerHTML = '';
                drawnIndexes = {};
            }
        };
        // Calculate how many canvases to render
        const numCanvases = Math.ceil(totalWidth / singleCanvasWidth);
        // Render all canvases if the waveform doesn't scroll
        if (!this.isScrollable) {
            for (let i = 0; i < numCanvases; i++) {
                draw(i);
            }
            return;
        }
        // Lazy rendering
        const initialRange = utils.getLazyRenderRange({
            scrollLeft: this.scrollContainer.scrollLeft,
            totalWidth,
            numCanvases,
        });
        initialRange.forEach((index) => draw(index));
        // Subscribe to the scroll event to draw additional canvases
        if (numCanvases > 1) {
            const unsubscribe = this.on('scroll', () => {
                const { scrollLeft } = this.scrollContainer;
                clearCanvases();
                utils.getLazyRenderRange({ scrollLeft, totalWidth, numCanvases }).forEach((index) => draw(index));
            });
            this.unsubscribeOnScroll.push(unsubscribe);
        }
    }
    renderChannel(channelData, _a, width, channelIndex) {
        var { overlay } = _a, options = __rest(_a, ["overlay"]);
        // A container for canvases
        const canvasContainer = document.createElement('div');
        const height = this.getHeight(options.height, options.splitChannels);
        canvasContainer.style.height = `${height}px`;
        if (overlay && channelIndex > 0) {
            canvasContainer.style.marginTop = `-${height}px`;
        }
        this.canvasWrapper.style.minHeight = `${height}px`;
        this.canvasWrapper.appendChild(canvasContainer);
        // A container for progress canvases
        const progressContainer = canvasContainer.cloneNode();
        this.progressWrapper.appendChild(progressContainer);
        // Render the waveform
        this.renderMultiCanvas(channelData, options, width, height, canvasContainer, progressContainer);
    }
    render(audioData) {
        return __awaiter(this, void 0, void 0, function* () {
            var _a;
            // Clear previous timeouts
            this.timeouts.forEach((clear) => clear());
            this.timeouts = [];
            // Clear the canvases
            this.canvasWrapper.innerHTML = '';
            this.progressWrapper.innerHTML = '';
            // Width
            if (this.options.width != null) {
                this.scrollContainer.style.width =
                    typeof this.options.width === 'number' ? `${this.options.width}px` : this.options.width;
            }
            // Determine the width of the waveform
            const pixelRatio = this.getPixelRatio();
            const parentWidth = this.scrollContainer.clientWidth;
            const { scrollWidth, isScrollable, useParentWidth, width } = utils.calculateWaveformLayout({
                duration: audioData.duration,
                minPxPerSec: this.options.minPxPerSec || 0,
                parentWidth,
                fillParent: this.options.fillParent,
                pixelRatio,
            });
            // Whether the container should scroll
            this.isScrollable = isScrollable;
            // Set the width of the wrapper
            this.wrapper.style.width = useParentWidth ? '100%' : `${scrollWidth}px`;
            // Set additional styles
            this.scrollContainer.style.overflowX = this.isScrollable ? 'auto' : 'hidden';
            this.scrollContainer.classList.toggle('noScrollbar', !!this.options.hideScrollbar);
            this.cursor.style.backgroundColor = `${this.options.cursorColor || this.options.progressColor}`;
            this.cursor.style.width = `${this.options.cursorWidth}px`;
            this.audioData = audioData;
            this.emit('render');
            // Render the waveform
            if (this.options.splitChannels) {
                // Render a waveform for each channel
                for (let i = 0; i < audioData.numberOfChannels; i++) {
                    const options = Object.assign(Object.assign({}, this.options), (_a = this.options.splitChannels) === null || _a === void 0 ? void 0 : _a[i]);
                    this.renderChannel([audioData.getChannelData(i)], options, width, i);
                }
            }
            else {
                // Render a single waveform for the first two channels (left and right)
                const channels = [audioData.getChannelData(0)];
                if (audioData.numberOfChannels > 1)
                    channels.push(audioData.getChannelData(1));
                this.renderChannel(channels, this.options, width, 0);
            }
            // Must be emitted asynchronously for backward compatibility
            Promise.resolve().then(() => this.emit('rendered'));
        });
    }
    reRender() {
        this.unsubscribeOnScroll.forEach((unsubscribe) => unsubscribe());
        this.unsubscribeOnScroll = [];
        // Return if the waveform has not been rendered yet
        if (!this.audioData)
            return;
        // Remember the current cursor position
        const { scrollWidth } = this.scrollContainer;
        const { right: before } = this.progressWrapper.getBoundingClientRect();
        // Re-render the waveform
        this.render(this.audioData);
        // Adjust the scroll position so that the cursor stays in the same place
        if (this.isScrollable && scrollWidth !== this.scrollContainer.scrollWidth) {
            const { right: after } = this.progressWrapper.getBoundingClientRect();
            const delta = utils.roundToHalfAwayFromZero(after - before);
            this.scrollContainer.scrollLeft += delta;
        }
    }
    zoom(minPxPerSec) {
        this.options.minPxPerSec = minPxPerSec;
        this.reRender();
    }
    scrollIntoView(progress, isPlaying = false) {
        var _a;
        const { scrollLeft, scrollWidth, clientWidth } = this.scrollContainer;
        const progressWidth = progress * scrollWidth;
        const startEdge = scrollLeft;
        const endEdge = scrollLeft + clientWidth;
        const middle = clientWidth / 2;
        if (this.isDragging) {
            // Scroll when dragging close to the edge of the viewport
            const minGap = 30;
            if (progressWidth + minGap > endEdge) {
                this.scrollContainer.scrollLeft += minGap;
            }
            else if (progressWidth - minGap < startEdge) {
                this.scrollContainer.scrollLeft -= minGap;
            }
        }
        else {
            if (progressWidth < startEdge || progressWidth > endEdge) {
                this.scrollContainer.scrollLeft = progressWidth - (this.options.autoCenter ? middle : 0);
            }
            // Keep the cursor centered when playing
            const center = progressWidth - scrollLeft - middle;
            if (isPlaying && this.options.autoCenter && center > 0) {
                const duration = (_a = this.audioData) === null || _a === void 0 ? void 0 : _a.duration;
                if (duration === undefined || duration <= 0) {
                    this.scrollContainer.scrollLeft += center;
                    return;
                }
                const pixelsPerSecond = scrollWidth / duration;
                if (pixelsPerSecond <= LOW_ZOOM_PIXELS_PER_SECOND_THRESHOLD) {
                    this.scrollContainer.scrollLeft += Math.min(center, SMOOTH_SCROLL_MAX_DELTA);
                }
                else {
                    this.scrollContainer.scrollLeft += center;
                }
            }
        }
    }
    renderProgress(progress, isPlaying) {
        if (isNaN(progress))
            return;
        const percents = progress * 100;
        this.canvasWrapper.style.clipPath = `polygon(${percents}% 0%, 100% 0%, 100% 100%, ${percents}% 100%)`;
        this.progressWrapper.style.width = `${percents}%`;
        this.cursor.style.left = `${percents}%`;
        this.cursor.style.transform = this.options.cursorWidth
            ? `translateX(-${progress * this.options.cursorWidth}px)`
            : '';
        // Only scroll if we have valid audio data to prevent race conditions during loading
        if (this.isScrollable && this.options.autoScroll && this.audioData && this.audioData.duration > 0) {
            this.scrollIntoView(progress, isPlaying);
        }
    }
    exportImage(format, quality, type) {
        return __awaiter(this, void 0, void 0, function* () {
            const canvases = this.canvasWrapper.querySelectorAll('canvas');
            if (!canvases.length) {
                throw new Error('No waveform data');
            }
            // Data URLs
            if (type === 'dataURL') {
                const images = Array.from(canvases).map((canvas) => canvas.toDataURL(format, quality));
                return Promise.resolve(images);
            }
            // Blobs
            return Promise.all(Array.from(canvases).map((canvas) => {
                return new Promise((resolve, reject) => {
                    canvas.toBlob((blob) => {
                        if (blob) {
                            resolve(blob);
                        }
                        else {
                            reject(new Error('Could not export image'));
                        }
                    }, format, quality);
                });
            }));
        });
    }
}
export default Renderer;
