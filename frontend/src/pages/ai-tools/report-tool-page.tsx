import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import { InsightTool } from "../../components/ai-tools/insight-tool";
import { INSIGHT_KIND_META, type InsightKind } from "../../lib/types/insight";

/**
 * Shared page body for the kind-specific report tools (smart report,
 * consultant note, pre-consultation, consolidated, medication report).
 */
export default function ReportToolPage({ kind }: { kind: InsightKind }) {
  const meta = INSIGHT_KIND_META[kind];
  return (
    <AiToolPage title={meta.label}>
      {(memberId) => (
        <InsightTool
          memberId={memberId}
          kind={kind}
          description={meta.description}
        />
      )}
    </AiToolPage>
  );
}
