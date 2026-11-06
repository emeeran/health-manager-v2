import type { Dictionary } from "./en";

/** Hindi dictionary — keys must mirror en.ts (type-checked). */
export const hi: Dictionary = {
  nav: {
    home: "होम",
    members: "सदस्य",
    providers: "डॉक्टर",
    medicines: "दवाइयाँ",
    dataHygiene: "डेटा स्वच्छता",
    chat: "चैट",
    aiTools: "AI उपकरण",
    settings: "सेटिंग्स",
  },
  header: {
    account: "खाता",
    logout: "लॉग आउट",
  },
  offline: {
    banner: "ऑफ़लाइन — सहेजा गया डेटा दिख रहा है",
  },
  update: {
    available: "अपडेट उपलब्ध है — नया संस्करण पाने के लिए पुनः लोड करें।",
    reload: "पुनः लोड",
    dismiss: "हटाएँ",
  },
  settings: {
    title: "सेटिंग्स",
    subtitle: "खाता सुरक्षा, परिवार प्रशासन और डेटा प्रबंधन।",
    tabs: {
      general: "सामान्य",
      household: "परिवार",
      aiProviders: "AI प्रदाता",
      twoFactor: "दो-चरणीय",
      notifications: "सूचनाएँ",
      data: "डेटा",
    },
    general: {
      heading: "सामान्य",
      appearance: "रूप",
      theme: "थीम",
      themeLight: "लाइट",
      themeSepia: "सेपिया",
      themeGrey: "ग्रे",
      themeDark: "डार्क",
      language: "भाषा",
      languageHint:
        "नेविगेशन और सेटिंग्स पर लागू; समय के साथ अन्य हिस्सों में भी।",
    },
    data: {
      heading: "डेटा",
      integrity: "डेटाबेस अखंडता",
      integrityOk: "डेटाबेस स्वस्थ है",
      integrityProblems: "अखंडता समस्याएँ मिलीं",
      engine: "इंजन",
      orphanCount: "अनाथ पंक्तियाँ",
      noOrphans: "कोई अनाथ संदर्भ नहीं मिले।",
      scanDuration: "स्कैन पूर्ण हुआ",
      attachmentsChecked: "अटैचमेंट जाँचे गए",
      attachmentsMissing: "गुम फ़ाइलें",
    },
  },
};
