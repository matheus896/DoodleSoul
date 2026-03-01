/**
 * Lock-free ring buffer for PCM audio playback.
 *
 * Accepts Int16 samples on the write side and produces Float32 samples on the
 * read side.  Designed for the same algorithm used inside the playback
 * AudioWorkletProcessor so that the same logic can be unit-tested outside the
 * worklet runtime.
 *
 * Overflow policy: overwrite oldest samples (write pointer pushes read pointer).
 * Underflow policy: output silence (zeros).
 */
export class PcmRingBuffer {
  private readonly size: number;
  private readonly buffer: Float32Array;
  private writeIdx = 0;
  private readIdx = 0;
  private count = 0;

  constructor(capacity: number) {
    this.size = capacity;
    this.buffer = new Float32Array(capacity);
  }

  write(samples: Int16Array): void {
    for (let i = 0; i < samples.length; i++) {
      this.buffer[this.writeIdx] = (samples[i] ?? 0) / 32768;
      this.writeIdx = (this.writeIdx + 1) % this.size;

      if (this.count === this.size) {
        this.readIdx = (this.readIdx + 1) % this.size;
      } else {
        this.count++;
      }
    }
  }

  /**
   * Read up to `output.length` samples into the provided buffer.
   * Returns the number of samples actually read (0 on underflow).
   * Remaining positions in `output` are filled with silence.
   */
  read(output: Float32Array): number {
    const available = this.count;
    const toRead = Math.min(available, output.length);

    for (let i = 0; i < toRead; i++) {
      output[i] = this.buffer[this.readIdx];
      this.readIdx = (this.readIdx + 1) % this.size;
    }
    this.count -= toRead;

    for (let i = toRead; i < output.length; i++) {
      output[i] = 0;
    }

    return toRead;
  }

  flush(): void {
    this.readIdx = this.writeIdx;
    this.count = 0;
  }

  bufferedSamples(): number {
    return this.count;
  }
}
