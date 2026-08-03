const NAV_LINKS = [
  ["Home", "/"],
  ["About", "/about"],
  ["Resume", "/resume"],
  ["Projects", "/projects"],
  ["Contact", "/contact"],
  ["Dashboard", "/dashboard"],
];

function NavLinks({ className }) {
  return (
    <nav className={className} aria-label="Portfolio navigation">
      {NAV_LINKS.map(([label, path]) => (
        <a key={path} href={path}>
          {label}
        </a>
      ))}
      <a href="/calgary-transit-live/" aria-current="page">
        Calgary Transit Live
      </a>
    </nav>
  );
}

export default function PortfolioNav() {
  return (
    <header className="portfolio-nav">
      <a className="portfolio-brand" href="/">
        My Portfolio
      </a>

      <NavLinks className="portfolio-nav-desktop" />

      <details className="portfolio-nav-mobile">
        <summary aria-label="Open portfolio navigation">Menu</summary>
        <NavLinks className="portfolio-nav-mobile-links" />
      </details>
    </header>
  );
}
