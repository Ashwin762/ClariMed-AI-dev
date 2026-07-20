// frontend/src/components/ReasoningPanel.test.tsx
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ReasoningPanel from './ReasoningPanel';
import type { Candidate, Evidence } from '../api';

function makeCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    id: 'EYE001',
    name: 'Conjunctivitis',
    specialist: 'Ophthalmologist',
    emergency_possible: false,
    fused_raw: 0.7,
    img_score: 0.6,
    sym_score: 0.8,
    image_relevant: true,
    matched_keywords: ['Ocular Redness', 'Watery Eyes'],
    share_pct: 70,
    strength_raw: 0.75,
    match_strength: 'Strong match',
    ...overrides,
  };
}

function makeEvidence(overrides: Partial<Evidence> = {}): Evidence {
  return {
    symptoms_reported: 2,
    image_provided: true,
    matched_signals: 2,
    candidates_considered: 8,
    separation: 0.3,
    ...overrides,
  };
}

describe('ReasoningPanel', () => {
  it('renders without crashing given a realistic candidate and evidence', () => {
    render(<ReasoningPanel top={makeCandidate()} evidence={makeEvidence()} rankingReliable={true} />);
    expect(screen.getByText(/how the ai got here/i)).toBeInTheDocument();
  });

  // REAL BUG FOUND ON FIRST ACTUAL TEST RUN, FIXED HERE: the percentage
  // values animate from 0% up to the target over ~800ms via
  // requestAnimationFrame -- that's intentional component behavior (the
  // "watch confidence build" effect), not a bug. The original version of
  // this test asserted the final value immediately after render, before
  // the animation had run at all, and failed against a real 0%. waitFor
  // polls until the animated value actually arrives instead of asserting
  // synchronously.
  it('shows the symptom match percentage derived from sym_score, once the reveal animation completes', async () => {
    render(<ReasoningPanel top={makeCandidate({ sym_score: 0.8 })} evidence={makeEvidence()} rankingReliable={true} />);
    await waitFor(() => expect(screen.getByText('80%')).toBeInTheDocument(), { timeout: 2000 });
  });

  it('shows the combined confidence percentage derived from strength_raw, once the reveal animation completes', async () => {
    render(<ReasoningPanel top={makeCandidate({ strength_raw: 0.75 })} evidence={makeEvidence()} rankingReliable={true} />);
    await waitFor(() => expect(screen.getByText('75%')).toBeInTheDocument(), { timeout: 2000 });
  });

  it('shows a photo match row when the image was relevant to this specific condition', () => {
    render(<ReasoningPanel top={makeCandidate({ image_relevant: true, img_score: 0.6 })} evidence={makeEvidence()} rankingReliable={true} />);
    expect(screen.getByText(/photo match/i)).toBeInTheDocument();
  });

  it('explains that the photo was not relevant, rather than showing a fake photo match row, when image_relevant is false but a photo was provided', () => {
    render(
      <ReasoningPanel
        top={makeCandidate({ image_relevant: false, img_score: null })}
        evidence={makeEvidence({ image_provided: true })}
        rankingReliable={true}
      />
    );
    expect(screen.queryByText(/photo match/i)).not.toBeInTheDocument();
    expect(screen.getByText(/wasn't a relevant signal/i)).toBeInTheDocument();
  });

  it('renders every matched keyword as a visible chip', () => {
    render(
      <ReasoningPanel
        top={makeCandidate({ matched_keywords: ['Ocular Redness', 'Watery Eyes', 'Eye Pain'] })}
        evidence={makeEvidence()}
        rankingReliable={true}
      />
    );
    expect(screen.getByText('Ocular Redness')).toBeInTheDocument();
    expect(screen.getByText('Watery Eyes')).toBeInTheDocument();
    expect(screen.getByText('Eye Pain')).toBeInTheDocument();
  });

  it('shows the evidence summary counts', () => {
    render(<ReasoningPanel top={makeCandidate()} evidence={makeEvidence({ candidates_considered: 8, matched_signals: 2 })} rankingReliable={true} />);
    expect(screen.getByText(/8 conditions evaluated/i)).toBeInTheDocument();
    expect(screen.getByText(/2 signals matched/i)).toBeInTheDocument();
  });

  it('mentions building confidence when ranking is not yet reliable', () => {
    render(<ReasoningPanel top={makeCandidate()} evidence={makeEvidence()} rankingReliable={false} />);
    expect(screen.getByText(/confidence still building/i)).toBeInTheDocument();
  });

  it('does not render the confidence-building note when ranking is reliable', () => {
    render(<ReasoningPanel top={makeCandidate()} evidence={makeEvidence()} rankingReliable={true} />);
    expect(screen.queryByText(/confidence still building/i)).not.toBeInTheDocument();
  });

  it('handles a condition with no matched keywords without crashing or rendering an empty chip row', () => {
    render(<ReasoningPanel top={makeCandidate({ matched_keywords: [] })} evidence={makeEvidence()} rankingReliable={true} />);
    expect(screen.queryByText(/what actually matched/i)).not.toBeInTheDocument();
  });
});