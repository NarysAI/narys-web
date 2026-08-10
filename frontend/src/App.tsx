import {
  Box,
  Boxes,
  ChevronRight,
  Database,
  Download,
  ExternalLink,
  FileSearch,
  GitFork,
  KeyRound,
  LoaderCircle,
  Lock,
  LogOut,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import {
  createContext,
  FormEvent,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Link, Route, Switch, useLocation, useRoute } from "wouter";
import {
  API,
  authenticate,
  createDownloadTicket,
  createAdminKey,
  getAdminKeys,
  getAdminSyncRuns,
  getAudit,
  getCatalog,
  getObject,
  getObjectByPath,
  getPackage,
  refresh,
  revokeAdminKey,
  search,
  setApiKey,
} from "./api";
import { Viewer } from "./components/Viewer";
import type { Catalog, CatalogObject, Package, Principal } from "./types";

const AuthContext = createContext<{ principal: Principal | null }>({
  principal: null,
});

function Logo() {
  return (
    <Link className="brand" href="/repository">
      <span className="brand-mark">N</span>
      <span>
        <b>Narys</b>
        <i>AI</i>
      </span>
    </Link>
  );
}

function Header({
  onMenu,
  principal,
  onLogin,
  onLogout,
}: {
  onMenu: () => void;
  principal: Principal | null;
  onLogin: (key: string) => Promise<void>;
  onLogout: () => void;
}) {
  const [, navigate] = useLocation();
  const [query, setQuery] = useState("");
  const [key, setKey] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (query.trim())
      navigate(`/repository?q=${encodeURIComponent(query.trim())}`);
  };
  const login = async (event: FormEvent) => {
    event.preventDefault();
    if (key.trim()) {
      await onLogin(key.trim());
      setKey("");
    }
  };
  return (
    <header>
      <button
        className="icon-button menu-button"
        onClick={onMenu}
        aria-label="Відкрити каталог"
      >
        <Menu />
      </button>
      <Logo />
      <form className="global-search" onSubmit={submit}>
        <Search size={18} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Пошук деталей, збірок і пакетів…"
          aria-label="Пошук"
        />
      </form>
      {principal ? (
        <button className="auth-chip" onClick={onLogout}>
          <Lock size={15} /> {principal.name} <LogOut size={15} />
        </button>
      ) : (
        <form className="auth-form" onSubmit={login}>
          <KeyRound size={15} />
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="API key"
            aria-label="API key"
          />
          <button>Увійти</button>
        </form>
      )}
      <a
        className="github-link"
        href="https://github.com/NarysAI"
        target="_blank"
        rel="noreferrer"
      >
        <GitFork size={18} /> GitHub
      </a>
    </header>
  );
}

function Sidebar({
  catalog,
  open,
  close,
}: {
  catalog: Catalog | null;
  open: boolean;
  close: () => void;
}) {
  const { principal } = useContext(AuthContext);
  return (
    <aside className={open ? "sidebar open" : "sidebar"}>
      <div className="sidebar-head">
        <span>Єдиний каталог</span>
        <button className="icon-button sidebar-close" onClick={close}>
          <X />
        </button>
      </div>
      <nav>
        <Link href="/repository" onClick={close}>
          <Database size={17} /> Усі записи{" "}
          <span>{catalog?.package_count ?? 0}</span>
        </Link>
        {principal?.role === "admin" && (
          <Link href="/repository/admin" onClick={close}>
            <KeyRound size={17} /> Адміністрування
          </Link>
        )}
        {catalog?.categories.map((category) => (
          <details key={category.name} open={category.name === "narysai"}>
            <summary>
              <ChevronRight size={15} /> {category.name.toLowerCase() === "fpv" ? "FPV" : category.name}
              <span>{category.packages.length}</span>
            </summary>
            <PackageTree packages={category.packages} close={close} />
          </details>
        ))}
      </nav>
      <div className="sidebar-note">
        <Sparkles size={18} />
        <div>
          <strong>AI-ready engineering</strong>
          <p>Версійовані моделі, метадані та відкриті формати.</p>
        </div>
      </div>
    </aside>
  );
}

type PackageNode = {
  package: Package;
  children: PackageNode[];
};

function buildPackageTree(packages: Package[]): PackageNode[] {
  const nodes = new Map(
    packages.map((pkg) => [pkg.path, { package: pkg, children: [] as PackageNode[] }]),
  );
  const roots: PackageNode[] = [];

  for (const node of nodes.values()) {
    const parent = [...nodes.values()]
      .filter((candidate) =>
        node.package.path.startsWith(`${candidate.package.path}/`),
      )
      .sort((left, right) => right.package.path.length - left.package.path.length)[0];

    if (parent) parent.children.push(node);
    else roots.push(node);
  }

  const sortNodes = (items: PackageNode[]) => {
    items.sort((left, right) => left.package.name.localeCompare(right.package.name));
    items.forEach((item) => sortNodes(item.children));
  };
  sortNodes(roots);
  return roots;
}

function PackageTree({ packages, close }: { packages: Package[]; close: () => void }) {
  const tree = useMemo(() => buildPackageTree(packages), [packages]);
  return <div className="package-tree">{tree.map((node) => (
    <PackageTreeNode key={node.package.id} node={node} close={close} depth={0} />
  ))}</div>;
}

function PackageTreeNode({
  node,
  close,
  depth,
}: {
  node: PackageNode;
  close: () => void;
  depth: number;
}) {
  const link = (
    <Link
      className="package-link"
      href={`/repository/package/${node.package.id}`}
      onClick={close}
      style={{ paddingLeft: `${34 + depth * 16}px` }}
    >
      {node.package.name}
    </Link>
  );

  if (!node.children.length) return link;

  return (
    <details
      className="package-group"
      open={node.package.path.includes("/raspberrypi")}
    >
      <summary style={{ paddingLeft: `${22 + depth * 16}px` }}>
        <ChevronRight size={13} />
        <Link href={`/repository/package/${node.package.id}`} onClick={close}>
          {node.package.name}
        </Link>
        <span>{node.children.length}</span>
      </summary>
      {node.children.map((child) => (
        <PackageTreeNode
          key={child.package.id}
          node={child}
          close={close}
          depth={depth + 1}
        />
      ))}
    </details>
  );
}

function ObjectCard({ item }: { item: CatalogObject }) {
  const displayName = item.product_variant?.name || item.name;
  return (
    <Link
      className="object-card"
      href={`/repository/${item.kind}/${item.semantic_path}`}
    >
      <div className="object-preview">
        {item.visibility === "private" ? (
          <Lock className="private-preview" />
        ) : (
          <img src={`${API}/api/v1/objects/${item.id}/thumbnail.png`} alt="" />
        )}
        <span>{item.visibility === "private" ? "private" : item.kind}</span>
      </div>
      <div className="object-copy">
        <small>{item.package_path}</small>
        <h3>
          {item.visibility === "private" && <Lock size={15} />} {displayName}
        </h3>
        <p>{item.description}</p>
        <div>
          <span>{item.source_type.toUpperCase()}</span>
          <ChevronRight size={17} />
        </div>
      </div>
    </Link>
  );
}

function Home({
  catalog,
  reload,
}: {
  catalog: Catalog | null;
  reload: () => Promise<void>;
}) {
  const { principal } = useContext(AuthContext);
  const [scope, setScope] = useState<"public" | "private">("public");
  const [entryFilter, setEntryFilter] = useState<"all" | "package" | "project">("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const params = new URLSearchParams(location.search);
  const query = params.get("q") || "";
  const [results, setResults] = useState<
    ((Package | CatalogObject) & { result_type: string })[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!query) {
      setResults([]);
      return;
    }
    setBusy(true);
    search(query)
      .then((data) => setResults(data.results))
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  }, [query]);
  const scopedPackages = useMemo(
    () =>
      catalog?.categories
        .flatMap((item) => item.packages)
        .filter((item) => item.visibility === scope)
        .filter((item) => entryFilter === "all" || (item.entry_type || "package") === entryFilter)
        .filter((item) => categoryFilter === "all" || item.category === categoryFilter) ?? [],
    [catalog, scope, entryFilter, categoryFilter],
  );
  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          catalog?.categories
            .flatMap((item) => item.packages)
            .filter((item) => item.visibility === scope)
            .map((item) => item.category) ?? [],
        ),
      ).sort(),
    [catalog, scope],
  );
  const doRefresh = async () => {
    setBusy(true);
    try {
      await refresh();
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (query)
    return (
      <main>
        <div className="breadcrumbs">
          <Link href="/repository">Repository</Link>
          <ChevronRight size={15} />
          <span>Пошук</span>
        </div>
        <div className="page-title">
          <div>
            <span className="eyebrow">Результати пошуку</span>
            <h1>“{query}”</h1>
            <p>{busy ? "Шукаємо…" : `Знайдено: ${results.length}`}</p>
          </div>
        </div>
        {error && <ErrorBox text={error} />}
        {!busy && !results.length && <Empty />}
        <div className="results-list">
          {results.map((result) =>
            result.result_type === "object" ? (
              <ObjectCard key={result.id} item={result as CatalogObject} />
            ) : (
              <PackageCard key={result.id} pkg={result as Package} />
            ),
          )}
        </div>
      </main>
    );
  return (
    <main>
      <section className="hero">
        <div>
          <span className="eyebrow">
            <span className="live-dot" /> Локальний інженерний реєстр
          </span>
          <h1>
            Креслення і проєкти,
            <br />
            до роботи з <em>ШІ.</em>
          </h1>
          <p>
            NarysAI об’єднує готові PartCAD-пакети, відкриті Git-проєкти та
            захищені командні розробки в одному версійованому каталозі.
          </p>
          <div className="hero-actions">
            <a href="#narys">
              Переглянути каталог <ChevronRight size={18} />
            </a>
            {principal?.role === "admin" && (
              <button onClick={doRefresh} disabled={busy}>
                <RefreshCw size={17} className={busy ? "spin" : ""} /> Оновити
                індекс
              </button>
            )}
          </div>
        </div>
        <div className="hero-stat">
          <Boxes />
          <strong>{catalog?.package_count ?? "—"}</strong>
          <span>доступних записів</span>
          <div>
            <span>{catalog?.object_count ?? 0}</span> об’єктів уже
            проіндексовано
          </div>
        </div>
      </section>
      {error && <ErrorBox text={error} />}
      {principal && (
        <div
          className="scope-switch"
          role="group"
          aria-label="Видимість каталогу"
        >
          <button
            className={scope === "public" ? "active" : ""}
            onClick={() => setScope("public")}
          >
            Public
          </button>
          <button
            className={scope === "private" ? "active" : ""}
            onClick={() => setScope("private")}
          >
            Private
          </button>
        </div>
      )}
      <div className="catalog-filters" aria-label="Фільтри каталогу">
        <div className="scope-switch" role="group" aria-label="Тип запису">
          <button className={entryFilter === "all" ? "active" : ""} onClick={() => setEntryFilter("all")}>Усі</button>
          <button className={entryFilter === "package" ? "active" : ""} onClick={() => setEntryFilter("package")}>Готові креслення</button>
          <button className={entryFilter === "project" ? "active" : ""} onClick={() => setEntryFilter("project")}>Проєкти</button>
        </div>
        <label>
          <span>Категорія</span>
          <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="all">Усі категорії</option>
            {categories.map((category) => (
              <option key={category} value={category}>{category.toLowerCase() === "fpv" ? "FPV" : category}</option>
            ))}
          </select>
        </label>
      </div>
      <section id="narys" className="section">
        <div className="section-head">
          <div>
            <span className="eyebrow">NarysAI {scope}</span>
            <h2>{scope === "public" ? "Публічний каталог" : "Приватний каталог"}</h2>
          </div>
          <span>{scopedPackages.length} пакетів</span>
        </div>
        <div className="package-grid">
          {scopedPackages.map((pkg) => (
            <PackageCard key={pkg.id} pkg={pkg} />
          ))}
        </div>
      </section>
      {catalog?.featured.length ? (
        <section className="section">
          <div className="section-head">
            <div>
              <span className="eyebrow">Recently indexed</span>
              <h2>Інженерні об’єкти</h2>
            </div>
          </div>
          <div className="object-grid">
            {catalog.featured.map((item) => (
              <ObjectCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}

function PackageCard({ pkg }: { pkg: Package }) {
  const project = pkg.entry_type === "project";
  return (
    <Link className="package-card" href={`/repository/package/${pkg.id}`}>
      <div>
        {project ? <GitFork /> : <Box />}
        <span>{project ? "project" : pkg.status}</span>
      </div>
      <small>{pkg.path}</small>
      <h3>{pkg.name}</h3>
      <p>{pkg.description}</p>
      <footer>
        {project ? "Відкрити проєкт" : "Відкрити пакет"} <ChevronRight size={17} />
      </footer>
    </Link>
  );
}

function PackagePage() {
  const [, params] = useRoute("/repository/package/:id");
  const id = params?.id ?? "";
  const [data, setData] = useState<
    (Package & { objects: CatalogObject[] }) | null
  >(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getPackage(id)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [id]);
  if (error)
    return (
      <main>
        <ErrorBox text={error} />
      </main>
    );
  if (!data) return <Loading />;
  const project = data.entry_type === "project";
  return (
    <main>
      <div className="breadcrumbs">
        <Link href="/repository">Repository</Link>
        <ChevronRight size={15} />
        <span>{data.name}</span>
      </div>
      <div className="page-title">
        <div>
          <span className="eyebrow">{project ? "NarysAI project" : "PartCAD package"}</span>
          <h1>{data.name}</h1>
          <p>{data.description}</p>
        </div>
        <div className="page-actions">
          {!project && data.visibility === "public" && (
            <a
              href={`https://github.com/NarysAI/PUB/tree/${data.git_commit || "main"}/${data.path.replace("//pub/", "")}`}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={16} /> Відкрити пакет у PUB
            </a>
          )}
          {project && data.canonical_repo_url && (
            <a href={data.canonical_repo_url} target="_blank" rel="noreferrer">
              <GitFork size={16} /> Git repository
            </a>
          )}
          {project && data.issues_url && (
            <a className="upstream-link" href={data.issues_url} target="_blank" rel="noreferrer">
              Issues <ExternalLink size={16} />
            </a>
          )}
          {project && data.contribution_url && (
            <a className="upstream-link" href={data.contribution_url} target="_blank" rel="noreferrer">
              Долучитися <ExternalLink size={16} />
            </a>
          )}
          {project && data.pub_url && (
            <a className="upstream-link" href={data.pub_url} target="_blank" rel="noreferrer">
              Покажчик у PUB <ExternalLink size={16} />
            </a>
          )}
          {!project && (
            <a className="upstream-link" href={data.upstream_url || data.source_url} target="_blank" rel="noreferrer">
              Upstream <ExternalLink size={16} />
            </a>
          )}
        </div>
      </div>
      {project && (
        <dl className="project-meta">
          <div><dt>Доступ</dt><dd>{data.visibility === "private" ? "Private" : "Open"}</dd></div>
          <div><dt>Гілка</dt><dd>{data.default_branch || "main"}</dd></div>
          <div><dt>Креслення</dt><dd>{data.current_drawing || "не вказано"}</dd></div>
          <div><dt>Clone URL</dt><dd>{data.canonical_repo_url ? `${data.canonical_repo_url}.git` : "захищено"}</dd></div>
        </dl>
      )}
      {data.objects.length ? (
        <div className="object-grid">
          {data.objects.map((item) => (
            <ObjectCard key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <Empty />
      )}
    </main>
  );
}

function ObjectPage() {
  const [, params] = useRoute("/repository/object/:id");
  const id = params?.id ?? "";
  const [item, setItem] = useState<CatalogObject | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getObject(id)
      .then(setItem)
      .catch((e) => setError(e.message));
  }, [id]);
  if (error)
    return (
      <main>
        <ErrorBox text={error} />
      </main>
    );
  if (!item) return <Loading />;
  return <ObjectDetail item={item} />;
}

function SemanticObjectPage() {
  const [location, setLocation] = useLocation();
  const [item, setItem] = useState<CatalogObject | null>(null);
  const [error, setError] = useState("");
  const match = location.match(/^\/repository\/(part|assembly|sketch)\/(.+)$/);
  const kind = match?.[1] ?? "";
  const semanticPath = match?.[2] ? decodeURI(match[2]) : "";
  useEffect(() => {
    if (kind && semanticPath)
      getObjectByPath(kind, semanticPath)
        .then(setItem)
        .catch((e) => setError(e.message));
  }, [kind, semanticPath]);
  useEffect(() => {
    if (!item) return;
    const canonicalLocation = `/repository/${item.kind}/${item.semantic_path}`;
    if (canonicalLocation !== location)
      setLocation(canonicalLocation, { replace: true });
  }, [item, location, setLocation]);
  if (error)
    return (
      <main>
        <ErrorBox text={error} />
      </main>
    );
  if (!item) return <Loading />;
  return <ObjectDetail item={item} />;
}

const parameterLabels: Record<string, string> = {
  thread_diameter: "Діаметр різьби, мм",
  thread_pitch: "Крок різьби, мм",
  body_length: "Довжина корпусу, мм",
  hex_width: "Розмір під ключ, мм",
  male_length: "Довжина зовнішньої різьби, мм",
  female_depth: "Глибина внутрішньої різьби, мм",
  bevel: "Фаска, мм",
};

const objectReferenceHref = (kind: string, semanticPath: string) =>
  `/repository/${kind}/${semanticPath}`;

function ObjectDetail({ item }: { item: CatalogObject }) {
  const { principal } = useContext(AuthContext);
  const displayName = item.product_variant?.name || item.name;
  const parameterDefaults = useMemo(
    () => Object.fromEntries(
      Object.entries(item.parameters || {}).map(([name, declaration]) => [name, declaration.default]),
    ) as Record<string, number | boolean | string>,
    [item.parameters],
  );
  const initialPreset = item.default_parameter_preset || item.parameter_presets?.[0]?.id || "";
  const initialParameters = useMemo(() => ({
    ...parameterDefaults,
    ...(item.parameter_presets?.find((candidate) => candidate.id === initialPreset)?.parameters || {}),
  }), [initialPreset, item.parameter_presets, parameterDefaults]);
  const [draftParameters, setDraftParameters] = useState(initialParameters);
  const [appliedParameters, setAppliedParameters] = useState(initialParameters);
  const [presetId, setPresetId] = useState(initialPreset);
  useEffect(() => {
    setDraftParameters(initialParameters);
    setAppliedParameters(initialParameters);
    setPresetId(initialPreset);
  }, [item.id, initialParameters, initialPreset]);
  const applyParameters = (event: FormEvent) => {
    event.preventDefault();
    const values = Object.fromEntries(
      Object.entries(draftParameters).map(([name, value]) => {
        const declaration = item.parameters?.[name];
        return [name, declaration?.type === "int" ? Number.parseInt(String(value), 10) : Number(value)];
      }),
    );
    setAppliedParameters(values);
  };
  const selectPreset = (id: string) => {
    setPresetId(id);
    const preset = item.parameter_presets?.find((candidate) => candidate.id === id);
    setDraftParameters({ ...parameterDefaults, ...(preset?.parameters || {}) });
  };
  const resetParameters = () => {
    setDraftParameters(initialParameters);
    setAppliedParameters(initialParameters);
    setPresetId(initialPreset);
  };
  const privateDownload = async () => {
    const data = await createDownloadTicket(item.id);
    window.location.assign(`${API}/api/v1/downloads/${data.ticket}`);
  };
  const gitUrl = item.entry_type === "project" && item.canonical_repo_url
    ? `${item.canonical_repo_url}/blob/${item.git_commit || item.default_branch || "main"}/${item.git_path || ""}`
    : `https://github.com/NarysAI/PUB/blob/${item.git_commit || "main"}/${item.git_path || ""}`;
  return (
    <main>
      <div className="breadcrumbs">
        <Link href="/repository">Repository</Link>
        <ChevronRight size={15} />
        <Link href={`/repository/package/${item.package_id}`}>
          {item.package_path}
        </Link>
        <ChevronRight size={15} />
        <span>{displayName}</span>
      </div>
      <div className="detail-layout">
        <Viewer
          id={item.id}
          privateObject={item.visibility === "private"}
          parameters={appliedParameters}
        />
        <article className="detail-panel">
          <span className="type-pill">
            {item.visibility === "private" ? "private" : item.kind}
          </span>
          <h1>{displayName}</h1>
          <p>{item.description}</p>
          {item.product_family && item.product_variant && (
            <section className="product-variant" aria-label="Архітектура варіанта">
              <div className="product-variant-head">
                <span>Сімейство виробу</span>
                <strong>{item.product_family.name}</strong>
              </div>
              <dl className="variant-summary">
                <div><dt>Точний варіант</dt><dd>{item.product_variant.name}</dd></div>
                <div><dt>Тип</dt><dd>{item.product_variant.kind}</dd></div>
                <div><dt>Ревізія</dt><dd>v{item.product_variant.revision}</dd></div>
              </dl>
              {item.base_variant && (
                <div className="base-variant">
                  <span>Базова модель</span>
                  <Link href={objectReferenceHref(item.base_variant.kind, item.base_variant.semantic_path)}>
                    {item.base_variant.label} <ChevronRight size={15} />
                  </Link>
                </div>
              )}
              {item.components && item.components.length > 0 && (
                <div className="variant-bom">
                  <div className="variant-bom-title">
                    <Boxes size={17} />
                    <strong>Склад варіанта</strong>
                  </div>
                  <ol>
                    {item.components.map((component, index) => (
                      <li key={`${component.label}-${index}`}>
                        <span className="component-quantity">{component.quantity}×</span>
                        <div>
                          {component.kind && component.semantic_path ? (
                            <Link href={objectReferenceHref(component.kind, component.semantic_path)}>
                              {component.label}
                            </Link>
                          ) : (
                            <strong>{component.label}</strong>
                          )}
                          <small>{component.role}</small>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </section>
          )}
          {item.parameters && Object.keys(item.parameters).length > 0 && (
            <form className="parameter-form" onSubmit={applyParameters}>
              <div className="parameter-form-head">
                <strong>Розміри</strong>
                <span>Змініть параметри й натисніть «Показати»</span>
              </div>
              {item.parameter_presets && item.parameter_presets.length > 0 && (
                <label>
                  Типорозмір
                  <select
                    aria-label="Типорозмір"
                    value={presetId}
                    onChange={(event) => selectPreset(event.target.value)}
                  >
                    <option value="">Власні розміри</option>
                    {item.parameter_presets.map((preset) => (
                      <option key={preset.id} value={preset.id}>{preset.label}</option>
                    ))}
                  </select>
                </label>
              )}
              <div className="parameter-fields">
                {Object.entries(item.parameters)
                  .filter(([, declaration]) => !declaration.hidden)
                  .map(([name, declaration]) => (
                    <label key={name}>
                      {parameterLabels[name] || name.replaceAll("_", " ")}
                      <select
                        aria-label={parameterLabels[name] || name}
                        value={String(draftParameters[name] ?? declaration.default)}
                        onChange={(event) => {
                          setPresetId("");
                          setDraftParameters((current) => ({
                            ...current,
                            [name]: event.target.value,
                          }));
                        }}
                      >
                        {(declaration.options || [Number(declaration.default)]).map((option) => (
                          <option key={option} value={String(option)}>{option}</option>
                        ))}
                      </select>
                    </label>
                  ))}
              </div>
              <div className="parameter-actions">
                <button type="submit">Показати</button>
                <button type="button" onClick={resetParameters}>Скинути</button>
              </div>
            </form>
          )}
          <dl>
            <div>
              <dt>Model role</dt>
              <dd>{item.model_role === "electronic_component" ? "Electronic component · AI SCAD" : item.model_role === "printable_part" ? "Printable part · FreeCAD master" : "Legacy · migration pending"}</dd>
            </div>
            <div>
              <dt>Формат</dt>
              <dd>{item.source_type.toUpperCase()}</dd>
            </div>
            <div>
              <dt>PartCAD path</dt>
              <dd>{item.semantic_path}</dd>
            </div>
            <div>
              <dt>Пакет</dt>
              <dd>{item.package_path}</dd>
            </div>
            <div>
              <dt>Файл</dt>
              <dd>{item.source_path || "генерований"}</dd>
            </div>
            <div>
              <dt>Ліцензія</dt>
              <dd>{item.license || "не перевірена"}</dd>
            </div>
          </dl>
          {item.source_path && item.visibility === "private" ? (
            <button
              className="source-button"
              disabled={!principal}
              onClick={privateDownload}
            >
              <Lock size={17} /> Захищене завантаження
            </button>
          ) : (
            item.source_path && (
              <a
                className="source-button"
                href={gitUrl}
                target="_blank"
                rel="noreferrer"
              >
                <Download size={17} /> {item.entry_type === "project" ? "Відкрити файл у Git" : "Відкрити файл у PUB"}
              </a>
            )
          )}
          <Link
            className="package-source-link"
            href={`/repository/package/${item.package_id}`}
          >
            Пакет у NarysAI <ChevronRight size={16} />
          </Link>
        </article>
      </div>
    </main>
  );
}

function Loading() {
  return (
    <main className="center-state">
      <LoaderCircle className="spin" />
      <h2>Завантажуємо пакет…</h2>
    </main>
  );
}
function ErrorBox({ text }: { text: string }) {
  return (
    <div className="error-box">
      <strong>Не вдалося завантажити</strong>
      <span>{text}</span>
    </div>
  );
}
function Empty() {
  return (
    <div className="empty">
      <FileSearch />
      <h2>Нічого не знайдено</h2>
      <p>Спробуйте інший запит або оновіть індекс.</p>
    </div>
  );
}

function AdminPage() {
  const { principal } = useContext(AuthContext);
  const [keys, setKeys] = useState<Array<Record<string, unknown>>>([]);
  const [audit, setAudit] = useState<Array<Record<string, string | number>>>(
    [],
  );
  const [runs, setRuns] = useState<Array<Record<string, string | number>>>([]);
  const [created, setCreated] = useState("");
  const [name, setName] = useState("");
  const load = () =>
    Promise.all([getAdminKeys(), getAudit(), getAdminSyncRuns()]).then(
      ([keyData, auditData, syncData]) => {
        setKeys(keyData.keys);
        setAudit(auditData.entries);
        setRuns(syncData.runs);
      },
    );
  useEffect(() => {
    if (principal?.role === "admin") load();
  }, [principal]);
  if (principal?.role !== "admin")
    return (
      <main>
        <ErrorBox text="Потрібен API-ключ адміністратора" />
      </main>
    );
  const create = async (event: FormEvent) => {
    event.preventDefault();
    const result = await createAdminKey(name, "user");
    setCreated(result.key);
    setName("");
    await load();
  };
  return (
    <main>
      <div className="page-title">
        <div>
          <span className="eyebrow">Admin</span>
          <h1>Доступ і аудит</h1>
          <p>
            Ключ показується лише один раз. Скопіюйте його перед закриттям
            сторінки.
          </p>
        </div>
      </div>
      <form className="admin-create" onSubmit={create}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Назва користувача"
          required
        />
        <button>Створити User key</button>
      </form>
      {created && <code className="created-key">{created}</code>}
      <section className="section">
        <h2>API-ключі</h2>
        <div className="admin-list">
          {keys.map((item) => (
            <div className="admin-key" key={String(item.key_id)}>
              <code>
                {String(item.name)} · {String(item.role)} ·{" "}
                {String(item.key_id)}
              </code>
              {!item.revoked_at && String(item.key_id) !== principal.key_id && (
                <button
                  onClick={async () => {
                    await revokeAdminKey(String(item.key_id));
                    await load();
                  }}
                >
                  Відкликати
                </button>
              )}
            </div>
          ))}
        </div>
      </section>
      <section className="section">
        <h2>Синхронізація</h2>
        <div className="admin-list">
          {runs.map((item) => (
            <code key={String(item.id)}>
              #{String(item.id)} · {String(item.status)}
            </code>
          ))}
        </div>
      </section>
      <section className="section">
        <h2>Аудит</h2>
        <div className="admin-list">
          {audit.map((item, index) => (
            <code key={index}>
              {String(item.action)} · {String(item.resource || "")}
            </code>
          ))}
        </div>
      </section>
    </main>
  );
}

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState("");
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const load = async () => {
    try {
      setCatalog(await getCatalog());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const login = async (key: string) => {
    try {
      setPrincipal(await authenticate(key));
      setError("");
      setCatalog(await getCatalog());
    } catch (e) {
      setApiKey("");
      setError((e as Error).message);
      throw e;
    }
  };
  const logout = () => {
    setApiKey("");
    setPrincipal(null);
    load();
  };
  useEffect(() => {
    load();
  }, []);
  return (
    <AuthContext.Provider value={{ principal }}>
      <div className="app-shell">
        <Header
          onMenu={() => setMenu(true)}
          principal={principal}
          onLogin={login}
          onLogout={logout}
        />
        <Sidebar catalog={catalog} open={menu} close={() => setMenu(false)} />
        <div className="content">
          {error && <ErrorBox text={error} />}
          <Switch>
            <Route path="/repository/admin">
              <AdminPage />
            </Route>
            <Route path="/repository/package/:id">
              <PackagePage />
            </Route>
            <Route path="/repository/object/:id">
              <ObjectPage />
            </Route>
            <Route path="/repository/:kind/*">
              <SemanticObjectPage />
            </Route>
            <Route path="/repository">
              <Home catalog={catalog} reload={load} />
            </Route>
            <Route>
              <Home catalog={catalog} reload={load} />
            </Route>
          </Switch>
        </div>
      </div>
    </AuthContext.Provider>
  );
}
