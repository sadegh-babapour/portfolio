import { useEffect, useState } from "react";

const THEME_STORAGE_KEY = "portfolio-theme";

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
  const [theme, setTheme] = useState(() => {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const dark = theme === "dark";

  return (
    <header className="portfolio-nav">
      <a className="portfolio-brand" href="/">
        My Portfolio
      </a>

      <NavLinks className="portfolio-nav-desktop" />

      <div className="portfolio-nav-actions">
        <button
          className="portfolio-theme-toggle"
          type="button"
          aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          title="Switch theme"
          onClick={() => setTheme(dark ? "light" : "dark")}
        >
          <span aria-hidden="true">{dark ? "☀️" : "🌙"}</span>
        </button>

        <details className="portfolio-nav-mobile">
          <summary aria-label="Open portfolio navigation">Menu</summary>
          <NavLinks className="portfolio-nav-mobile-links" />
        </details>
      </div>
    </header>
  );
}
