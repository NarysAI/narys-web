import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { Router } from 'wouter'
import { memoryLocation } from 'wouter/memory-location'
import App from './App'

vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ name: 'NarysAI Registry', package_count: 1, object_count: 0, categories: [], featured: [] }) })) as unknown as typeof fetch)

test('renders the NarysAI repository identity', async () => {
  const { hook } = memoryLocation({ path: '/repository' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByText(/Креслення, готові/i)).toBeInTheDocument()
  expect(screen.getByText('NarysAI collection')).toBeInTheDocument()
})
