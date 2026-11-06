/**
 * English dictionary — the source of truth for the i18n type.
 *
 * Every other language file must satisfy `Dictionary`, so a missing or
 * misspelled key is a compile error, not a runtime blank string.
 *
 * Pilot scope (Phase 12): nav labels, app-layout banners, and settings
 * headings only. The rest of the app is intentionally still hardcoded
 * English; new surfaces adopt the dictionary as they are touched.
 */
export const en = {
  nav: {
    home: "Home",
    members: "Members",
    providers: "Providers",
    medicines: "Medicines",
    dataHygiene: "Data hygiene",
    chat: "Chat",
    aiTools: "AI tools",
    settings: "Settings",
  },
  header: {
    account: "Account",
    logout: "Logout",
  },
  offline: {
    banner: "Offline — showing cached data",
  },
  update: {
    available: "Update available — reload to get the new version.",
    reload: "Reload",
    dismiss: "Dismiss",
  },
  settings: {
    title: "Settings",
    subtitle:
      "Account security, household administration, and data management.",
    tabs: {
      general: "General",
      household: "Household",
      aiProviders: "AI Providers",
      twoFactor: "Two-factor",
      notifications: "Notifications",
      data: "Data",
    },
    general: {
      heading: "General",
      appearance: "Appearance",
      theme: "Theme",
      themeLight: "Light",
      themeSepia: "Sepia",
      themeGrey: "Grey",
      themeDark: "Dark",
      language: "Language",
      languageHint:
        "Applies to navigation and settings; more surfaces over time.",
    },
    data: {
      heading: "Data",
      integrity: "Database integrity",
      integrityOk: "Database is healthy",
      integrityProblems: "Integrity problems detected",
      engine: "Engine",
      orphanCount: "Orphaned rows",
      noOrphans: "No orphaned references found.",
      scanDuration: "Scan completed in",
      attachmentsChecked: "attachments checked",
      attachmentsMissing: "missing files",
    },
  },
};

export type Dictionary = typeof en;
