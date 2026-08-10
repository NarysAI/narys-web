import { fireEvent, render, screen, within } from '@testing-library/react'
import { vi } from 'vitest'
import { Router } from 'wouter'
import { memoryLocation } from 'wouter/memory-location'
import App from './App'

vi.mock('./components/Viewer', () => ({ Viewer: () => <div>3D viewer</div> }))

const catalog = {
  name: 'NarysAI Registry', package_count: 3, object_count: 0, featured: [],
  categories: [{ name: 'electronics', packages: [
    { id: 'raspberrypi', path: '//pub/electronics/sbcs/raspberrypi', name: 'raspberrypi', description: '', source_url: '', category: 'electronics', status: 'available', visibility: 'public', entry_type: 'package' },
    { id: 'raspberrypi-boards', path: '//pub/electronics/sbcs/raspberrypi/boards', name: 'boards', description: '', source_url: '', category: 'electronics', status: 'available', visibility: 'public', entry_type: 'package' },
    { id: 'raspberrypi-rpi5', path: '//pub/electronics/sbcs/raspberrypi/boards/rpi5', name: 'rpi5', description: '', source_url: '', category: 'electronics', status: 'available', visibility: 'public', entry_type: 'package' },
  ] }, { name: 'fpv', packages: [
    { id: 'case-project', path: '//pub/fpv/case-holder', name: 'Case_holder', description: 'FPV project', source_url: 'https://github.com/NarysAI/Case_holder.git', category: 'fpv', status: 'loaded', visibility: 'public', entry_type: 'project' },
  ] }],
}
const battery = {
  id: 'ego-battery', package_id: 'ego', package_path: '//pub/electrical/battery/ego',
  name: 'battery-7_5', kind: 'part', description: 'EGO battery', source_type: 'step',
  source_path: 'battery-7_5.step', source_url: 'https://github.com/partcad/partcad-electrical-ego',
  semantic_path: 'electrical/battery/ego:battery-7_5',
  visibility: 'public', git_commit: 'main', git_path: 'electrical/battery/ego/battery-7_5.step',
  model_role: 'electronic_component',
}
const caseProject = {
  id: 'case-project', path: '//pub/fpv/case-holder', name: 'Case_holder',
  description: 'FPV project', source_url: 'https://github.com/NarysAI/Case_holder.git',
  category: 'fpv', status: 'loaded', visibility: 'public', entry_type: 'project',
  canonical_repo_url: 'https://github.com/NarysAI/Case_holder', default_branch: 'main',
  contribution_url: 'https://github.com/NarysAI/Case_holder/blob/main/CONTRIBUTING.md',
  issues_url: 'https://github.com/NarysAI/Case_holder/issues', current_drawing: 'drawing-v1.0.0',
  pub_url: 'https://github.com/NarysAI/PUB/tree/main/fpv/case-holder', objects: [],
}

vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
  const value = String(input)
  const payload = value.includes('/by-path/') ? battery : value.includes('/packages/case-project') ? caseProject : catalog
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) })
}) as unknown as typeof fetch)

test('renders the NarysAI repository identity', async () => {
  const { hook } = memoryLocation({ path: '/repository' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByText(/Креслення і проєкти/i)).toBeInTheDocument()
  expect(screen.getByText('NarysAI public')).toBeInTheDocument()
})

test('opens an object with a public PartCAD-compatible path', async () => {
  const { hook } = memoryLocation({ path: '/repository/part/electrical/battery/ego:battery-7_5' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByRole('heading', { name: 'battery-7_5' })).toBeInTheDocument()
  expect(screen.getByText('electrical/battery/ego:battery-7_5')).toBeInTheDocument()
  expect(screen.getByText('Electronic component · AI SCAD')).toBeInTheDocument()
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

test('filters the unified catalog to FPV projects', async () => {
  const { hook } = memoryLocation({ path: '/repository' })
  render(<Router hook={hook}><App /></Router>)
  await screen.findByText(/Креслення і проєкти/i)
  fireEvent.click(screen.getByRole('button', { name: 'Проєкти' }))
  const main = within(screen.getByRole('main'))
  expect(await main.findByRole('heading', { name: 'Case_holder' })).toBeInTheDocument()
  expect(main.queryByRole('heading', { name: 'raspberrypi' })).not.toBeInTheDocument()
})

test('shows collaboration actions for a project', async () => {
  const { hook } = memoryLocation({ path: '/repository/package/case-project' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByRole('heading', { name: 'Case_holder' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Git repository/ })).toHaveAttribute('href', 'https://github.com/NarysAI/Case_holder')
  expect(screen.getByRole('link', { name: /Issues/ })).toHaveAttribute('href', 'https://github.com/NarysAI/Case_holder/issues')
  expect(screen.getByText('drawing-v1.0.0')).toBeInTheDocument()
})
