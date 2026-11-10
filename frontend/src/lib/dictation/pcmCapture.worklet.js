/* global sampleRate, registerProcessor, AudioWorkletProcessor */
/**
 * Microphone capture for voice dictation: mono PCM16 at the provider's rate.
 *
 * Downsampling averages the input samples that fall into each output sample
 * (a box low-pass), which keeps speech intelligible without the aliasing of
 * plain decimation. Posts { pcm: ArrayBuffer } every 100 ms of output audio
 * and { level } (RMS, 0–1) about every 50 ms for the recording waveform.
 */
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const targetRate = options.processorOptions.targetRate;
    this.step = sampleRate / targetRate;
    this.chunk = new Int16Array(Math.round(targetRate / 10));
    this.filled = 0;
    this.position = 0;
    this.sum = 0;
    this.count = 0;
    this.levelSum = 0;
    this.levelCount = 0;
    this.levelEvery = Math.round(sampleRate / 20);
    // "flush" sends the partial last chunk so stopping loses no audio.
    this.port.onmessage = (event) => {
      if (event.data !== "flush") return;
      const pcm = this.chunk.slice(0, this.filled).buffer;
      this.filled = 0;
      this.port.postMessage({ pcm, flushed: true }, [pcm]);
    };
  }

  process(inputs) {
    const channels = inputs[0];
    if (!channels || channels.length === 0) return true;
    const frames = channels[0].length;
    for (let i = 0; i < frames; i += 1) {
      let sample = 0;
      for (let c = 0; c < channels.length; c += 1) sample += channels[c][i];
      sample /= channels.length;
      this.levelSum += sample * sample;
      this.levelCount += 1;
      if (this.levelCount >= this.levelEvery) {
        this.port.postMessage({ level: Math.sqrt(this.levelSum / this.levelCount) });
        this.levelSum = 0;
        this.levelCount = 0;
      }
      this.sum += sample;
      this.count += 1;
      this.position += 1;
      if (this.position >= this.step) {
        this.position -= this.step;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.chunk[this.filled] = value < 0 ? value * 0x8000 : value * 0x7fff;
        this.filled += 1;
        this.sum = 0;
        this.count = 0;
        if (this.filled === this.chunk.length) {
          const pcm = this.chunk.slice().buffer;
          this.port.postMessage({ pcm }, [pcm]);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pwc-pcm-capture", PcmCaptureProcessor);
