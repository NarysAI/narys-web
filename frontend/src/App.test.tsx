import { fireEvent, render, screen, within } from '@testing-library/react'
import { vi } from 'vitest'
import { Router } from 'wouter'
import { memoryLocation } from 'wouter/memory-location'
import App from './App'

vi.mock('./components/Viewer', () => ({
  Viewer: ({ parameters }: { parameters?: Record<string, number | string> }) => (
    <div data-testid="viewer-parameters">{JSON.stringify(parameters || {})}</div>
  ),
}))

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
const standoff = {
  id: 'standoff-mf', package_id: 'standoffs', package_path: '//pub/std/metric/standoffs',
  name: 'hex-standoff-male-female', kind: 'part', description: 'Metric standoff',
  source_type: 'scad', source_path: 'hex-standoff-male-female.scad', source_url: '',
  semantic_path: 'std/metric/standoffs:hex-standoff-male-female', visibility: 'public',
  parameters: {
    thread_diameter: { type: 'float', default: 3, min: 2, max: 6, hidden: true, options: [2, 3] },
    body_length: { type: 'float', default: 10, min: 4, max: 100, options: [6, 10] },
  },
  parameter_presets: [
    { id: 'm2', label: 'M2 · SW4 · L6', parameters: { thread_diameter: 2, body_length: 6 } },
    { id: 'm3', label: 'M3 · SW5.5 · L10', parameters: { thread_diameter: 3, body_length: 10 } },
  ],
  default_parameter_preset: 'm3',
}
const h30Enclosed = {
  id: 'h30-enclosed', package_id: 'wheeltec-h30', package_path: '//pub/electronics/modules/wheeltec-h30',
  name: 'h30-enclosed', kind: 'part', description: 'WHEELTEC H30 in metal housing',
  source_type: 'scad', source_path: 'h30-enclosed.scad', source_url: '',
  semantic_path: 'electronics/modules/wheeltec-h30:h30-enclosed', visibility: 'public',
  product_family: { id: 'wheeltec-h30', name: 'WHEELTEC H30' },
  product_variant: { id: 'h30-enclosed', name: 'H30 Enclosed', kind: 'enclosed', revision: '1.0' },
  base_variant: { kind: 'part', semantic_path: 'electronics/modules/wheeltec-h30:h30-pcb', label: 'H30 PCB' },
  components: [
    { kind: 'part', semantic_path: 'electronics/modules/wheeltec-h30:h30-pcb', label: 'H30 PCB', quantity: 1, role: 'electronics', modeled: true },
    { label: 'Metal enclosure', quantity: 1, role: 'housing', modeled: true },
    { label: 'M3 cover screws', quantity: 2, role: 'fastener', modeled: true },
  ],
}

vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
  const value = String(input)
  const payload = value.includes('std/metric/standoffs')
    ? standoff
    : value.includes('wheeltec-h30:h30-enclosed')
      ? h30Enclosed
    : value.includes('/by-path/')
      ? battery
      : value.includes('/packages/case-project')
        ? caseProject
        : catalog
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

test('shows an exact product variant, base model, and BOM', async () => {
  const { hook } = memoryLocation({ path: '/repository/part/electronics/modules/wheeltec-h30:h30-enclosed' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByRole('heading', { name: 'H30 Enclosed' })).toBeInTheDocument()
  expect(screen.getByText('WHEELTEC H30')).toBeInTheDocument()
  expect(screen.getByText('v1.0')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: 'H30 PCB' })[0]).toHaveAttribute(
    'href', '/repository/part/electronics/modules/wheeltec-h30:h30-pcb',
  )
  expect(screen.getByText('Metal enclosure')).toBeInTheDocument()
  expect(screen.getByText('M3 cover screws')).toBeInTheDocument()
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

test('applies a standoff size preset only after confirmation', async () => {
  const { hook } = memoryLocation({ path: '/repository/part/std/metric/standoffs:hex-standoff-male-female' })
  render(<Router hook={hook}><App /></Router>)
  expect(await screen.findByRole('heading', { name: 'hex-standoff-male-female' })).toBeInTheDocument()
  expect(screen.getByTestId('viewer-parameters')).toHaveTextContent('"thread_diameter":3')
  fireEvent.change(screen.getByLabelText('Типорозмір'), { target: { value: 'm2' } })
  expect(screen.getByTestId('viewer-parameters')).toHaveTextContent('"thread_diameter":3')
  fireEvent.click(screen.getByRole('button', { name: 'Показати' }))
  expect(screen.getByTestId('viewer-parameters')).toHaveTextContent('"thread_diameter":2')
  expect(screen.getByTestId('viewer-parameters')).toHaveTextContent('"body_length":6')
})
