describe('Request List Filter & Search (QA-02)', () => {
  const requests = [
    { id: '1', title: 'Fix HVAC unit', address: '123 Main St', status: 'SUBMITTED', priority: 'HIGH' },
    { id: '2', title: 'Plumbing leak', address: '456 Oak Ave', status: 'IN_PROGRESS', priority: 'NORMAL' },
    { id: '3', title: 'Electrical short', address: '789 Pine Rd', status: 'COMPLETED', priority: 'LOW' },
  ]

  const filterRequests = (items: typeof requests, query: string, status?: string) => {
    return items.filter((req) => {
      const matchesSearch =
        !query ||
        req.title.toLowerCase().includes(query.toLowerCase()) ||
        req.address.toLowerCase().includes(query.toLowerCase())
      const matchesStatus = !status || req.status === status
      return matchesSearch && matchesStatus
    })
  }

  it('filters requests by search query matching title', () => {
    const result = filterRequests(requests, 'HVAC')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('1')
  })

  it('filters requests by status and address', () => {
    const result = filterRequests(requests, 'Oak', 'IN_PROGRESS')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('2')
  })

  it('returns empty list when no matches exist', () => {
    const result = filterRequests(requests, 'Nonexistent')
    expect(result).toHaveLength(0)
  })
})
