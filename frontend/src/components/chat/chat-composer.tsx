import { Loader2, PanelRight, Send } from "lucide-react";
import type { FormEvent } from "react";
import { INPUT_CLASS, cn } from "../../lib/utils";

/** Message input row: textarea (Enter sends), reference-lookup toggle, send. */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  streaming,
  lookupOpen,
  onToggleLookup,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  streaming: boolean;
  lookupOpen: boolean;
  onToggleLookup: () => void;
}) {
  return (
    <form onSubmit={onSubmit} className="flex items-end gap-2 p-4">
      <label className="flex-1 space-y-1.5">
        <span className="sr-only">Message</span>
        <textarea
          rows={2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="Ask a question… (Enter to send, Shift+Enter for a new line)"
          disabled={streaming}
          className={cn(INPUT_CLASS, "resize-none")}
        />
      </label>
      <button
        type="button"
        onClick={onToggleLookup}
        aria-label={
          lookupOpen ? "Hide reference lookup" : "Open reference lookup"
        }
        aria-pressed={lookupOpen}
        title="Reference lookup"
        className={`flex size-10 shrink-0 items-center justify-center rounded-lg border transition-colors ${
          lookupOpen
            ? "border-primary/50 bg-primary/10 text-primary"
            : "border-border bg-background text-muted-foreground hover:text-foreground"
        }`}
      >
        <PanelRight className="size-4" aria-hidden />
      </button>
      <button
        type="submit"
        disabled={streaming || !value.trim()}
        className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
        aria-label="Send message"
      >
        {streaming ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Send className="size-4" aria-hidden />
        )}
      </button>
    </form>
  );
}
