import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { PlainLanguageInterpretation } from './PlainLanguageInterpretation';
afterEach(cleanup);
it('presents explanation and falsification without losing scientific notation or limits', () => {
 const {container}=render(<PlainLanguageInterpretation value={{summary:'Recent brightness predicts the next reading.',explanation:'The curved term $x^2$ changes sensitivity.',implication:'Error is lower than persistence.',boundaries:['One acquisition.','Causality was not tested.'],next_check:'Test a separate acquisition.'}} />);
 expect(screen.getByText('Plain-language interpretation')).not.toBeNull();
 expect(container.querySelector('.katex')).not.toBeNull();
 expect(screen.getByText('Scope and alternative explanations').closest('details')).not.toBeNull();
 expect(screen.getByText('Causality was not tested.')).not.toBeNull();
 expect(screen.getByText('Next validation')).not.toBeNull();
 expect(container.textContent).not.toContain('[object Object]');
});
it('keeps legacy explanations readable when new context is absent', () => {
 render(<PlainLanguageInterpretation fallback='Recorded interpretation.' />);
 expect(screen.getByText('Recorded interpretation.')).not.toBeNull();
 expect(screen.queryByText('Next validation')).toBeNull();
});
