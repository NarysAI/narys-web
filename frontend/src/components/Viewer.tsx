import { Bounds, Environment, OrbitControls, useGLTF } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useState } from 'react'
import * as THREE from 'three'
import { API, authorizedBlobUrl } from '../api'

function Model({ id }: { id: string }) {
  const { scene } = useGLTF(id)
  const greenScene = useMemo(() => {
    const clone = scene.clone(true)
    clone.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.material = new THREE.MeshStandardMaterial({
          color: '#109b68', roughness: 0.60, metalness: 0.04,
        })
        child.castShadow = true
        child.receiveShadow = true
      }
    })
    return clone
  }, [scene])
  return <primitive object={greenScene} />
}

export function Viewer({ id, privateObject = false }: { id: string; privateObject?: boolean }) {
  const [url, setUrl] = useState(privateObject ? '' : `${API}/api/v1/objects/${id}/preview.gltf`)
  useEffect(() => {
    if (!privateObject) { setUrl(`${API}/api/v1/objects/${id}/preview.gltf`); return }
    let active = true
    let blobUrl = ''
    authorizedBlobUrl(`/api/v1/objects/${id}/preview.gltf`).then((value) => {
      blobUrl = value
      if (active) setUrl(value)
    }).catch(() => setUrl(''))
    return () => { active = false; if (blobUrl) URL.revokeObjectURL(blobUrl) }
  }, [id, privateObject])
  return (
    <div className="viewer" aria-label="Інтерактивний 3D-переглядач">
      <Canvas camera={{ position: [3, 2.2, 3], fov: 42 }} shadows gl={{ toneMappingExposure: 0.72 }}>
        <color attach="background" args={['#101916']} />
        <ambientLight intensity={0.28} />
        <directionalLight position={[5, 7, 4]} intensity={1.15} color="#d8fff0" castShadow />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.25}>
            {url && <Model id={url} />}
          </Bounds>
          <Environment preset="warehouse" environmentIntensity={0.45} />
        </Suspense>
        <OrbitControls makeDefault />
        <gridHelper args={[10, 20, '#314b43', '#1c2b27']} position={[0, -1.2, 0]} />
      </Canvas>
      <div className="viewer-hint">Перетягніть для обертання · колесо для масштабу</div>
    </div>
  )
}
