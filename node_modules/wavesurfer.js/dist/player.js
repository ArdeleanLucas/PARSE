var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
import EventEmitter from './event-emitter.js';
import { signal } from './reactive/store.js';
class Player extends EventEmitter {
    // Expose reactive state as writable signals
    // These are writable to allow WaveSurfer to compose them into centralized state
    get isPlayingSignal() {
        return this._isPlaying;
    }
    get currentTimeSignal() {
        return this._currentTime;
    }
    get durationSignal() {
        return this._duration;
    }
    get volumeSignal() {
        return this._volume;
    }
    get mutedSignal() {
        return this._muted;
    }
    get playbackRateSignal() {
        return this._playbackRate;
    }
    get seekingSignal() {
        return this._seeking;
    }
    constructor(options) {
        super();
        this.isExternalMedia = false;
        this.reactiveMediaEventCleanups = [];
        if (options.media) {
            this.media = options.media;
            this.isExternalMedia = true;
        }
        else {
            this.media = document.createElement('audio');
        }
        // Initialize reactive state
        this._isPlaying = signal(false);
        this._currentTime = signal(0);
        this._duration = signal(0);
        this._volume = signal(this.media.volume);
        this._muted = signal(this.media.muted);
        this._playbackRate = signal(this.media.playbackRate || 1);
        this._seeking = signal(false);
        // Setup reactive media event handlers
        this.setupReactiveMediaEvents();
        // Controls
        if (options.mediaControls) {
            this.media.controls = true;
        }
        // Autoplay
        if (options.autoplay) {
            this.media.autoplay = true;
        }
        // Speed
        if (options.playbackRate != null) {
            this.onMediaEvent('canplay', () => {
                if (options.playbackRate != null) {
                    this.media.playbackRate = options.playbackRate;
                }
            }, { once: true });
        }
    }
    /**
     * Setup reactive media event handlers that update signals
     * This bridges the imperative HTMLMediaElement API to reactive state
     */
    setupReactiveMediaEvents() {
        // Playing state
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('play', () => {
            this._isPlaying.set(true);
        }));
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('pause', () => {
            this._isPlaying.set(false);
        }));
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('ended', () => {
            this._isPlaying.set(false);
        }));
        // Time tracking
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('timeupdate', () => {
            this._currentTime.set(this.media.currentTime);
        }));
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('durationchange', () => {
            this._duration.set(this.media.duration || 0);
        }));
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('loadedmetadata', () => {
            this._duration.set(this.media.duration || 0);
        }));
        // Seeking state
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('seeking', () => {
            this._seeking.set(true);
        }));
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('seeked', () => {
            this._seeking.set(false);
        }));
        // Volume and muted
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('volumechange', () => {
            this._volume.set(this.media.volume);
            this._muted.set(this.media.muted);
        }));
        // Playback rate
        this.reactiveMediaEventCleanups.push(this.onMediaEvent('ratechange', () => {
            this._playbackRate.set(this.media.playbackRate);
        }));
    }
    onMediaEvent(event, callback, options) {
        this.media.addEventListener(event, callback, options);
        return () => this.media.removeEventListener(event, callback, options);
    }
    getSrc() {
        return this.media.currentSrc || this.media.src || '';
    }
    revokeSrc() {
        const src = this.getSrc();
        if (src.startsWith('blob:')) {
            URL.revokeObjectURL(src);
        }
    }
    canPlayType(type) {
        return this.media.canPlayType(type) !== '';
    }
    setSrc(url, blob) {
        const prevSrc = this.getSrc();
        if (url && prevSrc === url)
            return; // no need to change the source
        this.revokeSrc();
        const newSrc = blob instanceof Blob && (this.canPlayType(blob.type) || !url) ? URL.createObjectURL(blob) : url;
        // Reset the media element, otherwise it keeps the previous source
        if (prevSrc) {
            this.media.removeAttribute('src');
        }
        if (newSrc || url) {
            try {
                this.media.src = newSrc;
            }
            catch (_a) {
                this.media.src = url;
            }
        }
    }
    destroy() {
        // Cleanup reactive media event listeners
        this.reactiveMediaEventCleanups.forEach((cleanup) => cleanup());
        this.reactiveMediaEventCleanups = [];
        if (this.isExternalMedia)
            return;
        this.media.pause();
        this.revokeSrc();
        this.media.removeAttribute('src');
        // Load resets the media element to its initial state
        this.media.load();
        // Remove from DOM after cleanup
        this.media.remove();
    }
    setMediaElement(element) {
        // Cleanup reactive event listeners from old media element
        this.reactiveMediaEventCleanups.forEach((cleanup) => cleanup());
        this.reactiveMediaEventCleanups = [];
        // Set new media element
        this.media = element;
        // Reinitialize reactive event listeners on new media element
        this.setupReactiveMediaEvents();
    }
    /** Start playing the audio */
    play() {
        return __awaiter(this, void 0, void 0, function* () {
            try {
                return yield this.media.play();
            }
            catch (err) {
                if (err instanceof DOMException && err.name === 'AbortError') {
                    return;
                }
                throw err;
            }
        });
    }
    /** Pause the audio */
    pause() {
        this.media.pause();
    }
    /** Check if the audio is playing */
    isPlaying() {
        return !this.media.paused && !this.media.ended;
    }
    /** Jump to a specific time in the audio (in seconds) */
    setTime(time) {
        this.media.currentTime = Math.max(0, Math.min(time, this.getDuration()));
    }
    /** Get the duration of the audio in seconds */
    getDuration() {
        return this.media.duration;
    }
    /** Get the current audio position in seconds */
    getCurrentTime() {
        return this.media.currentTime;
    }
    /** Get the audio volume */
    getVolume() {
        return this.media.volume;
    }
    /** Set the audio volume */
    setVolume(volume) {
        this.media.volume = volume;
    }
    /** Get the audio muted state */
    getMuted() {
        return this.media.muted;
    }
    /** Mute or unmute the audio */
    setMuted(muted) {
        this.media.muted = muted;
    }
    /** Get the playback speed */
    getPlaybackRate() {
        return this.media.playbackRate;
    }
    /** Check if the audio is seeking */
    isSeeking() {
        return this.media.seeking;
    }
    /** Set the playback speed, pass an optional false to NOT preserve the pitch */
    setPlaybackRate(rate, preservePitch) {
        // preservePitch is true by default in most browsers
        if (preservePitch != null) {
            this.media.preservesPitch = preservePitch;
        }
        this.media.playbackRate = rate;
    }
    /** Get the HTML media element */
    getMediaElement() {
        return this.media;
    }
    /** Set a sink id to change the audio output device */
    setSinkId(sinkId) {
        // See https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/setSinkId
        const media = this.media;
        return media.setSinkId(sinkId);
    }
}
export default Player;
