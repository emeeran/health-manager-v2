import { Settings as SettingsIcon } from "lucide-react";
import { useState } from "react";
import { AiProvidersSection } from "../components/settings/ai-providers-section";
import { DataSection } from "../components/settings/data-section";
import { GeneralSection } from "../components/settings/general-section";
import { HouseholdSection } from "../components/settings/household-section";
import { NotificationsSection } from "../components/settings/notifications-section";
import { TwoFactorSection } from "../components/settings/two-factor-section";
import { useI18n } from "../lib/i18n";
import { cn } from "../lib/utils";

const TABS = [
  "general",
  "household",
  "aiProviders",
  "twoFactor",
  "notifications",
  "data",
] as const;

type Tab = (typeof TABS)[number];

export default function Settings() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("general");

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <SettingsIcon className="size-6 text-primary" aria-hidden />
          {t.settings.title}
        </h1>
        <p className="text-sm text-muted-foreground">{t.settings.subtitle}</p>
      </div>

      <div
        role="tablist"
        aria-label={t.settings.title}
        className="flex flex-wrap gap-1 border-b border-border"
      >
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              "-mb-px rounded-t-lg border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === value
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.settings.tabs[value]}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === "general" && <GeneralSection />}
        {tab === "household" && <HouseholdSection />}
        {tab === "aiProviders" && <AiProvidersSection />}
        {tab === "twoFactor" && <TwoFactorSection />}
        {tab === "notifications" && <NotificationsSection />}
        {tab === "data" && <DataSection />}
      </div>
    </div>
  );
}
