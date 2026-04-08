var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
function watchProgress(response, progressCallback) {
    return __awaiter(this, void 0, void 0, function* () {
        if (!response.body || !response.headers)
            return;
        const reader = response.body.getReader();
        const contentLength = Number(response.headers.get('Content-Length')) || 0;
        let receivedLength = 0;
        // Process the data
        const processChunk = (value) => {
            // Add to the received length
            receivedLength += (value === null || value === void 0 ? void 0 : value.length) || 0;
            const percentage = Math.round((receivedLength / contentLength) * 100);
            progressCallback(percentage);
        };
        // Use iteration instead of recursion to avoid stack issues
        try {
            while (true) {
                const data = yield reader.read();
                if (data.done) {
                    break;
                }
                processChunk(data.value);
            }
        }
        catch (err) {
            // Ignore errors because we can only handle the main response
            console.warn('Progress tracking error:', err);
        }
    });
}
function fetchBlob(url, progressCallback, requestInit) {
    return __awaiter(this, void 0, void 0, function* () {
        // Fetch the resource
        const response = yield fetch(url, requestInit);
        if (response.status >= 400) {
            throw new Error(`Failed to fetch ${url}: ${response.status} (${response.statusText})`);
        }
        // Read the data to track progress
        watchProgress(response.clone(), progressCallback);
        return response.blob();
    });
}
const Fetcher = {
    fetchBlob,
};
export default Fetcher;
