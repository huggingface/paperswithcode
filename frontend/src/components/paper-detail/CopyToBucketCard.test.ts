import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/toaster";

const { copyPaperToBucketMock } = vi.hoisted(() => ({
  copyPaperToBucketMock: vi.fn(),
}));

vi.mock("@/lib/api/papers", () => ({
  papersApi: { copyToBucket: copyPaperToBucketMock },
}));

import {
  buildBucketCopyCommands,
  chunkBucketArtifacts,
  collectBucketArtifacts,
  paperArtifactBucketName,
} from "@/lib/bucketCopy";
import { CopyToBucketCard } from "./CopyToBucketCard";

beforeEach(() => {
  copyPaperToBucketMock.mockReset();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("chunkBucketArtifacts", () => {
  it("keeps large copies within the backend request limit", () => {
    const artifacts = Array.from({ length: 45 }, (_, index) => ({
      kind: "model" as const,
      repo_id: `owner/model-${index}`,
    }));

    const batches = chunkBucketArtifacts(artifacts);

    expect(batches.map((batch) => batch.length)).toEqual([20, 20, 5]);
    expect(batches.flat()).toEqual(artifacts);
  });
});

describe("collectBucketArtifacts", () => {
  it("normalizes and deduplicates linked repositories", () => {
    expect(
      collectBucketArtifacts({
        paperId: "42",
        pdfName: "2601.00001",
        pdfUrl: "https://arxiv.org/pdf/2601.00001v1",
        githubUrls: [
          "https://github.com/huggingface/transformers",
          "https://github.com/huggingface/transformers/",
        ],
        hfModelUrls: ["https://huggingface.co/openai/gpt-oss-20b?ref=paper"],
        hfDatasetUrls: ["https://huggingface.co/datasets/openai/gsm8k"],
        hfSpaceUrls: ["https://huggingface.co/spaces/openai/demo"],
      }).map(({ id, source, destination }) => ({ id, source, destination })),
    ).toEqual([
      {
        id: "pdf",
        source: "https://arxiv.org/pdf/2601.00001v1",
        destination: "paper/2601.00001.pdf",
      },
      {
        id: "model:openai/gpt-oss-20b",
        source: "hf://openai/gpt-oss-20b/",
        destination: "models/openai/gpt-oss-20b/",
      },
      {
        id: "dataset:openai/gsm8k",
        source: "hf://datasets/openai/gsm8k/",
        destination: "datasets/openai/gsm8k/",
      },
      {
        id: "space:openai/demo",
        source: "hf://spaces/openai/demo/",
        destination: "spaces/openai/demo/",
      },
      {
        id: "github:huggingface/transformers",
        source: "https://github.com/huggingface/transformers.git",
        destination: "github/huggingface/transformers/",
      },
    ]);
  });
});

describe("buildBucketCopyCommands", () => {
  it("builds server-side Hub copies and a bounded GitHub checkout", () => {
    const artifacts = collectBucketArtifacts({
      paperId: "42",
      pdfName: "2601.00001",
      pdfUrl: "https://arxiv.org/pdf/2601.00001v1",
      githubUrls: ["https://github.com/huggingface/transformers"],
      hfModelUrls: ["https://huggingface.co/openai/gpt-oss-20b"],
      hfDatasetUrls: [],
      hfSpaceUrls: [],
    });

    const commands = buildBucketCopyCommands("alice/paper-copy", artifacts, {
      create: true,
      isPrivate: true,
    });

    expect(commands).toContain("hf buckets create \"$HF_BUCKET\" --exist-ok --private");
    expect(commands).toContain(
      "hf cp 'hf://openai/gpt-oss-20b/' \"hf://buckets/$HF_BUCKET/models/openai/gpt-oss-20b/\"",
    );
    expect(commands).toContain(
      "curl --fail --location 'https://arxiv.org/pdf/2601.00001v1' --output \"$PWC_PDF\"",
    );
    expect(commands).toContain(
      "hf cp \"$PWC_PDF\" \"hf://buckets/$HF_BUCKET/paper/2601.00001.pdf\"",
    );
    expect(commands).toContain("PWC_COPY_DIR=\"$(mktemp -d)\"");
    expect(commands).toContain(
      "git clone --depth 1 -- 'https://github.com/huggingface/transformers.git'",
    );
    expect(commands).toContain(
      "hf sync \"$PWC_COPY_DIR/github/huggingface/transformers\"",
    );
  });
});

describe("paperArtifactBucketName", () => {
  it("uses the concise title prefix when a paper has a subtitle", () => {
    expect(paperArtifactBucketName("Kimi K3: Open Frontier Intelligence")).toBe(
      "kimi-k3-artifacts",
    );
  });

  it("normalizes punctuation and provides a fallback", () => {
    expect(paperArtifactBucketName("Qwen3 Technical Report")).toBe(
      "qwen3-technical-report-artifacts",
    );
    expect(paperArtifactBucketName("日本語")).toBe("paper-artifacts");
  });
});

describe("CopyToBucketCard", () => {
  it("deselects and reselects all artifacts in one action", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(CopyToBucketCard, {
        githubUrls: [],
        hfModelUrls: ["https://huggingface.co/openai/test-model"],
        hfDatasetUrls: [],
        hfSpaceUrls: [],
        paperId: "42",
        pdfName: "42",
        pdfUrl: "https://arxiv.org/pdf/42",
        isSignedIn: true,
        suggestedBucketId: "nielsr/paper-artifacts",
      }),
    );

    await user.click(screen.getByRole("button", { name: /copy to bucket/i }));

    const artifactCheckboxes = screen.getAllByRole("checkbox");
    expect(artifactCheckboxes).toHaveLength(2);
    artifactCheckboxes.forEach((checkbox) => expect(checkbox).toBeChecked());
    const commandPanel = document.getElementById("bucket-copy-commands");
    expect(commandPanel).toHaveClass("h-[190px]");
    expect(commandPanel).toHaveTextContent("hf cp 'hf://openai/test-model/'");

    const deselectAllButton = screen.getByRole("button", { name: "Deselect all" });
    expect(deselectAllButton).toHaveClass("border");
    await user.click(deselectAllButton);
    artifactCheckboxes.forEach((checkbox) => expect(checkbox).not.toBeChecked());
    expect(commandPanel).toHaveClass("h-[190px]");
    expect(commandPanel).not.toHaveTextContent("hf cp 'hf://openai/test-model/'");

    await user.click(screen.getByRole("button", { name: "Select all" }));
    artifactCheckboxes.forEach((checkbox) => expect(checkbox).toBeChecked());
  });

  it("prefills the suggested signed-in user destination when opened", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(CopyToBucketCard, {
        githubUrls: ["https://github.com/moonshotai/kimi-k3"],
        hfModelUrls: [],
        hfDatasetUrls: [],
        hfSpaceUrls: [],
        paperId: "42",
        pdfName: "42",
        pdfUrl: null,
        isSignedIn: true,
        suggestedBucketId: "nielsr/kimi-k3-artifacts",
      }),
    );

    await user.click(screen.getByRole("button", { name: /copy to bucket/i }));

    expect(screen.getByLabelText("Bucket name")).toHaveValue(
      "nielsr/kimi-k3-artifacts",
    );
    expect(screen.getByRole("link", { name: /view bucket/i })).toHaveAttribute(
      "href",
      "https://huggingface.co/buckets/nielsr/kimi-k3-artifacts",
    );
  });

  it("links the destination bucket from the completion toast", async () => {
    copyPaperToBucketMock.mockResolvedValue({
      bucket_id: "nielsr/paper-artifacts",
      copied: ["model:openai/test-model"],
      errors: [],
    });
    const user = userEvent.setup();
    render(
      React.createElement(
        React.Fragment,
        null,
        React.createElement(CopyToBucketCard, {
          githubUrls: [],
          hfModelUrls: ["https://huggingface.co/openai/test-model"],
          hfDatasetUrls: [],
          hfSpaceUrls: [],
          paperId: "42",
          pdfName: "42",
          pdfUrl: null,
          isSignedIn: true,
          suggestedBucketId: "nielsr/paper-artifacts",
        }),
        React.createElement(Toaster),
      ),
    );

    await user.click(screen.getByRole("button", { name: /copy to bucket/i }));
    await user.click(screen.getByRole("button", { name: "Copy now" }));

    expect(await screen.findByText("Copied to bucket")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open bucket" })).toHaveAttribute(
      "href",
      "https://huggingface.co/buckets/nielsr/paper-artifacts",
    );
  });

  it("resumes the copy automatically after bucket authorization", async () => {
    copyPaperToBucketMock.mockResolvedValue({
      bucket_id: "nielsr/paper-artifacts",
      copied: ["model:openai/test-model"],
      errors: [],
    });
    window.sessionStorage.setItem(
      "pwc:bucket-copy:42",
      JSON.stringify({
        paperId: "42",
        bucketId: "nielsr/paper-artifacts",
        destinationMode: "new",
        visibility: "private",
        selectedIds: ["model:openai/test-model"],
      }),
    );
    window.history.replaceState({}, "", "/paper/42?copy_to_bucket=42");

    render(
      React.createElement(CopyToBucketCard, {
        githubUrls: [],
        hfModelUrls: ["https://huggingface.co/openai/test-model"],
        hfDatasetUrls: [],
        hfSpaceUrls: [],
        paperId: "42",
        pdfName: "42",
        pdfUrl: null,
        isSignedIn: true,
        suggestedBucketId: "nielsr/paper-artifacts",
      }),
    );

    await waitFor(() => expect(copyPaperToBucketMock).toHaveBeenCalledOnce());
    expect(copyPaperToBucketMock).toHaveBeenCalledWith("42", {
      bucket_id: "nielsr/paper-artifacts",
      create: true,
      private: true,
      include_pdf: false,
      artifacts: [{ kind: "model", repo_id: "openai/test-model" }],
    });
    expect(window.location.search).toBe("");
    expect(window.sessionStorage.getItem("pwc:bucket-copy:42")).toBeNull();
  });
});
