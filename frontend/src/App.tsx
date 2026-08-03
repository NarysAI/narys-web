import { Box, Boxes, ChevronRight, Database, Download, ExternalLink, FileSearch, GitFork, LoaderCircle, Menu, RefreshCw, Search, Sparkles, X } from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, Route, Switch, useLocation, useRoute } from 'wouter'
import { API, getCatalog, getObject, getObjectByPath, getPackage, refresh, search } from './api'
import { Viewer } from './components/Viewer'
import type { Catalog, CatalogObject, Package } from './types'

function Logo() {
  return <Link className="brand" href="/repository"><span className="brand-mark">N</span><span><b>Narys</b><i>AI</i></span></Link>
}

function Header({ onMenu }: { onMenu: () => void }) {
  const [, navigate] = useLocation()
  const [query, setQuery] = useState('')
  const submit = (event: FormEvent) => { event.preventDefault(); if (query.trim()) navigate(`/repository?q=${encodeURIComponent(query.trim())}`) }
  return <header><button className="icon-button menu-button" onClick={onMenu} aria-label="Відкрити каталог"><Menu /></button><Logo /><form className="global-search" onSubmit={submit}><Search size={18} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Пошук деталей, збірок і пакетів…" aria-label="Пошук" /></form><a className="github-link" href="https://github.com/NarysAI" target="_blank" rel="noreferrer"><GitFork size={18} /> GitHub</a></header>
}

function Sidebar({ catalog, open, close }: { catalog: Catalog | null; open: boolean; close: () => void }) {
  return <aside className={open ? 'sidebar open' : 'sidebar'}><div className="sidebar-head"><span>Каталог пакетів</span><button className="icon-button sidebar-close" onClick={close}><X /></button></div><nav><Link href="/repository" onClick={close}><Database size={17} /> Усі пакети <span>{catalog?.package_count ?? 0}</span></Link>{catalog?.categories.map((category) => <details key={category.name} open={category.name === 'narysai'}><summary><ChevronRight size={15} /> {category.name}<span>{category.packages.length}</span></summary>{category.packages.map((pkg) => <Link className="package-link" key={pkg.id} href={`/repository/package/${pkg.id}`} onClick={close}>{pkg.name}</Link>)}</details>)}</nav><div className="sidebar-note"><Sparkles size={18} /><div><strong>AI-ready engineering</strong><p>Версійовані моделі, метадані та відкриті формати.</p></div></div></aside>
}

function ObjectCard({ item }: { item: CatalogObject }) {
  return <Link className="object-card" href={`/repository/${item.kind}/${item.semantic_path}`}><div className="object-preview"><img src={`${API}/api/v1/objects/${item.id}/thumbnail.png`} alt="" /><span>{item.kind}</span></div><div className="object-copy"><small>{item.package_path}</small><h3>{item.name}</h3><p>{item.description}</p><div><span>{item.source_type.toUpperCase()}</span><ChevronRight size={17} /></div></div></Link>
}

function Home({ catalog, reload }: { catalog: Catalog | null; reload: () => Promise<void> }) {
  const params = new URLSearchParams(location.search)
  const query = params.get('q') || ''
  const [results, setResults] = useState<((Package | CatalogObject) & { result_type: string })[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (!query) { setResults([]); return }; setBusy(true); search(query).then((data) => setResults(data.results)).catch((e) => setError(e.message)).finally(() => setBusy(false)) }, [query])
  const narysPackages = useMemo(() => catalog?.categories.find((item) => item.name === 'narysai')?.packages ?? [], [catalog])
  const doRefresh = async () => { setBusy(true); try { await refresh(); await reload() } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  if (query) return <main><div className="breadcrumbs"><Link href="/repository">Repository</Link><ChevronRight size={15} /><span>Пошук</span></div><div className="page-title"><div><span className="eyebrow">Результати пошуку</span><h1>“{query}”</h1><p>{busy ? 'Шукаємо…' : `Знайдено: ${results.length}`}</p></div></div>{error && <ErrorBox text={error} />}{!busy && !results.length && <Empty /> }<div className="results-list">{results.map((result) => result.result_type === 'object' ? <ObjectCard key={result.id} item={result as CatalogObject} /> : <PackageCard key={result.id} pkg={result as Package} />)}</div></main>
  return <main><section className="hero"><div><span className="eyebrow"><span className="live-dot" /> Локальний інженерний реєстр</span><h1>Креслення, готові<br />до роботи з <em>ШІ.</em></h1><p>NarysAI об’єднує відкриті PartCAD-пакети та ваші власні моделі в одному локальному, версійованому каталозі.</p><div className="hero-actions"><a href="#narys">Переглянути каталог <ChevronRight size={18} /></a><button onClick={doRefresh} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /> Оновити індекс</button></div></div><div className="hero-stat"><Boxes /><strong>{catalog?.package_count ?? '—'}</strong><span>доступних пакетів</span><div><span>{catalog?.object_count ?? 0}</span> об’єктів уже проіндексовано</div></div></section>{error && <ErrorBox text={error} />}<section id="narys" className="section"><div className="section-head"><div><span className="eyebrow">NarysAI collection</span><h2>Власні пакети</h2></div><span>{narysPackages.length} пакетів</span></div><div className="package-grid">{narysPackages.map((pkg) => <PackageCard key={pkg.id} pkg={pkg} />)}</div></section>{catalog?.featured.length ? <section className="section"><div className="section-head"><div><span className="eyebrow">Recently indexed</span><h2>Інженерні об’єкти</h2></div></div><div className="object-grid">{catalog.featured.map((item) => <ObjectCard key={item.id} item={item} />)}</div></section> : null}</main>
}

function PackageCard({ pkg }: { pkg: Package }) { return <Link className="package-card" href={`/repository/package/${pkg.id}`}><div><Box /><span>{pkg.status}</span></div><small>{pkg.path}</small><h3>{pkg.name}</h3><p>{pkg.description}</p><footer>Відкрити пакет <ChevronRight size={17} /></footer></Link> }

function PackagePage() {
  const [, params] = useRoute('/repository/package/:id'); const id = params?.id ?? ''; const [data, setData] = useState<(Package & { objects: CatalogObject[] }) | null>(null); const [error, setError] = useState('')
  useEffect(() => { getPackage(id).then(setData).catch((e) => setError(e.message)) }, [id])
  if (error) return <main><ErrorBox text={error} /></main>; if (!data) return <Loading />
  return <main><div className="breadcrumbs"><Link href="/repository">Repository</Link><ChevronRight size={15} /><span>{data.name}</span></div><div className="page-title"><div><span className="eyebrow">PartCAD package</span><h1>{data.name}</h1><p>{data.description}</p></div><div className="page-actions"><a href={`${API}/api/v1/packages/${data.id}/archive.zip`} download><Download size={16} /> Завантажити пакет</a><a className="upstream-link" href={data.source_url} target="_blank" rel="noreferrer">Upstream <ExternalLink size={16} /></a></div></div>{data.objects.length ? <div className="object-grid">{data.objects.map((item) => <ObjectCard key={item.id} item={item} />)}</div> : <Empty />}</main>
}

function ObjectPage() {
  const [, params] = useRoute('/repository/object/:id'); const id = params?.id ?? ''; const [item, setItem] = useState<CatalogObject | null>(null); const [error, setError] = useState('')
  useEffect(() => { getObject(id).then(setItem).catch((e) => setError(e.message)) }, [id])
  if (error) return <main><ErrorBox text={error} /></main>; if (!item) return <Loading />
  return <ObjectDetail item={item} />
}

function SemanticObjectPage() {
  const [location] = useLocation(); const [item, setItem] = useState<CatalogObject | null>(null); const [error, setError] = useState('')
  const match = location.match(/^\/repository\/(part|assembly|sketch)\/(.+)$/)
  const kind = match?.[1] ?? ''; const semanticPath = match?.[2] ? decodeURI(match[2]) : ''
  useEffect(() => { if (kind && semanticPath) getObjectByPath(kind, semanticPath).then(setItem).catch((e) => setError(e.message)) }, [kind, semanticPath])
  if (error) return <main><ErrorBox text={error} /></main>; if (!item) return <Loading />
  return <ObjectDetail item={item} />
}

function ObjectDetail({ item }: { item: CatalogObject }) {
  return <main><div className="breadcrumbs"><Link href="/repository">Repository</Link><ChevronRight size={15} /><Link href={`/repository/package/${item.package_id}`}>{item.package_path}</Link><ChevronRight size={15} /><span>{item.name}</span></div><div className="detail-layout"><Viewer id={item.id} /><article className="detail-panel"><span className="type-pill">{item.kind}</span><h1>{item.name}</h1><p>{item.description}</p><dl><div><dt>Формат</dt><dd>{item.source_type.toUpperCase()}</dd></div><div><dt>PartCAD path</dt><dd>{item.semantic_path}</dd></div><div><dt>Пакет</dt><dd>{item.package_path}</dd></div><div><dt>Файл</dt><dd>{item.source_path || 'генерований'}</dd></div><div><dt>Ліцензія</dt><dd>{item.license || 'див. пакет NarysAI'}</dd></div></dl>{item.source_path && <a className="source-button" href={`${API}/api/v1/objects/${item.id}/source`} download><Download size={17} /> Завантажити вихідний файл</a>}<Link className="package-source-link" href={`/repository/package/${item.package_id}`}>Пакет у NarysAI <ChevronRight size={16} /></Link></article></div></main>
}

function Loading() { return <main className="center-state"><LoaderCircle className="spin" /><h2>Завантажуємо пакет…</h2></main> }
function ErrorBox({ text }: { text: string }) { return <div className="error-box"><strong>Не вдалося завантажити</strong><span>{text}</span></div> }
function Empty() { return <div className="empty"><FileSearch /><h2>Нічого не знайдено</h2><p>Спробуйте інший запит або оновіть індекс.</p></div> }

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null); const [menu, setMenu] = useState(false); const [error, setError] = useState('')
  const load = async () => { try { setCatalog(await getCatalog()) } catch (e) { setError((e as Error).message) } }
  useEffect(() => { load() }, [])
  return <div className="app-shell"><Header onMenu={() => setMenu(true)} /><Sidebar catalog={catalog} open={menu} close={() => setMenu(false)} /><div className="content">{error && <ErrorBox text={error} />}<Switch><Route path="/repository/package/:id"><PackagePage /></Route><Route path="/repository/object/:id"><ObjectPage /></Route><Route path="/repository/:kind/*"><SemanticObjectPage /></Route><Route path="/repository"><Home catalog={catalog} reload={load} /></Route><Route><Home catalog={catalog} reload={load} /></Route></Switch></div></div>
}
