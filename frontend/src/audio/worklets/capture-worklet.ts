class CaptureWorkletProcessor extends AudioWorkletProcessor {
  private readonly targetRate = 16000;
  private readonly chunkSamples = 320;
  private sourceBuffer: number[] = [];

  private downsample(input: Float32Array): Float32Array {
    const ratio = sampleRate / this.targetRate;
    const outputLength = Math.floor(input.length / ratio);
    const output = new Float32Array(outputLength);

    for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
      const sourceIndex = Math.floor(outputIndex * ratio);
      output[outputIndex] = input[sourceIndex] ?? 0;
    }

    return output;
  }

  private toPcm16(input: Float32Array): Int16Array {
    const output = new Int16Array(input.length);
    for (let index = 0; index < input.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, input[index] ?? 0));
      output[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
    }
    return output;
  }

  process(inputs: Float32Array[][]): boolean {
    const input = inputs[0]?.[0];
    if (!input || input.length === 0) {
      return true;
    }

    for (let index = 0; index < input.length; index += 1) {
      this.sourceBuffer.push(input[index] ?? 0);
    }

    const sourceSamplesPerChunk = Math.ceil((sampleRate / this.targetRate) * this.chunkSamples);

    while (this.sourceBuffer.length >= sourceSamplesPerChunk) {
      const sourceChunk = this.sourceBuffer.splice(0, sourceSamplesPerChunk);
      const downsampled = this.downsample(Float32Array.from(sourceChunk));
      const pcm16 = this.toPcm16(downsampled);

      this.port.postMessage(
        {
          kind: "pcm16",
          sampleRate: this.targetRate,
          channels: 1,
          encoding: "pcm_s16le",
          data: pcm16.buffer
        },
        [pcm16.buffer]
      );
    }

    return true;
  }
}

registerProcessor("capture-worklet", CaptureWorkletProcessor);
