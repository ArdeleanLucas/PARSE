/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Pill, SectionCard } from './UIPrimitives';

describe('Pill', () => {
  it('renders the default slate tone', () => {
    const { container } = render(<Pill>Default</Pill>);

    expect(screen.getByText('Default')).toBeTruthy();
    expect(container.querySelector('.bg-slate-100')).toBeTruthy();
  });

  it('renders the emerald tone classes', () => {
    const { container } = render(<Pill tone="emerald">Ready</Pill>);

    expect(screen.getByText('Ready')).toBeTruthy();
    expect(container.querySelector('.bg-emerald-50')).toBeTruthy();
  });

  it('renders the indigo tone classes', () => {
    const { container } = render(<Pill tone="indigo">Grouped</Pill>);

    expect(screen.getByText('Grouped')).toBeTruthy();
    expect(container.querySelector('.bg-indigo-50')).toBeTruthy();
  });
});

describe('SectionCard', () => {
  it('renders title, aside, and children content', () => {
    render(
      <SectionCard title="Speaker forms" aside={<span>2 selected</span>}>
        <div>Rows go here</div>
      </SectionCard>,
    );

    expect(screen.getByText('Speaker forms')).toBeTruthy();
    expect(screen.getByText('2 selected')).toBeTruthy();
    expect(screen.getByText('Rows go here')).toBeTruthy();
  });
});
