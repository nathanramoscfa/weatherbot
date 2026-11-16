// frontend/src/ui/Button.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import {
  BUTTON_VARIANTS,
  Button,
  LinkButton,
  buttonClasses,
} from "./Button.tsx";

describe("Button", () => {
  it("is a button of type button with a focus ring and a 24-pixel target", async () => {
    const onClick = vi.fn();
    const { container } = render(
      <Button variant="primary" onClick={onClick}>
        Check now
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Check now" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveClass(
      "min-h-6",
      "min-w-6",
      "focus-visible:outline-2",
      "focus-visible:outline-brand",
      "bg-brand",
      "text-on-brand",
      "text-sm",
    );
    await userEvent.setup().click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("offers four variants and submits when asked", () => {
    expect(Object.keys(BUTTON_VARIANTS)).toEqual([
      "primary",
      "secondary",
      "ghost",
      "danger",
    ]);
    render(
      <Button type="submit" variant="danger" size="md" disabled>
        Prune now
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Prune now" });
    expect(button).toHaveAttribute("type", "submit");
    expect(button).toBeDisabled();
    expect(button).toHaveClass("bg-red-700", "py-2");
    expect(buttonClasses("ghost")).toContain("bg-transparent");
  });
});

describe("LinkButton", () => {
  it("routes inside the app with `to` and links out with `href`", () => {
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: (
            <>
              <LinkButton to="/map" variant="primary">
                Open the map
              </LinkButton>
              <LinkButton href="/api/report" download>
                Export report
              </LinkButton>
            </>
          ),
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    const internal = screen.getByRole("link", { name: "Open the map" });
    expect(internal).toHaveAttribute("href", "/map");
    expect(internal).toHaveClass("bg-brand", "min-h-6");
    const download = screen.getByRole("link", { name: "Export report" });
    expect(download).toHaveAttribute("href", "/api/report");
    expect(download).toHaveAttribute("download");
    expect(download).toHaveClass("bg-surface-card");
  });
});
