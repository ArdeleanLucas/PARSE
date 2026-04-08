import EventEmitter from './event-emitter.js';
type TimerEvents = {
    tick: [];
};
declare class Timer extends EventEmitter<TimerEvents> {
    private animationFrameId;
    private isRunning;
    start(): void;
    stop(): void;
    destroy(): void;
}
export default Timer;
