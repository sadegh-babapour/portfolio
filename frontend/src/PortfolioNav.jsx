import { useEffect, useState } from "react";
import {
  formatMountainClock,
  nextThemeMode,
  resolveTheme,
  RESOLVED_THEME_STORAGE_KEY,
  THEME_MODE_STORAGE_KEY,
} from "./mountainTime.js";

const NAV_LINKS = [
  ["Home", "/"],
  ["About", "/about"],
  ["Resume", "/resume"],
  ["Projects", "/projects"],
  ["Contact", "/contact"],
  ["Dashboard", "/dashboard"],
];
const ACCOUNT_LINK = ["Account", "/account"];
const TRANSIT_LINK = ["Calgary Transit Live", "/calgary-transit-live/"];

function NavLinks({ className, mobile = false }) {
  const links = mobile
    ? [ACCOUNT_LINK, ...NAV_LINKS, TRANSIT_LINK]
    : [...NAV_LINKS, TRANSIT_LINK, ACCOUNT_LINK];

  return (
    <nav className={className} aria-label="Portfolio navigation">
      {links.map(([label, path]) => (
        <a
          key={path}
          href={path}
          className={path === "/account" ? "portfolio-account-link" : undefined}
          aria-current={path === "/calgary-transit-live/" ? "page" : undefined}
        >
          {label}
        </a>
      ))}
    </nav>
  );
}

export default function PortfolioNav() {
  const [mode, setMode] = useState(() => {
    const storedMode = window.localStorage.getItem(THEME_MODE_STORAGE_KEY);
    return ["auto", "light", "dark"].includes(storedMode) ? storedMode : "auto";
  });
  const [now, setNow] = useState(() => new Date());
  const theme = resolveTheme(mode, now);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem(RESOLVED_THEME_STORAGE_KEY, theme);
    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, mode);
  }, [mode, theme]);

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(interval);
  }, []);

  const dark = theme === "dark";
  const nextMode = nextThemeMode(mode);
  const modeLabel = mode === "auto" ? "Auto" : mode === "light" ? "Light" : "Dark";

  return (
    <header className="portfolio-nav">
      <a className="portfolio-brand" href="/" aria-label="Bizqlab home">
        <img src="/static/bizqlab_logo.png" alt="Bizqlab logo" />
        <span>Bizqlab</span>
      </a>

      <NavLinks className="portfolio-nav-desktop" />

      <div className="portfolio-nav-actions">
        <time className="portfolio-mountain-clock" dateTime={now.toISOString()}>
          <span>Calgary</span>
          <strong>{formatMountainClock(now)}</strong>
        </time>
        <button
          className="portfolio-theme-toggle"
          type="button"
          aria-label={`Theme: ${modeLabel}. Switch to ${nextMode}.`}
          title={`Theme: ${modeLabel}. Next: ${nextMode}.`}
          onClick={() => setMode(nextMode)}
        >
          <span aria-hidden="true">{mode === "auto" ? "◐" : dark ? "☀️" : "🌙"}</span>
        </button>

        <details className="portfolio-nav-mobile">
          <summary aria-label="Open portfolio navigation">Menu</summary>
          <NavLinks className="portfolio-nav-mobile-links" mobile />
        </details>
      </div>
    </header>
  );
}
