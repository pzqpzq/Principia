import "@testing-library/jest-dom/vitest";
import {fireEvent, render, screen} from "@testing-library/react";
import {expect, it, vi} from "vitest";
import {FocusDialog} from "./FocusDialog";

it("focuses, traps, dismisses and restores keyboard focus", () => {
  const trigger = document.createElement("button");
  document.body.append(trigger);
  trigger.focus();
  const close = vi.fn();
  const view = render(<FocusDialog title="Rename project" onClose={close}><input aria-label="Name"/><button>Save</button></FocusDialog>);
  const input = screen.getByRole("textbox");
  const save = screen.getByRole("button", {name: "Save"});
  expect(input).toHaveFocus();
  fireEvent.keyDown(input, {key: "Tab", shiftKey: true});
  expect(save).toHaveFocus();
  fireEvent.keyDown(save, {key: "Tab"});
  expect(input).toHaveFocus();
  fireEvent.keyDown(input, {key: "Escape"});
  expect(close).toHaveBeenCalledOnce();
  view.unmount();
  expect(trigger).toHaveFocus();
  trigger.remove();
});
