/** A simple event emitter that can be used to listen to and emit events. */
class EventEmitter {
    constructor() {
        this.listeners = {};
    }
    /** Subscribe to an event. Returns an unsubscribe function. */
    on(event, listener, options) {
        if (!this.listeners[event]) {
            this.listeners[event] = new Set();
        }
        if (options === null || options === void 0 ? void 0 : options.once) {
            // Create a wrapper that removes itself after being called once
            const onceWrapper = (...args) => {
                this.un(event, onceWrapper);
                listener(...args);
            };
            this.listeners[event].add(onceWrapper);
            return () => this.un(event, onceWrapper);
        }
        this.listeners[event].add(listener);
        return () => this.un(event, listener);
    }
    /** Unsubscribe from an event */
    un(event, listener) {
        var _a;
        (_a = this.listeners[event]) === null || _a === void 0 ? void 0 : _a.delete(listener);
    }
    /** Subscribe to an event only once */
    once(event, listener) {
        return this.on(event, listener, { once: true });
    }
    /** Clear all events */
    unAll() {
        this.listeners = {};
    }
    /** Emit an event */
    emit(eventName, ...args) {
        if (this.listeners[eventName]) {
            this.listeners[eventName].forEach((listener) => listener(...args));
        }
    }
}
export default EventEmitter;
