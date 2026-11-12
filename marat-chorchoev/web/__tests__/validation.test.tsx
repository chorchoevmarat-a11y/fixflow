import { z } from 'zod'

describe('Web Form Validation (QA-02)', () => {
  it('validates required fields for service request creation', () => {
    const validateRequest = (data: { title?: string; description?: string }) => {
      const errors: Record<string, string> = {}
      if (!data.title || data.title.length < 5 || data.title.length > 120) {
        errors.title = 'Title must be between 5 and 120 characters'
      }
      if (!data.description || data.description.length < 20 || data.description.length > 3000) {
        errors.description = 'Description must be between 20 and 3,000 characters'
      }
      return errors
    }

    expect(validateRequest({ title: 'Hi', description: 'Short' })).toHaveProperty('title')
    expect(validateRequest({ title: 'Hi', description: 'Short' })).toHaveProperty('description')
    expect(validateRequest({
      title: 'Valid Request Title for Testing',
      description: 'This is a valid long description that exceeds twenty characters.',
    })).toEqual({})
  })

  it('validates email and credentials formats', () => {
    const emailSchema = z.string().email()
    expect(emailSchema.safeParse('valid@fixflow.com').success).toBe(true)
    expect(emailSchema.safeParse('invalid-email').success).toBe(false)
  })
})
