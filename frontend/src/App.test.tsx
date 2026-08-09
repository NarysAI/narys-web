import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import { Router } from 'wouter'
import { memoryLocation } from 'wouter/memory-location'
import App from './App'

vi.mock('./components/Viewer', () => ({ Viewer: () => <div>3D viewer</div> }))

const catalog = {
  name: 'NarysAI Registry', package_count: 3, object_count: 0, featured: [],
  categories: [{ name: 'electronics', packages: [
    { id: 'raspberrypi', path: '//pub/electronics/sbcs/raspberrypi', name: 'raspberrypi', description: '', source_url: '', category: 'electronics', status: 'available' },
    { id: 'raspberrypi-boards', path: '//pub/electronics/sbcs/raspberrypi/boards', name: 'boards', description: '', source_url: '', category: 'electronics', status: 'available' },
    { id: 'raspberrypi-rpi5', path: '//pub/electronics/sbcs/raspberrypi/boards/rpi5', name: 'rpi5', description: '', source_url: '', category: 'electronics', status: 'available' },
  ] }],
}
const battery = {
  id: 'ego-battery', package_id: 'ego', package_path: '//pub/electrical/battery/ego',
  name: 'battery-7_5', kind: 'part', description: 'EGO battery', source_type: 'step',
  source_path: 'battery-7_5.step', source_url: 'https://github.com/partcad/partcad-electrical-ego',
  semantic_path: 'electrical/battery/ego:battery-7_5',
  visibility: 'public', git_commit: 'main', git_path: 'electrical/battery/ego/battery-7_5.step',
}

vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
  const value = String(input)
  return Promise.resolve({ ok: true, json: () => Promise.resolve(value.includes('/by-path/') ? battery : catalog) })
}) as unknown as typeof fetch)

test('renders the NarysAI repository identity', async () => {
  const { hook } = memoryLocation({ path: '/repository' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByText(/Креслення, готові/i)).toBeInTheDocument()
  expect(screen.getByText('NarysAI public')).toBeInTheDocument()
})

test('opens an object with a public PartCAD-compatible path', async () => {
  const { hook } = memoryLocation({ path: '/repository/part/electrical/battery/ego:battery-7_5' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByRole('heading', { name: 'battery-7_5' })).toBeInTheDocument()
  expect(screen.getByText('electrical/battery/ego:battery-7_5')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Відкрити файл у PUB/ })).toHaveAttribute(
    'href', 'https://github.com/NarysAI/PUB/blob/main/electrical/battery/ego/battery-7_5.step',
  )
  expect(screen.getByRole('link', { name: /Пакет у NarysAI/ })).toHaveAttribute('href', '/repository/package/ego')
})

test('groups child packages under their manufacturer package', async () => {
  const { hook } = memoryLocation({ path: '/repository' })
  render(<Router hook={hook}><App /></Router>)
  const manufacturer = await screen.findByRole('link', { name: 'raspberrypi' })
  const rpi5 = screen.getByRole('link', { name: 'rpi5' })
  expect(manufacturer.closest('details')).toContainElement(rpi5)
})
