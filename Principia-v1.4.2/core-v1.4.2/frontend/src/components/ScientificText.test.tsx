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

it("typesets legacy recurrence prose without changing its words", () => {
  const view = render(<ScientificText value="The recurrence a_n = 3a_{n-1} - 3a_{n-2} + a_{n-3} held exactly; R²=0.846." />);
  expect(view.container.querySelectorAll('.katex').length).toBeGreaterThanOrEqual(2);
  expect(view.container.querySelectorAll('.katex-error')).toHaveLength(0);
  expect(view.container.textContent).toContain('held exactly');
});

it("preserves explicit equations and ordinary dataset identifiers", () => {
  const view = render(<ScientificText value={'Measured $\\alpha = 2$ in met_mpy and patient_id.'} />);
  expect(view.container.querySelectorAll('.katex')).toHaveLength(1);
  expect(view.container.textContent).toContain('met_mpy and patient_id');
});

it("typesets named Greek AST parameters while preserving prose and text labels", () => {
  const view = render(<ScientificText value={'The beta parameter: $P=\\exp(-beta (M-M_0)) + \\alpha_0 + \\text{beta control}$.'} />);
  const formula = view.container.querySelector('.katex-html')?.textContent || '';
  expect(formula).toContain('β');
  expect(formula).toContain('α');
  expect(formula.replace(/\s+/g, ' ')).toContain('beta control');
  expect(view.container.textContent).toContain('The beta parameter');
  expect(view.container.querySelectorAll('.katex-error')).toHaveLength(0);
});

it("keeps complete executable symbol subscripts together", () => {
  const view = render(<ScientificText value={'$c_10 + T_ref + \\text{source label}$'} />);
  const subscripts = [...view.container.querySelectorAll('msub')];
  expect(subscripts.map(node => node.lastElementChild?.textContent)).toEqual(['10', 'ref']);
  expect(view.container.querySelector('.katex-html')?.textContent?.replace(/\s+/g, ' ')).toContain('source label');
  expect(view.container.querySelectorAll('.katex-error')).toHaveLength(0);
});
