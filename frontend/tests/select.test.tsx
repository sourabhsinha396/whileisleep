import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Select } from "@/components/select";
import { nextStartingWith, opensAbove } from "@/lib/dropdown";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const FRUIT = ["apple", "banana", "blueberry", "cherry"].map((value) => ({ value, label: value[0].toUpperCase() + value.slice(1) }));

describe("Select", () => {
  let root: Root;
  let box: HTMLElement;
  const changed = vi.fn();

  function Fruit({ inLabel }: { inLabel?: boolean }) {
    const [value, setValue] = useState("banana");
    const select = (
      <Select
        label="Fruit"
        value={value}
        options={FRUIT}
        onChange={(next) => {
          changed(next);
          setValue(next);
        }}
      />
    );
    return inLabel ? <label>Pick one {select}</label> : select;
  }

  beforeEach(async () => {
    changed.mockReset();
    box = document.body.appendChild(document.createElement("div"));
    root = createRoot(box);
    await act(async () => root.render(<Fruit />));
  });

  afterEach(() => {
    act(() => root.unmount());
    box.remove();
  });

  const button = () => box.querySelector("button")!;
  const options = () => [...box.querySelectorAll<HTMLElement>('[role="option"]')];
  const click = (element: HTMLElement) => act(async () => element.click());
  const press = (key: string) => act(async () => void button().dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })));

  it("shows what is picked, and names itself with it", () => {
    expect(button().textContent).toBe("Banana");
    expect(button().getAttribute("aria-label")).toBe("Fruit: Banana");
    expect(options()).toEqual([]);
  });

  it("opens, picks with a click and closes", async () => {
    await click(button());
    expect(options().map((o) => o.textContent)).toEqual(["Apple", "Banana", "Blueberry", "Cherry"]);
    expect(options().map((o) => o.getAttribute("aria-selected"))).toEqual(["false", "true", "false", "false"]);
    await click(options()[3]);
    expect(changed.mock.calls).toEqual([["cherry"]]);
    expect(button().textContent).toBe("Cherry");
    expect(options()).toEqual([]);
  });

  it("works from the keyboard", async () => {
    await press("ArrowDown");
    await press("ArrowDown");
    await press("Enter");
    expect(changed.mock.calls).toEqual([["blueberry"]]);
    await press("ArrowDown");
    await press("a");
    await press(" ");
    expect(changed).toHaveBeenLastCalledWith("apple");
  });

  it("closes with Escape, and picking the same one changes nothing", async () => {
    await click(button());
    await press("End");
    await press("Escape");
    expect(options()).toEqual([]);
    await click(button());
    await press("Enter");
    expect(changed).not.toHaveBeenCalled();
  });

  it("stays closed after a pick inside a label", async () => {
    await act(async () => root.render(<Fruit inLabel />));
    await click(button());
    await click(options()[0]);
    expect(options()).toEqual([]);
    expect(button().textContent).toBe("Apple");
  });
});

it("opens above only when there is no room below and more above", () => {
  expect(opensAbove({ top: 100, bottom: 140 }, 900)).toBe(false);
  expect(opensAbove({ top: 800, bottom: 840 }, 900)).toBe(true);
  expect(opensAbove({ top: 60, bottom: 100 }, 300)).toBe(false);
  expect(opensAbove(undefined, 900)).toBe(false);
});

it("finds the next option starting with a letter, going round", () => {
  const labels = ["Apple", "Banana", "Blueberry"];
  expect(nextStartingWith(labels, "b", 0)).toBe(1);
  expect(nextStartingWith(labels, "b", 1)).toBe(2);
  expect(nextStartingWith(labels, "B", 2)).toBe(1);
  expect(nextStartingWith(labels, "z", 2)).toBe(2);
});
