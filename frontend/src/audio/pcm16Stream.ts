export type Pcm16DecodeResult = {
  samples: Int16Array;
  carry: Uint8Array;
};

export function decodePcm16StreamChunk(
  chunk: ArrayBuffer,
  carry: Uint8Array = new Uint8Array(0)
): Pcm16DecodeResult {
  const incoming = new Uint8Array(chunk);
  const mergedLength = carry.length + incoming.length;
  const merged = new Uint8Array(mergedLength);
  merged.set(carry, 0);
  merged.set(incoming, carry.length);

  const evenLength = merged.length - (merged.length % 2);
  const nextCarry = merged.slice(evenLength);
  const sampleCount = evenLength / 2;
  const samples = new Int16Array(sampleCount);
  const view = new DataView(merged.buffer, merged.byteOffset, evenLength);

  for (let index = 0; index < sampleCount; index += 1) {
    samples[index] = view.getInt16(index * 2, true);
  }

  return {
    samples,
    carry: nextCarry,
  };
}
