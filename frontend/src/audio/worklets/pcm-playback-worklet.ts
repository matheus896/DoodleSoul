/**
 * AudioWorkletProcessor for PCM playback with a ring buffer.
 *
 * Follows the proven pattern from the official ADK bidi-demo
 * (pcm-player-processor.js). Audio samples are written to a ring buffer
 * from the main thread via postMessage, and the audio rendering thread
 * pulls from the buffer at hardware-clock cadence.
 *
 * Messages accepted:
 *   - ArrayBuffer: Int16 PCM samples to enqueue
 *   - { command: "flush" }: clear the buffer (barge-in / interruption)
 *   - { command: "getMetrics" }: reply with current buffer metrics
 */
class PcmPlaybackProcessor extends AudioWorkletProcessor {
  private readonly bufferSize: number;
  private readonly buffer: Float32Array;
  private writeIdx = 0;
  private readIdx = 0;
  private count = 0;

  private underflowFrames = 0;
  private overflowSamples = 0;
  private totalWritten = 0;
  private totalRead = 0;

  constructor() {
    super();
    this.bufferSize = 24000 * 60;
    this.buffer = new Float32Array(this.bufferSize);

    this.port.onmessage = (event: MessageEvent) => {
      if (event.data && typeof event.data === "object" && "command" in event.data) {
        const cmd = (event.data as { command: string }).command;
        if (cmd === "flush") {
          this.readIdx = this.writeIdx;
          this.count = 0;
          return;
        }
        if (cmd === "getMetrics") {
          this.port.postMessage({
            type: "metrics",
            bufferedSamples: this.count,
            underflowFrames: this.underflowFrames,
            overflowSamples: this.overflowSamples,
            totalWritten: this.totalWritten,
            totalRead: this.totalRead,
          });
          return;
        }
        return;
      }

      const int16Samples = new Int16Array(event.data as ArrayBuffer);
      this.enqueue(int16Samples);
    };
  }

  private enqueue(samples: Int16Array): void {
    for (let i = 0; i < samples.length; i++) {
      this.buffer[this.writeIdx] = (samples[i] ?? 0) / 32768;
      this.writeIdx = (this.writeIdx + 1) % this.bufferSize;

      if (this.count === this.bufferSize) {
        this.readIdx = (this.readIdx + 1) % this.bufferSize;
        this.overflowSamples++;
      } else {
        this.count++;
      }
    }
    this.totalWritten += samples.length;
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
    const output = outputs[0];
    if (!output || output.length === 0) {
      return true;
    }
    const channel = output[0];
    if (!channel) {
      return true;
    }

    const frames = channel.length;

    if (this.count === 0) {
      this.underflowFrames++;
      for (let i = 0; i < frames; i++) {
        channel[i] = 0;
      }
      if (output.length > 1 && output[1]) {
        for (let i = 0; i < frames; i++) {
          output[1][i] = 0;
        }
      }
      return true;
    }

    const toRead = Math.min(this.count, frames);
    for (let i = 0; i < toRead; i++) {
      channel[i] = this.buffer[this.readIdx];
      this.readIdx = (this.readIdx + 1) % this.bufferSize;
    }
    this.count -= toRead;
    this.totalRead += toRead;

    for (let i = toRead; i < frames; i++) {
      channel[i] = 0;
    }

    if (output.length > 1 && output[1]) {
      for (let i = 0; i < frames; i++) {
        output[1][i] = channel[i];
      }
    }

    return true;
  }
}

registerProcessor("pcm-playback-worklet", PcmPlaybackProcessor);
