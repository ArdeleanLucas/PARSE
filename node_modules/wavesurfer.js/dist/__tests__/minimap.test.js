var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
jest.mock('../wavesurfer.js', () => ({
    __esModule: true,
    default: {
        create: jest.fn(),
    },
}));
import MinimapPlugin from '../plugins/minimap.js';
import WaveSurfer from '../wavesurfer.js';
const createEmitter = () => {
    const listeners = new Map();
    return {
        on: jest.fn((event, listener) => {
            if (!listeners.has(event)) {
                listeners.set(event, new Set());
            }
            listeners.get(event).add(listener);
            return () => { var _a; return (_a = listeners.get(event)) === null || _a === void 0 ? void 0 : _a.delete(listener); };
        }),
        emit: (event, ...args) => {
            var _a;
            (_a = listeners.get(event)) === null || _a === void 0 ? void 0 : _a.forEach((listener) => listener(...args));
        },
    };
};
const createMiniWaveSurfer = (duration = 30) => {
    const emitter = createEmitter();
    const renderer = { renderProgress: jest.fn() };
    return Object.assign(Object.assign({}, emitter), { destroy: jest.fn(() => emitter.emit('destroy')), getDuration: jest.fn(() => duration), getRenderer: jest.fn(() => renderer), setTime: jest.fn(), renderer });
};
const createMainWaveSurfer = (dragToSeek = true) => {
    const emitter = createEmitter();
    const wrapperParent = document.createElement('div');
    const wrapper = document.createElement('div');
    const renderer = { renderProgress: jest.fn() };
    const channelData = new Float32Array([0, 1, -1]);
    let scroll = 0;
    let width = 200;
    let wrapperWidth = 500;
    Object.defineProperty(wrapper, 'clientWidth', {
        configurable: true,
        get: () => wrapperWidth,
    });
    wrapperParent.appendChild(wrapper);
    return Object.assign(Object.assign({}, emitter), { __setScroll: (value) => {
            scroll = value;
        }, __setWidth: (value) => {
            width = value;
        }, __setWrapperWidth: (value) => {
            wrapperWidth = value;
        }, options: { dragToSeek }, getCurrentTime: jest.fn(() => 12), getDecodedData: jest.fn(() => ({
            duration: 30,
            numberOfChannels: 1,
            getChannelData: jest.fn(() => channelData),
        })), getDuration: jest.fn(() => 30), getRenderer: jest.fn(() => renderer), getScroll: jest.fn(() => scroll), getWidth: jest.fn(() => width), getWrapper: jest.fn(() => wrapper), isPlaying: jest.fn(() => false), seekTo: jest.fn(), renderer });
};
const createMock = WaveSurfer.create;
describe('MinimapPlugin', () => {
    afterEach(() => {
        jest.clearAllMocks();
        jest.useRealTimers();
    });
    test('renders the minimap from peaks without sharing the main media element', () => __awaiter(void 0, void 0, void 0, function* () {
        const miniWaveSurfer = createMiniWaveSurfer();
        const mainWaveSurfer = createMainWaveSurfer();
        createMock.mockReturnValue(miniWaveSurfer);
        const plugin = MinimapPlugin.create({ height: 20 });
        plugin._init(mainWaveSurfer);
        yield Promise.resolve();
        expect(createMock).toHaveBeenCalledWith(expect.objectContaining({
            container: expect.any(HTMLElement),
            duration: 30,
            media: undefined,
            url: undefined,
        }));
        expect(createMock.mock.calls[0][0].peaks).toEqual([new Float32Array([0, 1, -1])]);
        mainWaveSurfer.emit('timeupdate', 5);
        expect(miniWaveSurfer.setTime).toHaveBeenLastCalledWith(5);
        mainWaveSurfer.emit('drag', 0.25);
        expect(miniWaveSurfer.renderer.renderProgress).toHaveBeenCalledWith(0.25, false);
    }));
    test('syncs the main waveform immediately when interacting with the minimap', () => __awaiter(void 0, void 0, void 0, function* () {
        jest.useFakeTimers();
        const miniWaveSurfer = createMiniWaveSurfer();
        const mainWaveSurfer = createMainWaveSurfer(true);
        createMock.mockReturnValue(miniWaveSurfer);
        const plugin = MinimapPlugin.create({ dragToSeek: true });
        plugin._init(mainWaveSurfer);
        yield Promise.resolve();
        miniWaveSurfer.emit('click', 0.5, 0.1);
        expect(mainWaveSurfer.seekTo).toHaveBeenCalledWith(0.5);
        miniWaveSurfer.emit('drag', 0.75);
        expect(mainWaveSurfer.renderer.renderProgress).toHaveBeenCalledWith(0.75, false);
        jest.advanceTimersByTime(200);
        expect(mainWaveSurfer.seekTo).toHaveBeenLastCalledWith(0.75);
    }));
    test('keeps the overlay contained while redraw and scroll updates are catching up during zoom-out', () => __awaiter(void 0, void 0, void 0, function* () {
        const miniWaveSurfer = createMiniWaveSurfer();
        const mainWaveSurfer = createMainWaveSurfer();
        createMock.mockReturnValue(miniWaveSurfer);
        const plugin = MinimapPlugin.create({ height: 20 });
        plugin._init(mainWaveSurfer);
        yield Promise.resolve();
        const minimapContainer = createMock.mock.calls[0][0].container;
        const overlay = minimapContainer.querySelector('[part="minimap-overlay"]');
        expect(overlay.style.transition).toBe('left 100ms ease-out, width 100ms ease-out');
        mainWaveSurfer.__setScroll(180);
        mainWaveSurfer.emit('redraw');
        mainWaveSurfer.emit('scroll', 10.8, 22.8, 180, 380);
        mainWaveSurfer.__setScroll(300);
        mainWaveSurfer.__setWrapperWidth(400);
        mainWaveSurfer.emit('redraw');
        expect(overlay.style.left).toBe('75%');
        expect(overlay.style.width).toBe('25%');
        mainWaveSurfer.__setScroll(200);
        mainWaveSurfer.emit('scroll', 15, 30, 200, 400);
        expect(overlay.style.left).toBe('50%');
        expect(overlay.style.width).toBe('50%');
    }));
});
