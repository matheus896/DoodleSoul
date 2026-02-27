export class Pcm24kPlayer {
  private queue: Int16Array[] = [];
  private queuedSamples = 0;
  private readonly maxBufferedSamples: number;

  constructor(maxBufferedSamples = 24000) {
    this.maxBufferedSamples = maxBufferedSamples;
  }

  enqueue(chunk: Int16Array): void {
    if (chunk.length === 0) {
      return;
    }

    this.queue.push(chunk);
    this.queuedSamples += chunk.length;

    while (this.queuedSamples > this.maxBufferedSamples && this.queue.length > 0) {
      const dropped = this.queue.shift();
      this.queuedSamples -= dropped?.length ?? 0;
    }
  }

  flush(): void {
    this.queue = [];
    this.queuedSamples = 0;
  }

  pullChunk(maxSamples = 2400): Int16Array {
    if (this.queue.length === 0 || maxSamples <= 0) {
      return new Int16Array(0);
    }

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
}
