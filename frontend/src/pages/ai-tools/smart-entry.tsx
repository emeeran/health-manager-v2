import { SmartEntryBar } from "../../components/home/smart-entry-bar";
import { AiToolPage } from "../../components/ai-tools/ai-tool-page";

/** Smart entry with a member picked, so voice dictation is available. */
export default function SmartEntryPage() {
  return (
    <AiToolPage title="Smart entry">
      {(memberId) => <SmartEntryBar key={memberId} memberId={memberId} />}
    </AiToolPage>
  );
}
