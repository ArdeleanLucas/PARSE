import RegionsPlugin from '../plugins/regions.js';
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
    };
};
const createWaveSurfer = (duration = 10, width = 100, scroll = 0) => {
    const emitter = createEmitter();
    const wrapper = document.createElement('div');
    document.body.appendChild(wrapper);
    return Object.assign(Object.assign({}, emitter), { getDecodedData: jest.fn(() => ({ numberOfChannels: 1 })), getDuration: jest.fn(() => duration), getScroll: jest.fn(() => scroll), getWidth: jest.fn(() => width), getWrapper: jest.fn(() => wrapper) });
};
describe('RegionsPlugin', () => {
    beforeEach(() => {
        jest.useFakeTimers();
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            value: jest.fn().mockImplementation((query) => ({
                matches: false,
                media: query,
                onchange: null,
                addListener: jest.fn(),
                removeListener: jest.fn(),
                addEventListener: jest.fn(),
                removeEventListener: jest.fn(),
                dispatchEvent: jest.fn(),
            })),
        });
    });
    afterEach(() => {
        jest.runOnlyPendingTimers();
        jest.useRealTimers();
        document.body.innerHTML = '';
        jest.clearAllMocks();
    });
    test('re-renders a lazily detached region when setOptions moves it into view', () => {
        var _a, _b, _c, _d, _e;
        const wavesurfer = createWaveSurfer();
        const plugin = RegionsPlugin.create();
        plugin._init(wavesurfer);
        const regionsContainer = wavesurfer.getWrapper().querySelector('[part="regions-container"]');
        expect(regionsContainer).toBeTruthy();
        Object.defineProperty(regionsContainer, 'clientWidth', { configurable: true, value: 1000 });
        const region = plugin.addRegion({ start: 8, end: 9 });
        jest.runOnlyPendingTimers();
        expect((_a = region.element) === null || _a === void 0 ? void 0 : _a.parentElement).toBeNull();
        region.setOptions({ start: 0.5, end: 1.5 });
        expect((_b = region.element) === null || _b === void 0 ? void 0 : _b.parentElement).toBe(regionsContainer);
        expect((_c = region.element) === null || _c === void 0 ? void 0 : _c.style.left).toBe('5%');
        expect((_d = region.element) === null || _d === void 0 ? void 0 : _d.style.right).toBe('85%');
        region.setOptions({ start: 8, end: 9 });
        expect((_e = region.element) === null || _e === void 0 ? void 0 : _e.parentElement).toBeNull();
    });
});
