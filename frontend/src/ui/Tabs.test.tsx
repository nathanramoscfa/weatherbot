// frontend/src/ui/Tabs.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Tab, TabList, TabPanel, Tabs } from "./Tabs.tsx";

function Harness({ initial = "first" }: { readonly initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <Tabs value={value} onValueChange={setValue} idPrefix="demo">
      <TabList aria-label="Demo sections">
        <Tab value="first">First</Tab>
        <Tab value="second">Second</Tab>
        <Tab value="third">Third</Tab>
      </TabList>
      <TabPanel value="first">
        <p>First panel body</p>
      </TabPanel>
      <TabPanel value="second">
        <p>Second panel body</p>
      </TabPanel>
      <TabPanel value="third">
        <p>Third panel body</p>
      </TabPanel>
    </Tabs>
  );
}

describe("Tabs", () => {
  it("renders WAI-ARIA tablist, tab, and tabpanel roles with roving tabindex, unmounts inactive panels, and sets no inline style", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);

    const tablist = screen.getByRole("tablist", { name: "Demo sections" });
    expect(tablist).toBeInTheDocument();

    const firstTab = screen.getByRole("tab", { name: "First" });
    const secondTab = screen.getByRole("tab", { name: "Second" });
    const thirdTab = screen.getByRole("tab", { name: "Third" });

    expect(firstTab).toHaveAttribute("aria-selected", "true");
    expect(firstTab).toHaveAttribute("tabindex", "0");
    expect(firstTab).toHaveAttribute("aria-controls", "demo-panel-first");

    expect(secondTab).toHaveAttribute("aria-selected", "false");
    expect(secondTab).toHaveAttribute("tabindex", "-1");
    expect(thirdTab).toHaveAttribute("aria-selected", "false");
    expect(thirdTab).toHaveAttribute("tabindex", "-1");

    const panel = screen.getByRole("tabpanel", { name: "First" });
    expect(panel).toHaveAttribute("id", "demo-panel-first");
    expect(panel).toHaveAttribute("tabindex", "0");
    expect(panel).toHaveTextContent("First panel body");
    expect(screen.queryByText("Second panel body")).toBeNull();
    expect(screen.queryByText("Third panel body")).toBeNull();

    await user.click(secondTab);
    expect(secondTab).toHaveAttribute("aria-selected", "true");
    expect(secondTab).toHaveAttribute("tabindex", "0");
    expect(firstTab).toHaveAttribute("aria-selected", "false");
    expect(firstTab).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tabpanel", { name: "Second" })).toHaveTextContent(
      "Second panel body",
    );
    expect(screen.queryByText("First panel body")).toBeNull();

    expect(container.querySelector("[style]")).toBeNull();
  });

  it("moves focus and selection with ArrowRight, ArrowLeft, End, and Home keys", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);

    const firstTab = screen.getByRole("tab", { name: "First" });
    const secondTab = screen.getByRole("tab", { name: "Second" });
    const thirdTab = screen.getByRole("tab", { name: "Third" });

    firstTab.focus();
    expect(firstTab).toHaveFocus();

    await user.keyboard("{ArrowRight}");
    expect(secondTab).toHaveFocus();
    expect(secondTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Second panel body")).toBeInTheDocument();

    await user.keyboard("{ArrowRight}");
    expect(thirdTab).toHaveFocus();
    expect(thirdTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Third panel body")).toBeInTheDocument();

    // Wraps around from last to first
    await user.keyboard("{ArrowRight}");
    expect(firstTab).toHaveFocus();
    expect(firstTab).toHaveAttribute("aria-selected", "true");

    // Wraps around from first to last
    await user.keyboard("{ArrowLeft}");
    expect(thirdTab).toHaveFocus();
    expect(thirdTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Home}");
    expect(firstTab).toHaveFocus();
    expect(firstTab).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{End}");
    expect(thirdTab).toHaveFocus();
    expect(thirdTab).toHaveAttribute("aria-selected", "true");

    expect(container.querySelector("[style]")).toBeNull();
  });
});
