var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
/** Decode an array buffer into an audio buffer */
function decode(audioData, sampleRate) {
    return __awaiter(this, void 0, void 0, function* () {
        const audioCtx = new AudioContext({ sampleRate });
        try {
            return yield audioCtx.decodeAudioData(audioData);
        }
        finally {
            // Ensure AudioContext is always closed, even on synchronous errors
            audioCtx.close();
        }
    });
}
/** Normalize peaks to -1..1 */
function normalize(channelData) {
    const firstChannel = channelData[0];
    if (firstChannel.some((n) => n > 1 || n < -1)) {
        const length = firstChannel.length;
        let max = 0;
        for (let i = 0; i < length; i++) {
            const absN = Math.abs(firstChannel[i]);
            if (absN > max)
                max = absN;
        }
        for (const channel of channelData) {
            for (let i = 0; i < length; i++) {
                channel[i] /= max;
            }
        }
    }
    return channelData;
}
/** Create an audio buffer from pre-decoded audio data */
function createBuffer(channelData, duration) {
    // Validate inputs
    if (!channelData || channelData.length === 0) {
        throw new Error('channelData must be a non-empty array');
    }
    if (duration <= 0) {
        throw new Error('duration must be greater than 0');
    }
    // If a single array of numbers is passed, make it an array of arrays
    if (typeof channelData[0] === 'number')
        channelData = [channelData];
    // Validate channel data after conversion
    if (!channelData[0] || channelData[0].length === 0) {
        throw new Error('channelData must contain non-empty channel arrays');
    }
    // Normalize to -1..1
    normalize(channelData);
    // Convert to Float32Array for consistency
    const float32Channels = channelData.map((channel) => channel instanceof Float32Array ? channel : Float32Array.from(channel));
    return {
        duration,
        length: float32Channels[0].length,
        sampleRate: float32Channels[0].length / duration,
        numberOfChannels: float32Channels.length,
        getChannelData: (i) => {
            const channel = float32Channels[i];
            if (!channel) {
                throw new Error(`Channel ${i} not found`);
            }
            return channel;
        },
        copyFromChannel: AudioBuffer.prototype.copyFromChannel,
        copyToChannel: AudioBuffer.prototype.copyToChannel,
    };
}
const Decoder = {
    decode,
    createBuffer,
};
export default Decoder;
