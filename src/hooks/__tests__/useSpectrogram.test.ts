// @vitest-environment jsdom
import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSpectrogram } from "../useSpectrogram";
import type { SpectrogramParams } from "../../workers/spectrogram-worker";

type MockWorker = {
  postMessage: ReturnType<typeof vi.fn>;
  terminate: ReturnType<typeof vi.fn>;
  onmessage: ((evt: MessageEvent) => void) | null;
  onerror: ((evt: ErrorEvent) => void) | null;
};

function makeAudioBufferLike(samples?: Float32Array) {
  const length = samples?.length ?? 4410;
  const data = samples ?? new Float32Array(length);
  return {
    numberOfChannels: 1,
    length,
    sampleRate: 44100,
    duration: length / 44100,
    getChannelData: () => data,
  };
}

function makeLongAudioBufferLike(durationSec: number) {
  // Don't allocate the actual array — `useSpectrogram` will slice the channel
  // and only the slice gets read. Return a thin object that still answers
  // `getChannelData` with a typed array spanning the requested length.
  const sr = 44100;
  const length = Math.floor(durationSec * sr);
  const data = new Float32Array(length);
  return {
    numberOfChannels: 1,
    length,
    sampleRate: sr,
    duration: durationSec,
    getChannelData: () => data,
  };
}

const PARAMS: SpectrogramParams = {
  windowLengthSec: 0.005,
  windowShape: "gaussian",
  maxFrequencyHz: 5500,
  dynamicRangeDb: 50,
  preEmphasisHz: 50,
  colorScheme: "praat",
};

describe("useSpectrogram", () => {
  let clearRect: ReturnType<typeof vi.fn>;
  let drawImage: ReturnType<typeof vi.fn>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let getContextSpy: any;
  let workerInstances: MockWorker[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let WorkerMock: any;

  beforeEach(() => {
    vi.clearAllMocks();

    clearRect = vi.fn();
    drawImage = vi.fn();
    workerInstances = [];

    getContextSpy = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockImplementation((contextId: string) => {
        if (contextId === "2d") {
          return {
            clearRect,
            drawImage,
            putImageData: vi.fn(),
            imageSmoothingEnabled: false,
            imageSmoothingQuality: "low",
          } as unknown as CanvasRenderingContext2D;
        }
        return null;
      });

    WorkerMock = vi.fn(() => {
      const worker: MockWorker = {
        postMessage: vi.fn(),
        terminate: vi.fn(),
        onmessage: null,
        onerror: null,
      };
      workerInstances.push(worker);
      return worker;
    });

    vi.stubGlobal("Worker", WorkerMock);
  });

  it("when enabled=false, does not create worker and clears canvas", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 120;

    const wsRef = { current: null };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: false,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
      }),
    );

    expect(WorkerMock).not.toHaveBeenCalled();
    expect(getContextSpy).toHaveBeenCalledWith("2d");
    expect(clearRect).toHaveBeenCalledWith(0, 0, 640, 120);
  });

  it("when enabled=true, creates worker and posts compute payload with params", () => {
    const canvas = document.createElement("canvas");
    const wsMock = {
      getDecodedData: vi.fn(() => makeAudioBufferLike()),
    };

    const wsRef = { current: wsMock };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
      }),
    );

    expect(WorkerMock).toHaveBeenCalledTimes(1);
    expect(wsMock.getDecodedData).toHaveBeenCalledTimes(1);

    const worker = workerInstances[0];
    expect(worker.postMessage).toHaveBeenCalledTimes(1);

    const [payload] = vi.mocked(worker.postMessage).mock.calls[0] as [
      {
        type: string;
        audioData: Float32Array;
        sampleRate: number;
        params: SpectrogramParams;
      },
      Transferable[],
    ];

    expect(payload.type).toBe("compute");
    expect(payload.audioData).toBeInstanceOf(Float32Array);
    expect(payload.audioData.length).toBe(4410);
    expect(payload.sampleRate).toBe(44100);
    expect(payload.params).toEqual(PARAMS);
  });

  it("transfers audioData buffer in postMessage second argument", () => {
    const canvas = document.createElement("canvas");
    const wsRef = {
      current: {
        getDecodedData: vi.fn(() => makeAudioBufferLike()),
      },
    };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
      }),
    );

    const worker = workerInstances[0];
    const [payload, transfer] = vi.mocked(worker.postMessage).mock.calls[0] as [
      { audioData: Float32Array },
      Transferable[],
    ];

    expect(Array.isArray(transfer)).toBe(true);
    expect(transfer).toHaveLength(1);
    expect(transfer[0]).toBe(payload.audioData.buffer);
  });

  it("snaps canvas pixel dimensions to bounding rect × devicePixelRatio", () => {
    const canvas = document.createElement("canvas");
    Object.defineProperty(canvas, "getBoundingClientRect", {
      value: () => ({ width: 640, height: 180, top: 0, left: 0, right: 640, bottom: 180, x: 0, y: 0, toJSON: () => ({}) }),
    });
    Object.defineProperty(window, "devicePixelRatio", { value: 2, configurable: true });

    const wsRef = {
      current: {
        getDecodedData: vi.fn(() => makeAudioBufferLike()),
      },
    };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
      }),
    );

    expect(canvas.width).toBe(1280);
    expect(canvas.height).toBe(360);
  });

  it("terminates worker when enabled flips from true to false", () => {
    const canvas = document.createElement("canvas");
    const wsRef = {
      current: {
        getDecodedData: vi.fn(() => makeAudioBufferLike()),
      },
    };
    const canvasRef = { current: canvas };

    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useSpectrogram({
          enabled,
          wsRef: wsRef as never,
          canvasRef: canvasRef as never,
          params: PARAMS,
        }),
      { initialProps: { enabled: true } },
    );

    const worker = workerInstances[0];
    rerender({ enabled: false });

    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });

  it("terminates worker on unmount", () => {
    const canvas = document.createElement("canvas");
    const wsRef = {
      current: {
        getDecodedData: vi.fn(() => makeAudioBufferLike()),
      },
    };
    const canvasRef = { current: canvas };

    const { unmount } = renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
      }),
    );

    const worker = workerInstances[0];
    unmount();

    expect(worker.terminate).toHaveBeenCalled();
  });

  it("slices audio to the provided timeRange before posting", () => {
    const canvas = document.createElement("canvas");
    // 10 s at 44100 Hz = 441000 samples
    const audioBuf = makeLongAudioBufferLike(10);
    const wsRef = { current: { getDecodedData: vi.fn(() => audioBuf) } };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
        timeRange: { startSec: 2, endSec: 5 },
      }),
    );

    const worker = workerInstances[0];
    const [payload] = vi.mocked(worker.postMessage).mock.calls[0] as [
      { audioData: Float32Array; sampleRate: number },
      Transferable[],
    ];
    // 3 seconds at 44100 Hz = 132300 samples
    expect(payload.audioData.length).toBe(132300);
    expect(payload.sampleRate).toBe(44100);
  });

  it("clamps timeRange to the audio duration when endSec exceeds it", () => {
    const canvas = document.createElement("canvas");
    const audioBuf = makeLongAudioBufferLike(2);
    const wsRef = { current: { getDecodedData: vi.fn(() => audioBuf) } };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
        timeRange: { startSec: 0, endSec: 100 },
      }),
    );

    const worker = workerInstances[0];
    const [payload] = vi.mocked(worker.postMessage).mock.calls[0] as [
      { audioData: Float32Array },
      Transferable[],
    ];
    // 2 s at 44100 Hz = 88200 samples (entire buffer)
    expect(payload.audioData.length).toBe(88200);
  });

  it("defaults to the first 30 s of audio when no timeRange is provided", () => {
    const canvas = document.createElement("canvas");
    // 600 s of audio (10 minutes) — must NOT be passed in full
    const audioBuf = makeLongAudioBufferLike(600);
    const wsRef = { current: { getDecodedData: vi.fn(() => audioBuf) } };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
      }),
    );

    const worker = workerInstances[0];
    const [payload] = vi.mocked(worker.postMessage).mock.calls[0] as [
      { audioData: Float32Array },
      Transferable[],
    ];
    // Cap = 30 s × 44100 = 1323000 samples; not the full 26.46 M.
    expect(payload.audioData.length).toBe(1323000);
  });

  it("skips computation when the timeRange is empty (end <= start)", () => {
    const canvas = document.createElement("canvas");
    const wsRef = {
      current: { getDecodedData: vi.fn(() => makeAudioBufferLike()) },
    };
    const canvasRef = { current: canvas };

    renderHook(() =>
      useSpectrogram({
        enabled: true,
        wsRef: wsRef as never,
        canvasRef: canvasRef as never,
        params: PARAMS,
        timeRange: { startSec: 5, endSec: 5 },
      }),
    );

    expect(WorkerMock).not.toHaveBeenCalled();
  });
});
