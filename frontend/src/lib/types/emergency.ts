export interface EmergencyCard {
  member: {
    name: string;
    birth_date: string | null;
    blood_group: string | null;
    phone: string | null;
    address: string | null;
    emergency_contact_name: string | null;
    emergency_contact_phone: string | null;
    medical_history: string | null;
  };
  allergies: { substance: string; severity: string; reaction: string | null }[];
  conditions: { name: string; status: string }[];
  active_medications: { medicine: string; dosage: string | null }[];
  providers: {
    name: string;
    specialty: string | null;
    hospital: string | null;
    uhid: string | null;
  }[];
}

export type HistoryItemType = "record" | "medication" | "lab" | "vital";

export interface HistoryItem {
  type: HistoryItemType;
  date: string;
  title: string;
  detail: string | null;
  ref_id: string;
}
