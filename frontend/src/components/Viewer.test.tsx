import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { vi } from 'vitest'
import { Viewer } from './Viewer'

const { useGLTFMock } = vi.hoisted(() => ({
  useGLTFMock: vi.fn(() => { throw new Error('preview failed') }),
}))

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@react-three/drei', () => ({
  Bounds: ({ children }: { children: ReactNode }) => <>{children}</>,
  Environment: () => null,
  OrbitControls: () => null,
  useGLTF: useGLTFMock,
}))

test('keeps the object page usable when the 3D preview fails', () => {
  render(<Viewer id="broken-preview" />)
  expect(screen.getByRole('status')).toHaveTextContent('3D-прев’ю тимчасово недоступне')
})

test('builds a stable preview URL from applied parameters', () => {
  render(<Viewer id="standoff" parameters={{ thread_diameter: 2.5, body_length: 12 }} />)
  expect(useGLTFMock).toHaveBeenCalledWith(
    '/api/v1/objects/standoff/preview.gltf?body_length=12&thread_diameter=2.5',
  )
})
