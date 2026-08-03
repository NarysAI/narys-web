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
        <span>Каталог пакетів</span>
        <button className="icon-button sidebar-close" onClick={close}>
          <X />
        </button>
      </div>
      <nav>
        <Link href="/repository" onClick={close}>
          <Database size={17} /> Усі пакети{" "}
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
              <ChevronRight size={15} /> {category.name}
              <span>{category.packages.length}</span>
            </summary>
            {category.packages.map((pkg) => (
              <Link
                className="package-link"
                key={pkg.id}
                href={`/repository/package/${pkg.id}`}
                onClick={close}
              >
                {pkg.name}
              </Link>
            ))}
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

function ObjectCard({ item }: { item: CatalogObject }) {
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
          {item.visibility === "private" && <Lock size={15} />} {item.name}
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
        .filter((item) => item.visibility === scope) ?? [],
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
            Креслення, готові
            <br />
            до роботи з <em>ШІ.</em>
          </h1>
          <p>
            NarysAI об’єднує відкриті PartCAD-пакети та ваші власні моделі в
            одному локальному, версійованому каталозі.
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
          <span>доступних пакетів</span>
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
      <section id="narys" className="section">
        <div className="section-head">
          <div>
            <span className="eyebrow">NarysAI {scope}</span>
            <h2>
              {scope === "public" ? "Публічні пакети" : "Приватні пакети"}
            </h2>
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
  return (
    <Link className="package-card" href={`/repository/package/${pkg.id}`}>
      <div>
        <Box />
        <span>{pkg.status}</span>
      </div>
      <small>{pkg.path}</small>
      <h3>{pkg.name}</h3>
      <p>{pkg.description}</p>
      <footer>
        Відкрити пакет <ChevronRight size={17} />
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
  return (
    <main>
      <div className="breadcrumbs">
        <Link href="/repository">Repository</Link>
        <ChevronRight size={15} />
        <span>{data.name}</span>
      </div>
      <div className="page-title">
        <div>
          <span className="eyebrow">PartCAD package</span>
          <h1>{data.name}</h1>
          <p>{data.description}</p>
        </div>
        <div className="page-actions">
          {data.visibility === "public" && (
            <a
              href={`https://github.com/NarysAI/PUB/tree/${data.git_commit || "main"}/${data.path.replace("//pub/", "")}`}
              target="_blank"
              rel="noreferrer"
            >
              <Download size={16} /> Відкрити пакет у PUB
            </a>
          )}
          <a
            className="upstream-link"
            href={data.upstream_url || data.source_url}
            target="_blank"
            rel="noreferrer"
          >
            Upstream <ExternalLink size={16} />
          </a>
        </div>
      </div>
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
  const [location] = useLocation();
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
  if (error)
    return (
      <main>
        <ErrorBox text={error} />
      </main>
    );
  if (!item) return <Loading />;
  return <ObjectDetail item={item} />;
}

function ObjectDetail({ item }: { item: CatalogObject }) {
  const { principal } = useContext(AuthContext);
  const privateDownload = async () => {
    const data = await createDownloadTicket(item.id);
    window.location.assign(`${API}/api/v1/downloads/${data.ticket}`);
  };
  const gitUrl = `https://github.com/NarysAI/PUB/blob/${item.git_commit || "main"}/${item.git_path || ""}`;
  return (
    <main>
      <div className="breadcrumbs">
        <Link href="/repository">Repository</Link>
        <ChevronRight size={15} />
        <Link href={`/repository/package/${item.package_id}`}>
          {item.package_path}
        </Link>
        <ChevronRight size={15} />
        <span>{item.name}</span>
      </div>
      <div className="detail-layout">
        <Viewer id={item.id} privateObject={item.visibility === "private"} />
        <article className="detail-panel">
          <span className="type-pill">
            {item.visibility === "private" ? "private" : item.kind}
          </span>
          <h1>{item.name}</h1>
          <p>{item.description}</p>
          <dl>
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
                <Download size={17} /> Відкрити файл у PUB
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
