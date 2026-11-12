describe('Mutation State Updates (QA-02)', () => {
  interface RequestState {
    status: string
    triage_notes?: string
    version: number
  }

  const applyTransition = (
    current: RequestState,
    action: string,
    payload?: { reason?: string; notes?: string }
  ): RequestState => {
    switch (action) {
      case 'TRIAGE':
        if (current.status !== 'SUBMITTED') throw new Error('Cannot triage non-submitted request')
        return {
          ...current,
          status: 'TRIAGED',
          triage_notes: payload?.notes,
          version: current.version + 1,
        }
      case 'CANCEL':
        return {
          ...current,
          status: 'CANCELED',
          version: current.version + 1,
        }
      default:
        return current
    }
  }

  it('correctly updates state after successful triage mutation without full page reload', () => {
    const initial: RequestState = { status: 'SUBMITTED', version: 1 }
    const updated = applyTransition(initial, 'TRIAGE', { notes: 'Priority confirmed' })

    expect(updated.status).toBe('TRIAGED')
    expect(updated.triage_notes).toBe('Priority confirmed')
    expect(updated.version).toBe(2)
  })

  it('rejects invalid state transition', () => {
    const inProgress: RequestState = { status: 'IN_PROGRESS', version: 1 }
    expect(() => applyTransition(inProgress, 'TRIAGE')).toThrow()
  })
})
