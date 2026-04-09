// @vitest-environment jsdom
import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSpectrogram } from "../useSpectrogram";

type MockWorker = {
  postMessage: ReturnType<typeof vi.fn>;
  terminate: ReturnType<typeof vi.fn>;
  onmessage: ((evt: MessageEvent) => void) | null;
  onerror: ((evt: ErrorEvent) => void) | null;
};

function makeAudioBufferLike() {
  return {
    numberOfChannels: 1,
    length: 4410,
    sampleRate: 44100,
    duration: 0.1,
    getChannelData: () => new Float32Array(4410),
  };
}

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
      }),
    );

    expect(WorkerMock).not.toHaveBeenCalled();
    expect(getContextSpy).toHaveBeenCalledWith("2d");
    expect(clearRect).toHaveBeenCalledWith(0, 0, 640, 120);
  });

  it("when enabled=true, creates worker and posts compute payload", () => {
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
        windowSize: 256,
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
        windowSize: number;
        startSec: number;
        endSec: number;
      },
      Transferable[]
    ];

    expect(payload.type).toBe("compute");
    expect(payload.audioData).toBeInstanceOf(Float32Array);
    expect(payload.audioData.length).toBe(4410);
    expect(payload.sampleRate).toBe(44100);
    expect(payload.windowSize).toBe(256);
    expect(payload.startSec).toBe(0);
    expect(payload.endSec).toBe(0.1);
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
      }),
    );

    const worker = workerInstances[0];
    const [payload, transfer] = vi.mocked(worker.postMessage).mock.calls[0] as [
      { audioData: Float32Array },
      Transferable[]
    ];

    expect(Array.isArray(transfer)).toBe(true);
    expect(transfer).toHaveLength(1);
    expect(transfer[0]).toBe(payload.audioData.buffer);
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
      (enabled: boolean) =>
        useSpectrogram({
          enabled,
          wsRef: wsRef as never,
          canvasRef: canvasRef as never,
        }),
      { initialProps: true },
    );

    const worker = workerInstances[0];
    rerender(false);

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
      }),
    );

    const worker = workerInstances[0];
    unmount();

    expect(worker.terminate).toHaveBeenCalled();
  });
});
