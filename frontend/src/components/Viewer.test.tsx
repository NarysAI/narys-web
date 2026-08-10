import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { vi } from 'vitest'
import { Viewer } from './Viewer'

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@react-three/drei', () => ({
  Bounds: ({ children }: { children: ReactNode }) => <>{children}</>,
  Environment: () => null,
  OrbitControls: () => null,
  useGLTF: () => { throw new Error('preview failed') },
}))

test('keeps the object page usable when the 3D preview fails', () => {
  render(<Viewer id="broken-preview" />)
  expect(screen.getByRole('status')).toHaveTextContent('3D-прев’ю тимчасово недоступне')
})
