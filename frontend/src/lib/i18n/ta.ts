import type { Dictionary } from "./en";

/** Tamil dictionary — keys must mirror en.ts (type-checked). */
export const ta: Dictionary = {
  nav: {
    home: "முகப்பு",
    members: "உறுப்பினர்கள்",
    providers: "மருத்துவர்கள்",
    medicines: "மருந்துகள்",
    dataHygiene: "தரவு சுகாதாரம்",
    chat: "அரட்டை",
    aiTools: "AI கருவிகள்",
    settings: "அமைப்புகள்",
  },
  header: {
    account: "கணக்கு",
    logout: "வெளியேறு",
  },
  offline: {
    banner: "இணைப்பில்லை — சேமித்த தரவு காட்டப்படுகிறது",
  },
  update: {
    available: "புதுப்பிப்பு உள்ளது — புதிய பதிப்பைப் பெற மீண்டும் ஏற்றவும்.",
    reload: "மீண்டும் ஏற்று",
    dismiss: "நிராகரி",
  },
  settings: {
    title: "அமைப்புகள்",
    subtitle: "கணக்கு பாதுகாப்பு, குடும்ப நிர்வாகம் மற்றும் தரவு மேலாண்மை.",
    tabs: {
      general: "பொது",
      household: "குடும்பம்",
      aiProviders: "AI வழங்குநர்கள்",
      twoFactor: "இரண்டு-காரணி",
      notifications: "அறிவிப்புகள்",
      data: "தரவு",
    },
    general: {
      heading: "பொது",
      appearance: "தோற்றம்",
      theme: "தீம்",
      themeLight: "ஒளி",
      themeSepia: "செபியா",
      themeGrey: "சாம்பல்",
      themeDark: "இருள்",
      language: "மொழி",
      languageHint:
        "வழிசெலுத்தல் மற்றும் அமைப்புகளுக்குப் பயன்படும்; படிப்படியாக மற்ற பகுதிகளுக்கும்.",
    },
    data: {
      heading: "தரவு",
      integrity: "தரவுத்தள ஒருமைப்பாடு",
      integrityOk: "தரவுத்தள ஆரோக்கியமாக உள்ளது",
      integrityProblems: "ஒருமைப்பாட்டு சிக்கல்கள் கண்டறியப்பட்டன",
      engine: "இயந்திரம்",
      orphanCount: "துணைப்பிரிவில்லாத வரிசைகள்",
      noOrphans: "துணைப்பிரிவில்லாத குறிப்புகள் இல்லை.",
      scanDuration: "ஸ்கேன் முடிந்தது",
      attachmentsChecked: "இணைப்புகள் சரிபார்க்கப்பட்டன",
      attachmentsMissing: "காணாமல் போன கோப்புகள்",
    },
  },
};
