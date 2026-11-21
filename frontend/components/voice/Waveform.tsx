"use client";
import { useEffect, useRef } from "react";

interface WaveformProps {
  /** Read every frame, so the source can switch between mic and agent without remounting. */
  getAnalyser: () => AnalyserNode | null;
  label: string;
}

/** Live time-domain trace from a Web Audio AnalyserNode. Flat line when there is no audio. */
export function Waveform({ getAnalyser, label }: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let frame = 0;
    let samples = new Uint8Array(0);

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth * dpr;
      const height = canvas.clientHeight * dpr;
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      ctx.clearRect(0, 0, width, height);
      ctx.lineWidth = 2 * dpr;
      ctx.strokeStyle = getComputedStyle(canvas).color;
      ctx.beginPath();
      const analyser = getAnalyser();
      if (analyser) {
        if (samples.length !== analyser.fftSize) samples = new Uint8Array(analyser.fftSize);
        analyser.getByteTimeDomainData(samples);
        for (let i = 0; i < samples.length; i++) {
          const x = (i / (samples.length - 1)) * width;
          const y = (samples[i] / 255) * height;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      } else {
        ctx.moveTo(0, height / 2);
        ctx.lineTo(width, height / 2);
      }
      ctx.stroke();
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [getAnalyser]);

  return <canvas ref={canvasRef} role="img" aria-label={label} className="h-24 w-full text-accent" />;
}
