import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { XThread } from "@/lib/api/papers.types";

import { XThreadsCard } from "./XThreadsCard";

const thread: XThread = {
  url: "https://x.com/artemZholus/status/2108983104178213096",
  tweet_id: "2108983104178213096",
  author_name: "Artem Zholus",
  author_handle: "artemZholus",
  author_avatar_url: "https://pbs.twimg.com/profile_images/1/a_bigger.jpg",
  text: "Introducing RoboJEPA.\n\nCode: https://robojepa.github.io/",
  posted_at: "2026-10-10T18:08:49Z",
  like_count: 1729,
  reply_count: 34,
  media_url: "https://pbs.twimg.com/amplify_video_thumb/1/img/x.jpg",
  media_type: "video",
  fetched_at: "2026-10-12T09:00:00Z",
};

describe("XThreadsCard", () => {
  it("renders a linked preview of each post", () => {
    render(<XThreadsCard threads={[thread]} onEdit={() => undefined} />);

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", thread.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("Artem Zholus")).toBeInTheDocument();
    expect(screen.getByText("@artemZholus")).toBeInTheDocument();
    expect(screen.getByText("robojepa.github.io")).toBeInTheDocument();
    expect(screen.getByText("♥ 1.7k")).toBeInTheDocument();
    expect(screen.getByLabelText("Video")).toBeInTheDocument();
    expect(screen.getByText("1 post")).toBeInTheDocument();
  });

  it("shows an empty state with an edit entry point", async () => {
    const onEdit = vi.fn();
    render(<XThreadsCard threads={[]} onEdit={onEdit} />);

    expect(screen.getByText("No author threads linked yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "edit" }));
    expect(onEdit).toHaveBeenCalledOnce();
  });
});
