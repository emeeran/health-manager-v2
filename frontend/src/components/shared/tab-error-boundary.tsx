import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCcw } from "lucide-react";

/**
 * Per-tab error boundary: a render crash in one member tab shows a scoped
 * error card with a remount action instead of blanking the whole page.
 */
export class TabErrorBoundary extends Component<
  { children: ReactNode; label: string },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(
      `[${this.props.label} tab] render crash:`,
      error,
      info.componentStack,
    );
  }

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="space-y-2 rounded-xl border border-danger/40 bg-danger/5 p-4"
        >
          <p className="text-sm font-medium">
            The {this.props.label} tab crashed — the rest of the page is
            unaffected.
          </p>
          <p className="text-xs text-muted-foreground">
            {this.state.error.message}
          </p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
          >
            <RotateCcw className="size-4" aria-hidden />
            Reload tab
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
