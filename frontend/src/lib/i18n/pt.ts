import type { Dictionary } from "./en";

/**
 * Portuguese pilot translation. `Dictionary` (derived from en.ts) forces this
 * object to stay key-for-key identical with the English source.
 */
export const pt: Dictionary = {
  nav: {
    home: "Início",
    members: "Membros",
    providers: "Médicos",
    medicines: "Medicamentos",
    dataHygiene: "Higiene de dados",
    chat: "Conversa",
    aiTools: "Ferramentas de IA",
    settings: "Configurações",
  },
  header: {
    account: "Conta",
    logout: "Terminar sessão",
  },
  offline: {
    banner: "Sem ligação — a mostrar dados em cache",
  },
  update: {
    available: "Atualização disponível — recarregue para obter a nova versão.",
    reload: "Recarregar",
    dismiss: "Dispensar",
  },
  settings: {
    title: "Configurações",
    subtitle:
      "Segurança da conta, administração do agregado e gestão de dados.",
    tabs: {
      general: "Geral",
      household: "Agregado",
      aiProviders: "Provedores de IA",
      twoFactor: "Dois fatores",
      notifications: "Notificações",
      data: "Dados",
    },
    general: {
      heading: "Geral",
      appearance: "Aparência",
      theme: "Tema",
      themeLight: "Claro",
      themeSepia: "Sépia",
      themeGrey: "Cinza",
      themeDark: "Escuro",
      language: "Idioma",
      languageHint:
        "Aplica-se à navegação e às configurações; mais áreas ao longo do tempo.",
    },
    data: {
      heading: "Dados",
      integrity: "Integridade da base de dados",
      integrityOk: "Base de dados saudável",
      integrityProblems: "Problemas de integridade detetados",
      engine: "Motor",
      orphanCount: "Registos órfãos",
      noOrphans: "Nenhuma referência órfã encontrada.",
      scanDuration: "Verificação concluída em",
      attachmentsChecked: "anexos verificados",
      attachmentsMissing: "ficheiros em falta",
    },
  },
};
