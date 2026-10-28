import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PdfCitationSteps } from './PdfCitationSteps';

describe('PDF citation steps', () => {
  it('steps through citations and closes', () => {
    const onStep = vi.fn();
    const onClose = vi.fn();
    render(<PdfCitationSteps index={1} count={3} onStep={onStep} onClose={onClose} />);
    expect(screen.getByRole('status')).toHaveTextContent('Citation 2 of 3');
    fireEvent.click(screen.getByRole('button', { name: 'Previous citation' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next citation' }));
    expect(onStep.mock.calls).toEqual([[-1], [1]]);
    fireEvent.click(screen.getByRole('button', { name: 'Close citations' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
