export interface PlayerMetrics {
  enqueuedChunks: number;
  pulledChunks: number;
  underflowCount: number;
  overflowDropCount: number;
  flushCount: number;
  peakBufferedSamples: number;
  totalEnqueuedSamples: number;
  totalPulledSamples: number;
}

export class Pcm24kPlayer {
  private queue: Int16Array[] = [];
  private queuedSamples = 0;
  private readonly maxBufferedSamples: number;
  private readonly catchupThreshold: number;

  private _enqueuedChunks = 0;
  private _pulledChunks = 0;
  private _underflowCount = 0;
  private _overflowDropCount = 0;
  private _flushCount = 0;
  private _peakBufferedSamples = 0;
  private _totalEnqueuedSamples = 0;
  private _totalPulledSamples = 0;

  constructor(maxBufferedSamples = 24000, catchupThreshold?: number) {
    this.maxBufferedSamples = maxBufferedSamples;
    this.catchupThreshold = catchupThreshold ?? maxBufferedSamples;
  }

  enqueue(chunk: Int16Array): void {
    if (chunk.length === 0) {
      return;
    }

    this.queue.push(chunk);
    this.queuedSamples += chunk.length;
    this._enqueuedChunks += 1;
    this._totalEnqueuedSamples += chunk.length;

    this._trimToThreshold();

    if (this.queuedSamples > this._peakBufferedSamples) {
      this._peakBufferedSamples = this.queuedSamples;
    }
  }

  private _trimToThreshold(): void {
    const limit = Math.min(this.maxBufferedSamples, this.catchupThreshold);
    while (this.queuedSamples > limit && this.queue.length > 0) {
      const dropped = this.queue.shift();
      if (dropped) {
        this.queuedSamples -= dropped.length;
        this._overflowDropCount += 1;
      }
    }
  }

  flush(): void {
    this.queue = [];
    this.queuedSamples = 0;
    this._flushCount += 1;
  }

  pullChunk(maxSamples = 2400): Int16Array {
    if (this.queue.length === 0 || maxSamples <= 0) {
      if (maxSamples > 0) {
        this._underflowCount += 1;
      }
      return new Int16Array(0);
    }

    this._pulledChunks += 1;

    const output = new Int16Array(Math.min(maxSamples, this.queuedSamples));
    let writeIndex = 0;

    while (writeIndex < output.length && this.queue.length > 0) {
      const current = this.queue[0];
      if (!current) {
        break;
      }
      const remaining = output.length - writeIndex;
      const take = Math.min(remaining, current.length);
      output.set(current.subarray(0, take), writeIndex);
      writeIndex += take;
      this.queuedSamples -= take;
      this._totalPulledSamples += take;

      if (take === current.length) {
        this.queue.shift();
      } else {
        this.queue[0] = current.subarray(take);
      }
    }

    return output;
  }

  getBufferedSampleCount(): number {
    return this.queuedSamples;
  }

  getMetrics(): PlayerMetrics {
    return {
      enqueuedChunks: this._enqueuedChunks,
      pulledChunks: this._pulledChunks,
      underflowCount: this._underflowCount,
      overflowDropCount: this._overflowDropCount,
      flushCount: this._flushCount,
      peakBufferedSamples: this._peakBufferedSamples,
      totalEnqueuedSamples: this._totalEnqueuedSamples,
      totalPulledSamples: this._totalPulledSamples,
    };
  }

  resetMetrics(): void {
    this._enqueuedChunks = 0;
    this._pulledChunks = 0;
    this._underflowCount = 0;
    this._overflowDropCount = 0;
    this._flushCount = 0;
    this._peakBufferedSamples = 0;
    this._totalEnqueuedSamples = 0;
    this._totalPulledSamples = 0;
  }
}
