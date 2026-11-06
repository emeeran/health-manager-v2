import { Outlet } from "react-router-dom";
import { ErrorBanner } from "../components/ErrorBanner";
import { Header } from "../components/layout/header";
import { OfflineBanner } from "../components/layout/offline-banner";
import { UpdateToast } from "../components/layout/update-toast";
import { Sidebar } from "../components/layout/sidebar";
import { useEscapeNavigation } from "../hooks/use-escape-navigation";
import { I18nProvider } from "../lib/i18n";

export default function AppLayout() {
  useEscapeNavigation();

  return (
    <I18nProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <OfflineBanner />
          <UpdateToast />
          <ErrorBanner />
          <main className="flex-1 overflow-y-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </I18nProvider>
  );
}
