// Shared application shell for ContextForge.  One layout, one chrome — the
// workspace, source exploration, chat and Repository Intelligence all render
// inside the same three-column frame so nothing reads as a separate product.
export default function AppShell({
  sidebar,
  main,
  right,
  layoutClass = '',
  mainClass = '',
  rightClass = '',
}) {
  return (
    <main className="app-shell">
      <div className={`app-layout ${layoutClass}`}>
        {sidebar}
        <section className={`main-shell ${mainClass}`}>{main}</section>
        <aside className={`shell-right ${rightClass}`}>{right}</aside>
      </div>
    </main>
  )
}
