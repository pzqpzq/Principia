// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScientificText } from "./ScientificText";

describe("ScientificText", () => {
  it("compiles inline LaTeX while preserving surrounding scientific prose", () => {
    const view = render(
      <ScientificText value={"For $\\dot x=Ax+Bu$, require $[B,AB,\\dots,A^{n-1}B]$."} />,
    );

    expect(view.container.querySelectorAll(".katex")).toHaveLength(2);
    expect(view.container.textContent).toContain("For");
    expect(view.container.querySelector(".katex-html")?.textContent).not.toContain(
      "\\dot",
    );
  });
});
