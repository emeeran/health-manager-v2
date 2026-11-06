import { lazy, Suspense } from "react";
import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";

const Home = lazy(() => import("./pages/home"));
const DataHygiene = lazy(() => import("./pages/data-hygiene"));
const Members = lazy(() => import("./pages/members"));
const MemberDetail = lazy(() => import("./pages/member-detail"));
const MemberEmergency = lazy(() => import("./pages/member-emergency"));
const Providers = lazy(() => import("./pages/providers"));
const RecordDetail = lazy(() => import("./pages/record-detail"));
const Medicines = lazy(() => import("./pages/medicines"));
const MedicineSchedule = lazy(() => import("./pages/medicine-schedule"));
const Login = lazy(() => import("./pages/login"));
const Register = lazy(() => import("./pages/register"));
const Chat = lazy(() => import("./pages/chat"));
const Settings = lazy(() => import("./pages/settings"));
const PublicShare = lazy(() => import("./pages/public-share"));
const AiToolsHub = lazy(() => import("./pages/ai-tools/hub"));
const HealthInsightsPage = lazy(
  () => import("./pages/ai-tools/health-insights"),
);
const SmartReportPage = lazy(() => import("./pages/ai-tools/smart-report"));
const ConsultantNotePage = lazy(
  () => import("./pages/ai-tools/consultant-note"),
);
const PreConsultationPage = lazy(
  () => import("./pages/ai-tools/pre-consultation"),
);
const ConsolidatedReportPage = lazy(
  () => import("./pages/ai-tools/consolidated-report"),
);
const MedicationReportPage = lazy(
  () => import("./pages/ai-tools/medication-report"),
);
const DrugInteractionsPage = lazy(
  () => import("./pages/ai-tools/drug-interactions"),
);
const SmartEntryPage = lazy(() => import("./pages/ai-tools/smart-entry"));
const SummariesPage = lazy(() => import("./pages/ai-tools/summaries"));

function Page({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="p-6 text-sm text-muted-foreground">Loading…</div>
      }
    >
      {children}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      {
        path: "/",
        element: (
          <Page>
            <Home />
          </Page>
        ),
      },
      {
        path: "/members",
        element: (
          <Page>
            <Members />
          </Page>
        ),
      },
      {
        path: "/data-hygiene",
        element: (
          <Page>
            <DataHygiene />
          </Page>
        ),
      },
      {
        path: "/members/:memberId",
        element: (
          <Page>
            <MemberDetail />
          </Page>
        ),
      },
      {
        path: "/members/:memberId/emergency",
        element: (
          <Page>
            <MemberEmergency />
          </Page>
        ),
      },
      {
        path: "/providers",
        element: (
          <Page>
            <Providers />
          </Page>
        ),
      },
      {
        path: "/chat",
        element: (
          <Page>
            <Chat />
          </Page>
        ),
      },
      {
        path: "/settings",
        element: (
          <Page>
            <Settings />
          </Page>
        ),
      },
      {
        path: "/medicines",
        element: (
          <Page>
            <Medicines />
          </Page>
        ),
      },
      {
        path: "/ai-tools",
        element: (
          <Page>
            <AiToolsHub />
          </Page>
        ),
      },
      {
        path: "/ai-tools/health-insights",
        element: (
          <Page>
            <HealthInsightsPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/smart-report",
        element: (
          <Page>
            <SmartReportPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/consultant-note",
        element: (
          <Page>
            <ConsultantNotePage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/pre-consultation",
        element: (
          <Page>
            <PreConsultationPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/consolidated-report",
        element: (
          <Page>
            <ConsolidatedReportPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/medication-report",
        element: (
          <Page>
            <MedicationReportPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/drug-interactions",
        element: (
          <Page>
            <DrugInteractionsPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/smart-entry",
        element: (
          <Page>
            <SmartEntryPage />
          </Page>
        ),
      },
      {
        path: "/ai-tools/summaries",
        element: (
          <Page>
            <SummariesPage />
          </Page>
        ),
      },
      {
        path: "/members/:memberId/records/:recordId",
        element: (
          <Page>
            <RecordDetail />
          </Page>
        ),
      },
    ],
  },
  {
    // Outside the app layout: printing must not pick up sidebar/header chrome.
    path: "/members/:memberId/medicine-schedule",
    element: (
      <Page>
        <MedicineSchedule />
      </Page>
    ),
  },
  {
    path: "/login",
    element: (
      <Page>
        <Login />
      </Page>
    ),
  },
  {
    // Outside the auth guard: share-link visitors have no account and must
    // never be redirected to /login.
    path: "/public/share/:token",
    element: (
      <Page>
        <PublicShare />
      </Page>
    ),
  },
  {
    path: "/register",
    element: (
      <Page>
        <Register />
      </Page>
    ),
  },
]);
