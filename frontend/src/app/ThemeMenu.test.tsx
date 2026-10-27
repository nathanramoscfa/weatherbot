// frontend/src/app/ThemeMenu.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ThemeMenu } from "./ThemeMenu.tsx";
import { THEME_STORAGE_KEY } from "./theme.ts";

describe("ThemeMenu", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("defaults to system theme and stores and applies dark and light selections", async () => {
    const user = userEvent.setup();
    render(<ThemeMenu />);

    const trigger = screen.getByRole("button", { name: "Theme: System" });
    expect(trigger).toBeInTheDocument();
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    await user.click(trigger);
    const darkOption = await screen.findByRole("menuitemradio", {
      name: "Dark",
    });
    await user.click(darkOption);

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(
      screen.getByRole("button", { name: "Theme: Dark" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Theme: Dark" }));
    const lightOption = await screen.findByRole("menuitemradio", {
      name: "Light",
    });
    await user.click(lightOption);

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(
      screen.getByRole("button", { name: "Theme: Light" }),
    ).toBeInTheDocument();
  });

  it("initializes from a stored theme preference in localStorage", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<ThemeMenu />);

    expect(
      screen.getByRole("button", { name: "Theme: Dark" }),
    ).toBeInTheDocument();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
