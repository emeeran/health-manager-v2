export interface Provider {
  id: string;
  name: string;
  specialty: string | null;
  hospital: string | null;
  phone: string | null;
  notes: string | null;
  created_at: string;
}

export interface ProviderCreate {
  name: string;
  specialty?: string;
  hospital?: string;
  phone?: string;
  notes?: string;
}

export interface ProviderUpdate {
  name?: string;
  specialty?: string | null;
  hospital?: string | null;
  phone?: string | null;
  notes?: string | null;
}

export interface ProviderAssignment {
  id: string;
  provider_id: string;
  provider_name: string;
  specialty: string | null;
  hospital: string | null;
  uhid: string | null;
  created_at: string;
}
