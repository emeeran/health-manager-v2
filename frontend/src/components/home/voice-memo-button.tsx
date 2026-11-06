import { Loader2, Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { transcribeVoiceMemo } from "../../lib/api/voice-memos";

/**
 * Mic button for the smart-entry bar: records via MediaRecorder, sends the
 * clip to POST /members/{id}/voice-memos (local faster-whisper), and calls
 * `onTranscript` with the text. Nothing is stored server-side.
 *
 * A 501 (faster-whisper not installed on the server) surfaces as an inline
 * hint instead of an error — the feature is off, not broken.
 */
export function VoiceMemoButton({
  memberId,
  onTranscript,
}: {
  memberId: string;
  onTranscript: (text: string) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    return () => {
      recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function start() {
    setHint(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        recorder.stream.getTracks().forEach((track) => track.stop());
        void finish(new Blob(chunksRef.current, { type: recorder.mimeType }));
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setHint("Microphone unavailable — check browser permissions.");
    }
  }

  function stop() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  async function finish(blob: Blob) {
    if (blob.size === 0) {
      setHint("Nothing recorded — try again.");
      return;
    }
    setTranscribing(true);
    try {
      const { text } = await transcribeVoiceMemo(memberId, blob);
      onTranscript(text);
    } catch (err) {
      setHint(transcribeHint(err));
    } finally {
      setTranscribing(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => (recording ? stop() : void start())}
        disabled={transcribing}
        aria-label={recording ? "Stop recording" : "Record a voice memo"}
        title={recording ? "Stop recording" : "Dictate a health event"}
        className={`flex size-9 items-center justify-center rounded-lg border transition-colors disabled:opacity-60 ${
          recording
            ? "border-danger/40 bg-danger/10 text-danger"
            : "border-border bg-background text-muted-foreground hover:text-foreground"
        }`}
      >
        {transcribing ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : recording ? (
          <Square className="size-4" aria-hidden />
        ) : (
          <Mic className="size-4" aria-hidden />
        )}
      </button>
      {recording && (
        <span className="flex items-center gap-1 text-xs text-danger">
          <span
            className="size-2 animate-pulse rounded-full bg-danger"
            aria-hidden
          />
          Recording…
        </span>
      )}
      {transcribing && (
        <span className="text-xs text-muted-foreground">Transcribing…</span>
      )}
      {hint && (
        <span
          role="alert"
          className="rounded-lg bg-warning/15 px-2 py-0.5 text-xs text-warning-foreground"
        >
          {hint}
        </span>
      )}
    </div>
  );
}

/** Human hint for a transcription failure, e.g. missing faster-whisper. */
export function transcribeHint(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  if (message.toLowerCase().includes("faster-whisper")) {
    return "Voice transcription is off on this server — install faster-whisper (uv add 'faster-whisper').";
  }
  return message || "Transcription failed — try again.";
}
