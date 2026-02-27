export function floatToPcm16Sample(sample: number): number {
  const clamped = Math.max(-1, Math.min(1, sample));
  return clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
}

export function downsampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate <= 0) {
    throw new Error("inputRate must be > 0");
  }

  const targetRate = 16000;
  if (input.length === 0) {
    return new Float32Array(0);
  }

  const ratio = inputRate / targetRate;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Float32Array(outputLength);

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const sourceIndex = Math.floor(outputIndex * ratio);
    output[outputIndex] = input[sourceIndex] ?? 0;
  }

  return output;
}

export function toPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    output[index] = floatToPcm16Sample(input[index] ?? 0);
  }
  return output;
}

export function downsampleTo16kPcm16(input: Float32Array, inputRate: number): Int16Array {
  return toPcm16(downsampleTo16k(input, inputRate));
}

export function encodePcm16Chunk(input: Float32Array, inputRate: number): ArrayBuffer {
  const pcm16 = downsampleTo16kPcm16(input, inputRate);
  return pcm16.buffer.slice(0);
}
