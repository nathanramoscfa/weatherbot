// frontend/src/ui/Disclosure.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Disclosure } from "./Disclosure.tsx";

describe("Disclosure", () => {
  it("is a native details element, closed by default, whose content stays in the DOM", async () => {
    const { container } = render(
      <Disclosure
        summary="Why this level / Official provenance & controls"
        caption="2 products"
        data-testid="provenance"
      >
        <code>hurricane_warning</code>
      </Disclosure>,
    );
    const details = screen.getByTestId("provenance");
    expect(details.tagName).toBe("DETAILS");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("hurricane_warning");
    expect(screen.getByText("2 products")).toHaveClass("text-caption");
    expect(container.querySelector("[style]")).toBeNull();

    const summary = container.querySelector("summary");
    expect(summary).not.toBeNull();
    expect(summary).toHaveTextContent(
      "Why this level / Official provenance & controls",
    );
    await userEvent.setup().click(summary as HTMLElement);
    expect(details).toHaveAttribute("open");
  });
});
