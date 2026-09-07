import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { CalibrationDetails, ComputedEvidence } from './ScientificEvidence';
import { scientificNumber, conciseMeasurements } from '../utils/scientificNumbers';
afterEach(cleanup);
it('rounds measurement presentation without corrupting identities or stored precision', () => {
  expect(scientificNumber(1.234567891)).toBe('1.235');
  expect(scientificNumber(0.00000001234567)).toBe('1.235e-8');
  expect(scientificNumber(-123456789.123)).toBe('-1.235e8');
  expect(scientificNumber(0)).toBe('0');
  expect(scientificNumber(1.234567891, true)).toBe('1.234567891');
  expect(conciseMeasurements('error = 1.234567891; r = -0.12345678')).toBe('error = 1.235; r = -0.1235');
  expect(conciseMeasurements('1.2.840.123456789 /raw/1.23456789.dcm finding:1.23456789')).toBe('1.2.840.123456789 /raw/1.23456789.dcm finding:1.23456789');
});
it('keeps calibration behind disclosure and provides full stored precision on request', () => {
  const original = { equation_parameters: { b: 1.234567891 }, ridge: .001 };
  const { container } = render(<CalibrationDetails display={{ coefficients: {b: 1.234567891}, fitted_coefficient_count: 1 }} original={original} />);
  expect(container.querySelector('details')?.open).toBe(false);
  fireEvent.click(screen.getByText('Calibration · 1 fitted coefficients'));
  fireEvent.click(screen.getByText('Complete calibration record'));
  expect(screen.queryByText('1.234567891')).toBeNull();
  fireEvent.click(screen.getByLabelText('Show full stored precision'));
  expect(screen.getByText('1.234567891')).not.toBeNull();
  expect(original.equation_parameters.b).toBe(1.234567891);
});
it('separates measured evidence from fitted coefficients and diagnostic settings', () => {
  const { container } = render(<ComputedEvidence test={{ test_id:'test:one', estimate: { r_squared:.987654321, equation_parameters:{c_0:1.23456789}, ridge:.01 }, expression_latex:'y=a x+b', sample_definition:'12 complete specimens', independent_unit_count:12 }} />);
  expect(container.querySelector('.katex')).not.toBeNull();
  expect(screen.getAllByText('0.9877')[0]).not.toBeNull();
  expect(screen.getAllByText('Equation Parameters')[0].closest('details')?.open).toBe(false);
  expect(screen.getByText('12 complete specimens')).not.toBeNull();
});
it('typesets small coefficients as powers of ten instead of the variable e', () => {
  const { container } = render(<ComputedEvidence test={{ estimate:{coefficient:0.000000012345678}, expression_latex:'y=1.23456789e-8 x' }} />);
  const annotations=Array.from(container.querySelectorAll('annotation')).map(node=>node.textContent);
  expect(annotations.some(value=>value?.includes('1.235\\times 10^{-8}'))).toBe(true);
});
