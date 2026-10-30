import { describe, expect, it } from "vitest";

import { hfLoginUrl } from "@/components/HfSignInButton";

describe("hfLoginUrl (positional chat form)", () => {
  it("marks chat authorization as an inference permission request", () => {
    const url = new URL(hfLoginUrl("/chat", true), window.location.origin);

    expect(url.searchParams.get("return_to")).toBe("/chat");
    expect(url.searchParams.get("authorize_inference")).toBe("true");
  });
});
