import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PrivacyView from "@/views/PrivacyView";

describe("PrivacyView chat retention", () => {
  it("discloses verified contributor email collection", () => {
    render(<PrivacyView />);

    expect(screen.getByText(/If you request contributor access/i)).toHaveTextContent(
      /verified email address.*review and communicate/i,
    );
  });

  it("states retention, archive, deletion, sharing, and export behavior", () => {
    render(<PrivacyView />);

    const retention = screen.getByText(/Private chats are retained until you delete them/i);
    expect(retention).toHaveTextContent("500 active chats");
    expect(retention).toHaveTextContent("100 MB");
    expect(retention).toHaveTextContent(/Archiving.*does not delete/i);
    expect(retention).toHaveTextContent(/unlisted snapshot/i);
    expect(retention).toHaveTextContent(/No dedicated private-chat export format/i);
  });
});
