import { AiToolPage } from "../../components/ai-tools/ai-tool-page";
import { DrugInteractionsView } from "../../components/ai-tools/drug-interactions-view";

export default function DrugInteractionsPage() {
  return (
    <AiToolPage title="Drug interactions">
      {(memberId) => <DrugInteractionsView memberId={memberId} />}
    </AiToolPage>
  );
}
