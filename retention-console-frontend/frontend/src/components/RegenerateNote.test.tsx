import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { RegenerateNote } from './RegenerateNote'

describe('RegenerateNote', () => {
  it('renders note component', () => {
    render(<RegenerateNote />)
    expect(screen.getByText(/AI Note generated based on customer profile/i)).toBeInTheDocument()
  })
})
