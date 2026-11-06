import { beforeEach, describe, expect, it } from "vitest";
import {
  buildRecordPayload,
  canSubmit,
  initialWizardDraft,
  lastDoctorName,
  matchProviderId,
  wizardFormError,
} from "../wizard-state";

function completedDraft() {
  return {
    ...initialWizardDraft(),
    recordType: "doctor_visit" as const,
    recordDate: "2026-11-01",
    diagnosis: "高血压",
  };
}

beforeEach(() => localStorage.clear());

describe("form validation", () => {
  it("blocks submission without a record type", () => {
    const draft = initialWizardDraft();
    expect(canSubmit(draft)).toBe(false);
    expect(wizardFormError(draft)).toContain("record type");
  });

  it("blocks submission without a date", () => {
    const draft = {
      ...initialWizardDraft(),
      recordType: "lab_report" as const,
      recordDate: "",
    };
    expect(canSubmit(draft)).toBe(false);
  });

  it("allows submission with a complete draft", () => {
    expect(canSubmit(completedDraft())).toBe(true);
  });
});

describe("matchProviderId", () => {
  const providers = [
    { id: "p1", name: "Dr Wang" },
    { id: "p2", name: "City Clinic" },
  ];

  it("matches case-insensitively on exact name", () => {
    expect(matchProviderId("dr wang", providers)).toBe("p1");
  });

  it("returns undefined for free text that is not in the directory", () => {
    expect(matchProviderId("Dr Unlisted", providers)).toBeUndefined();
    expect(matchProviderId("  ", providers)).toBeUndefined();
  });
});

describe("buildRecordPayload", () => {
  it("omits empty optional fields and carries no tracking metadata", () => {
    const payload = buildRecordPayload(completedDraft());
    expect(payload).toEqual({
      record_type: "doctor_visit",
      record_date: "2026-11-01",
      diagnosis: "高血压",
    });
    expect(payload.tags).toBeUndefined();
    expect(payload.record_time).toBeUndefined();
    expect(payload.provider_id).toBeUndefined();
    expect(payload.confidentiality_level).toBeUndefined();
  });

  it("joins reason + note into the summary and sends investigations", () => {
    const draft = {
      ...completedDraft(),
      reason: "follow-up",
      note: "随访记录",
      investigations: "CBC, X-ray chest",
    };
    expect(buildRecordPayload(draft)).toMatchObject({
      summary: "follow-up\n随访记录",
      investigations: "CBC, X-ray chest",
    });
  });

  it("trims the provider name and links the directory provider", () => {
    const draft = { ...completedDraft(), providerName: "  Dr Wang  " };
    const providers = [{ id: "p1", name: "Dr Wang" }];
    expect(buildRecordPayload(draft, providers)).toMatchObject({
      doctor_name: "Dr Wang",
      provider_id: "p1",
    });
    expect(buildRecordPayload(draft, [])).not.toHaveProperty("provider_id");
  });

  it("prefills the provider name from the previous creation", () => {
    buildRecordPayload({ ...completedDraft(), providerName: "Dr Wang" });
    expect(lastDoctorName()).toBe("Dr Wang");
    expect(initialWizardDraft().providerName).toBe("Dr Wang");
  });

  it("throws when required fields are missing", () => {
    expect(() => buildRecordPayload(initialWizardDraft())).toThrow(
      "Record type is required.",
    );
  });
});
