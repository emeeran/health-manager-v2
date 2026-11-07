import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import { InsightTool } from "../../components/ai-tools/insight-tool";

/**
 * Pre-consultation note (A5): structured kind — the model fills a validated
 * schema, the page renders the note field-by-field with print + WhatsApp
 * export (see A5NoteView, wired through InsightTool's structured mode).
 */
export default function PreConsultationPage() {
  return (
    <AiToolPage title="Pre-consultation notes">
      {(memberId) => (
        <InsightTool
          memberId={memberId}
          kind="pre_consultation"
          structured
          confirmBeforeRun
          description="One-page note to carry to the doctor — print on A5 or share as text"
        />
      )}
    </AiToolPage>
  );
}
