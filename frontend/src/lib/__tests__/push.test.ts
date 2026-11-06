import { describe, expect, it } from "vitest";
import { urlBase64ToUint8Array } from "../push";

describe("urlBase64ToUint8Array", () => {
  it("decodes a URL-safe base64 VAPID key into raw bytes", () => {
    // "hello" — no padding or URL-safe characters needed.
    expect(Array.from(urlBase64ToUint8Array("aGVsbG8"))).toEqual([
      104, 101, 108, 108, 111,
    ]);
  });

  it("handles URL-safe - and _ characters and missing padding", () => {
    // Standard base64 "+/8=" encodes bytes 251, 255; URL-safe form is "-_8".
    expect(Array.from(urlBase64ToUint8Array("-_8"))).toEqual([251, 255]);
  });

  it("round-trips through btoa for a realistic 65-byte key", () => {
    const bytes = new Uint8Array(65).map((_, i) => (i * 37) % 256);
    const base64Url = btoa(String.fromCharCode(...bytes))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    expect(Array.from(urlBase64ToUint8Array(base64Url))).toEqual(
      Array.from(bytes),
    );
  });
});
