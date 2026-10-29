import { describe, expect, it } from "vitest";

import { completeChatText } from "./chatPrompts";

const vocabulary = [
  "Transformer", "Object Detection", "Real-Time Object Detection", "Optical Flow", "Proximal Policy Optimization",
  "The Pile", "Model Merging", "COCO", "COCO-Stuff",
];

describe("completeChatText", () => {
  it("completes question starters before catalog names", () => {
    expect(completeChatText("find rel", vocabulary)).toBe("evant papers on RLVR");
    expect(completeChatText("Which bench", vocabulary)).toBe("marks are used for ");
  });

  it("completes the longest trailing phrase that starts a catalog name", () => {
    expect(completeChatText("papers on object det", vocabulary)).toBe("ection");
    expect(completeChatText("latest real-time object d", vocabulary)).toBe("etection");
    expect(completeChatText("Explain how (transf", vocabulary)).toBe("ormer");
  });

  it("follows the vocabulary's popularity order", () => {
    expect(completeChatText("results on coco-", vocabulary)).toBe("Stuff");
    expect(completeChatText("results on COC", vocabulary)).toBe("");
  });

  it("needs four letters before completing a lone word", () => {
    expect(completeChatText("Compare with opt", vocabulary)).toBe("");
    expect(completeChatText("Compare with proximal policy opt", vocabulary)).toBe("imization");
    expect(completeChatText("Compare with opti", vocabulary)).toBe("cal Flow");
  });

  it("skips common words, finished names, and trailing whitespace", () => {
    expect(completeChatText("compare the", vocabulary)).toBe("");
    expect(completeChatText("compare model", vocabulary)).toBe("");
    expect(completeChatText("compare model m", vocabulary)).toBe("erging");
    expect(completeChatText("papers on optical flow", vocabulary)).toBe("");
    expect(completeChatText("papers on transf ", vocabulary)).toBe("");
    expect(completeChatText("", vocabulary)).toBe("");
  });
});
