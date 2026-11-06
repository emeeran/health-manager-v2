/** Created share link; `token` is returned exactly once and never again. */
export interface ShareLinkCreated {
  id: string;
  token_shown_once: string;
  expires_at: string;
}

export interface ShareLinkSummary {
  id: string;
  created_at: string;
  expires_at: string;
  revoked: boolean;
}

export interface PublicShareAllergy {
  substance: string;
  severity: string | null;
}

export interface PublicShareMedication {
  medicine: string;
  dosage: string | null;
}

export interface PublicShareCondition {
  name: string;
  status: string | null;
}

export interface PublicShare {
  member: {
    name: string;
    relationship: string;
    age_years: number | null;
  };
  medications: PublicShareMedication[];
  allergies: PublicShareAllergy[];
  conditions: PublicShareCondition[];
  generated_at: string;
}
