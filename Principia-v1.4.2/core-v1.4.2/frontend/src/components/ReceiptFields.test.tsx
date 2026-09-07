// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ReceiptFields, SourceEvidence } from "./ReceiptFields";
afterEach(cleanup);

it("preserves nested estimates, coordinates and complete source identifiers", () => {
  const digest = 'a'.repeat(64);
  const { container } = render(<ReceiptFields value={{ spacing: 3.0000001723, geometry: { orientation: [1, 0, 0], dimensions: [480, 480] }, byte_sha256: digest }} />);
  expect(container.querySelector('[title="3.0000001723"]')?.textContent).toBe('3');
  expect(container.textContent).toContain('[480, 480]');
  expect(container.textContent).not.toContain('[object Object]');
  const details = container.querySelector('details')!;
  expect(details.open).toBe(false);
  fireEvent.click(screen.getByText(/Identifiers and provenance/));
  expect(details.open).toBe(true);
  expect(container.textContent).toContain(digest);
});

it("renders tabular receipts progressively without dropping later records", () => {
  const { container } = render(<ReceiptFields value={{ fits: Array.from({length:30}, (_, index) => ({ group: `specimen ${index}`, error: index / 10 })) }} />);
  expect(container.querySelectorAll('tbody tr')).toHaveLength(12);
  fireEvent.click(screen.getByRole('button', {name:'Show more entries'}));
  expect(container.querySelectorAll('tbody tr')).toHaveLength(30);
  expect(container.textContent).toContain('specimen 29');
});

it("keeps many source anchors behind searchable provenance instead of flooding findings", () => {
  const evidence = Array.from({length:70}, (_, index) => ({ evidence_id:`evidence:${index}`, asset_id:`asset:${index}`, locator: { relative_path:`raw/slice-${index}.dcm`, role:'DICOM slice' } }));
  const { container } = render(<SourceEvidence evidence={evidence} />);
  expect(container.textContent).toContain('70 evidence anchors across 70 source files');
  expect(container.querySelector('details')?.open).toBe(false);
  fireEvent.click(screen.getByText('Inspect source files and provenance'));
  expect(container.querySelectorAll('.data-evidence-receipt')).toHaveLength(12);
  fireEvent.change(screen.getByRole('textbox',{name:'Search source evidence'}), {target:{value:'slice-69.dcm'}});
  expect(container.querySelectorAll('.data-evidence-receipt')).toHaveLength(1);
  expect(container.textContent).toContain('slice-69.dcm');
});
