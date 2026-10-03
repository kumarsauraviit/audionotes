"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Pause, Play, Volume2, VolumeX } from "lucide-react";

import { formatClock } from "@/lib/notes";
import { Button } from "@/components/ui/button";

/**
 * Waveform player backed by wavesurfer.js. If waveform decoding fails (e.g. a
 * cross-origin restriction) or stalls, it falls back to a native <audio>
 * element so playback always works. The known duration is shown immediately
 * from the backend, then corrected once the media metadata loads.
 */
export function AudioPlayer({
  src,
  filename,
  initialDuration,
  onTime,
  seek,
}: {
  src: string;
  filename: string;
  initialDuration?: number | null;
  onTime?: (t: number) => void;
  seek?: { t: number; nonce: number } | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const waveRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(initialDuration ?? 0);
  const [speed, setSpeed] = useState(1);
  const [isMuted, setIsMuted] = useState(false);

  useEffect(() => {
    if (!src) return;
    let destroyed = false;
    let wave: any;
    setFailed(false);
    setLoading(true);
    setIsPlaying(false);
    setCurrent(0);
    setDuration(initialDuration ?? 0);
    onTime?.(0);

    import("wavesurfer.js")
      .then(({ default: WaveSurfer }) => {
        if (destroyed || !containerRef.current) return;
        try {
          wave = WaveSurfer.create({
            container: containerRef.current,
            url: src,
            height: 46,
            waveColor: "#c6d2cd",
            progressColor: "#0f6b62",
            cursorColor: "#0b544d",
            cursorWidth: 1,
            barWidth: 2,
            barGap: 1,
            barRadius: 2,
            normalize: true,
          });
          waveRef.current = wave;
          wave.on("ready", (value: number) => {
            setLoading(false);
            if (value) setDuration(value);
          });
          wave.on("decode", () => setLoading(false));
          wave.on("timeupdate", (value: number) => {
            setCurrent(value);
            onTime?.(value);
          });
          wave.on("play", () => setIsPlaying(true));
          wave.on("pause", () => setIsPlaying(false));
          wave.on("finish", () => setIsPlaying(false));
          // Only fall back to the native player on a genuine decode/fetch error.
          wave.on("error", () => setFailed(true));
        } catch {
          setFailed(true);
        }
      })
      .catch(() => setFailed(true));

    return () => {
      destroyed = true;
      try {
        wave?.destroy();
      } catch {
        // ignore teardown races
      }
      waveRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  useEffect(() => {
    if (!seek) return;
    if (waveRef.current && !failed) {
      try {
        waveRef.current.setTime(seek.t);
        void waveRef.current.play();
      } catch {
        // ignore
      }
    } else if (audioRef.current) {
      audioRef.current.currentTime = seek.t;
      void audioRef.current.play();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seek?.nonce]);

  const togglePlay = () => {
    if (waveRef.current && !failed) {
      void waveRef.current.playPause();
    } else if (audioRef.current) {
      if (audioRef.current.paused) void audioRef.current.play();
      else audioRef.current.pause();
    }
  };

  const cycleSpeed = () => {
    const speeds = [1, 1.25, 1.5, 2];
    const next = speeds[(speeds.indexOf(speed) + 1) % speeds.length];
    setSpeed(next);
    if (waveRef.current && !failed) waveRef.current.setPlaybackRate(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  };

  const toggleMute = () => {
    const next = !isMuted;
    setIsMuted(next);
    if (waveRef.current && !failed) waveRef.current.setMuted(next);
    if (audioRef.current) audioRef.current.muted = next;
  };

  return (
    <div className="rounded-lg border border-border bg-paper p-4">
      <audio
        ref={audioRef}
        src={failed ? src : undefined}
        preload="metadata"
        onTimeUpdate={() => {
          if (audioRef.current) {
            setCurrent(audioRef.current.currentTime);
            onTime?.(audioRef.current.currentTime);
          }
        }}
        onLoadedMetadata={() => {
          const value = audioRef.current?.duration;
          if (value && Number.isFinite(value)) setDuration(value);
        }}
        onDurationChange={() => {
          const value = audioRef.current?.duration;
          if (value && Number.isFinite(value)) setDuration(value);
        }}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
        controls={failed}
        className={failed ? "mb-3 w-full" : "hidden"}
      />
      {!failed && (
        <div className="relative mb-3" style={{ minHeight: 46 }}>
          <div ref={containerRef} className={loading ? "opacity-0" : "transition-opacity duration-300"} />
          {loading && (
            <div
              className="absolute inset-0 flex items-center gap-[3px] overflow-hidden"
              aria-hidden="true"
            >
              {Array.from({ length: 48 }).map((_, index) => (
                <span
                  key={index}
                  className="w-[3px] flex-1 animate-pulse rounded-full bg-line"
                  style={{
                    height: `${20 + Math.abs(Math.sin(index * 1.7)) * 70}%`,
                    animationDelay: `${(index % 8) * 90}ms`,
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button size="icon" onClick={togglePlay} aria-label={isPlaying ? "Pause audio" : "Play audio"} className="rounded-full">
          {isPlaying ? <Pause size={16} /> : <Play size={16} className="translate-x-px" />}
        </Button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={filename}>
            {filename}
          </p>
          <p className="text-xs tabular-nums text-muted-foreground">
            {formatClock(current)} / {duration ? formatClock(duration) : "--:--"}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={cycleSpeed} title="Change playback speed">
          {speed}×
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={toggleMute} aria-label={isMuted ? "Unmute" : "Mute"}>
          {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
        </Button>
        <a
          href={src}
          download={filename}
          className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-ink"
          title="Download audio file"
          aria-label="Download audio file"
        >
          <Download size={14} />
        </a>
      </div>
    </div>
  );
}
