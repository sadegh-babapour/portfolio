// import { useState } from 'react'
// import reactLogo from './assets/react.svg'
// import viteLogo from './assets/vite.svg'
// import heroImg from './assets/hero.png'
// import './App.css'

// function App() {
//   const [count, setCount] = useState(0)

//   return (
//     <>
//       <section id="center">
//         <div className="hero">
//           <img src={heroImg} className="base" width="170" height="179" alt="" />
//           <img src={reactLogo} className="framework" alt="React logo" />
//           <img src={viteLogo} className="vite" alt="Vite logo" />
//         </div>
//         <div>
//           <h1>Get started</h1>
//           <p>
//             Edit <code>src/App.jsx</code> and save to test <code>HMR</code>
//           </p>
//         </div>
//         <button
//           className="counter"
//           onClick={() => setCount((count) => count + 1)}
//         >
//           Count is {count}
//         </button>
//       </section>

//       <div className="ticks"></div>

//       <section id="next-steps">
//         <div id="docs">
//           <svg className="icon" role="presentation" aria-hidden="true">
//             <use href="/icons.svg#documentation-icon"></use>
//           </svg>
//           <h2>Documentation</h2>
//           <p>Your questions, answered</p>
//           <ul>
//             <li>
//               <a href="https://vite.dev/" target="_blank">
//                 <img className="logo" src={viteLogo} alt="" />
//                 Explore Vite
//               </a>
//             </li>
//             <li>
//               <a href="https://react.dev/" target="_blank">
//                 <img className="button-icon" src={reactLogo} alt="" />
//                 Learn more
//               </a>
//             </li>
//           </ul>
//         </div>
//         <div id="social">
//           <svg className="icon" role="presentation" aria-hidden="true">
//             <use href="/icons.svg#social-icon"></use>
//           </svg>
//           <h2>Connect with us</h2>
//           <p>Join the Vite community</p>
//           <ul>
//             <li>
//               <a href="https://github.com/vitejs/vite" target="_blank">
//                 <svg
//                   className="button-icon"
//                   role="presentation"
//                   aria-hidden="true"
//                 >
//                   <use href="/icons.svg#github-icon"></use>
//                 </svg>
//                 GitHub
//               </a>
//             </li>
//             <li>
//               <a href="https://chat.vite.dev/" target="_blank">
//                 <svg
//                   className="button-icon"
//                   role="presentation"
//                   aria-hidden="true"
//                 >
//                   <use href="/icons.svg#discord-icon"></use>
//                 </svg>
//                 Discord
//               </a>
//             </li>
//             <li>
//               <a href="https://x.com/vite_js" target="_blank">
//                 <svg
//                   className="button-icon"
//                   role="presentation"
//                   aria-hidden="true"
//                 >
//                   <use href="/icons.svg#x-icon"></use>
//                 </svg>
//                 X.com
//               </a>
//             </li>
//             <li>
//               <a href="https://bsky.app/profile/vite.dev" target="_blank">
//                 <svg
//                   className="button-icon"
//                   role="presentation"
//                   aria-hidden="true"
//                 >
//                   <use href="/icons.svg#bluesky-icon"></use>
//                 </svg>
//                 Bluesky
//               </a>
//             </li>
//           </ul>
//         </div>
//       </section>

//       <div className="ticks"></div>
//       <section id="spacer"></section>
//     </>
//   )
// }

// export default App
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { antPath } from "leaflet-ant-path";

const QUADRANT_COLOURS = {
  NE: "#4A90D9",
  NW: "#A78BFA",
  SE: "#34D399",
  SW: "#FB923C",
};
const STALE_COLOUR = "#F87171";
const DEFAULT_COLOUR = "#4A90D9";

const TILE_DARK =
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_LIGHT =
  "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTRIBUTION = "© OpenStreetMap contributors © CARTO";

function getColour(v) {
  if (v.is_stale) return STALE_COLOUR;
  return QUADRANT_COLOURS[v.quadrant] || DEFAULT_COLOUR;
}

// sample up to maxPerQuadrant vehicles per quadrant
function sampleVehicles(vehicles, maxPerQuadrant = 5) {
  const buckets = {};
  for (const v of vehicles) {
    const q = v.quadrant || "XX";
    if (!buckets[q]) buckets[q] = [];
    buckets[q].push(v);
  }
  const result = [];
  for (const group of Object.values(buckets)) {
    const shuffled = [...group].sort(() => Math.random() - 0.5);
    result.push(...shuffled.slice(0, maxPerQuadrant));
  }
  return result;
}

export default function App() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const tileLayerRef = useRef(null);
  const layersRef = useRef([]);
  const [darkMode, setDarkMode] = useState(true);
  const [vehicleCount, setVehicleCount] = useState("");
  const [countdown, setCountdown] = useState(30);
  const [quadrant, setQuadrant] = useState("All");
  const [route, setRoute] = useState("All routes");
  const [routes, setRoutes] = useState([]);
  const [lastSample, setLastSample] = useState([]);
  const countdownRef = useRef(30);

  // init map once
  useEffect(() => {
    if (mapInstanceRef.current) return;
    const map = L.map(mapRef.current).setView([51.0447, -114.0719], 11);
    tileLayerRef.current = L.tileLayer(TILE_DARK, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 19,
      subdomains: "abcd",
    }).addTo(map);
    mapInstanceRef.current = map;
  }, []);

  // tile toggle
  useEffect(() => {
    if (!mapInstanceRef.current) return;
    if (tileLayerRef.current) {
      mapInstanceRef.current.removeLayer(tileLayerRef.current);
    }
    tileLayerRef.current = L.tileLayer(darkMode ? TILE_DARK : TILE_LIGHT, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 19,
      subdomains: "abcd",
    }).addTo(mapInstanceRef.current);
  }, [darkMode]);

  function clearLayers() {
    for (const layer of layersRef.current) {
      mapInstanceRef.current.removeLayer(layer);
    }
    layersRef.current = [];
  }

  function drawVehicles(vehicles) {
    const map = mapInstanceRef.current;
    if (!map) return;
    clearLayers();

    for (const v of vehicles) {
      const colour = getColour(v);
      const speedKmh = v.speed ? (v.speed * 3.6).toFixed(1) : 0;
      const tooltip = `Route ${v.route_id || "?"} | Vehicle ${v.vehicle_id} | ${speedKmh} km/h | ${v.is_stale ? "⚠️ Stale" : "✅ Moving"}`;

      // ghost dot
      if (v.prev_lat && v.prev_lon) {
        const ghost = L.circleMarker([v.prev_lat, v.prev_lon], {
          radius: 5,
          color: colour,
          fillColor: colour,
          fillOpacity: 0.25,
          opacity: 0.25,
          weight: 1,
        }).addTo(map);
        layersRef.current.push(ghost);

        // ant path from prev to current (only if moving)
        if (!v.is_stale) {
          const trail = antPath(
            [
              [v.prev_lat, v.prev_lon],
              [v.lat, v.lon],
            ],
            {
              delay: 600,
              dashArray: [8, 20],
              weight: 3,
              color: colour,
              pulseColor: "#ffffff",
              opacity: 0.7,
              hardwareAccelerated: true,
            }
          ).addTo(map);
          layersRef.current.push(trail);
        }
      }

      // current dot
      const dot = L.circleMarker([v.lat, v.lon], {
        radius: 8,
        color: "white",
        fillColor: colour,
        fillOpacity: 0.95,
        opacity: 1,
        weight: 2,
      })
        .bindTooltip(tooltip, { sticky: true })
        .addTo(map);
      layersRef.current.push(dot);
    }
  }

  async function fetchAndDraw(resample = false) {
    try {
      const res = await fetch("/api/vehicles");
      const all = await res.json();

      // collect unique route ids for dropdown
      const uniqueRoutes = [...new Set(all.map((v) => v.route_id).filter(Boolean))].sort();
      setRoutes(uniqueRoutes);

      // filter
      let filtered = all;
      if (quadrant !== "All") filtered = filtered.filter((v) => v.quadrant === quadrant);
      if (route !== "All routes") filtered = filtered.filter((v) => v.route_id === route);

      // sample
      const sample = resample || lastSample.length === 0
        ? sampleVehicles(filtered)
        : filtered.filter((v) => lastSample.includes(v.vehicle_id));

      if (resample || lastSample.length === 0) {
        setLastSample(sample.map((v) => v.vehicle_id));
      }

      setVehicleCount(`${all.length} total · ${sample.length} shown`);
      drawVehicles(sample);

      // reset countdown
      countdownRef.current = 30;
      setCountdown(30);
    } catch (err) {
      console.error("Failed to fetch vehicles:", err);
    }
  }

  // initial fetch + 30s refresh
  useEffect(() => {
    fetchAndDraw(true);
    const interval = setInterval(() => fetchAndDraw(), 30000);
    return () => clearInterval(interval);
  }, [quadrant, route]);

  // countdown tick
  useEffect(() => {
    const tick = setInterval(() => {
      countdownRef.current = Math.max(0, countdownRef.current - 1);
      setCountdown(countdownRef.current);
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  return (
    <div style={{ fontFamily: "sans-serif", background: "#1a1a2e", minHeight: "100vh", color: "#eee" }}>
      {/* header */}
      <div style={{ padding: "12px 16px", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, borderBottom: "1px solid #333" }}>
        <span style={{ fontSize: 20, fontWeight: 600, flex: 1 }}>🚌 Calgary Transit — Live Map</span>
        <span style={{ fontSize: 13, color: "#aaa" }}>{vehicleCount}</span>
        <span style={{ fontSize: 13, color: "#aaa" }}>Next refresh: {countdown}s</span>
        <button onClick={() => setDarkMode((d) => !d)} style={btnStyle}>
          {darkMode ? "☀️ Light" : "🌙 Dark"}
        </button>
      </div>

      {/* controls */}
      <div style={{ padding: "8px 16px", display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", borderBottom: "1px solid #333" }}>
        <label style={{ fontSize: 13 }}>
          Quadrant&nbsp;
          <select value={quadrant} onChange={(e) => setQuadrant(e.target.value)} style={selectStyle}>
            {["All", "NE", "NW", "SE", "SW"].map((q) => <option key={q}>{q}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 13 }}>
          Route&nbsp;
          <select value={route} onChange={(e) => setRoute(e.target.value)} style={selectStyle}>
            <option>All routes</option>
            {routes.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <button onClick={() => fetchAndDraw(true)} style={btnStyle}>🔀 Resample</button>
      </div>

      {/* legend */}
      <div style={{ padding: "6px 16px", display: "flex", flexWrap: "wrap", gap: 16, fontSize: 12, borderBottom: "1px solid #333" }}>
        {Object.entries(QUADRANT_COLOURS).map(([q, c]) => (
          <span key={q} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: "50%", background: c, display: "inline-block" }} />
            {q}
          </span>
        ))}
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: STALE_COLOUR, display: "inline-block" }} />
          Stale
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#aaa", opacity: 0.4, display: "inline-block" }} />
          Ghost
        </span>
      </div>

      {/* map */}
      <div ref={mapRef} style={{ width: "100%", height: "calc(100vh - 130px)" }} />
    </div>
  );
}

const btnStyle = {
  background: "#333",
  color: "#eee",
  border: "1px solid #555",
  borderRadius: 6,
  padding: "4px 12px",
  cursor: "pointer",
  fontSize: 13,
};

const selectStyle = {
  background: "#333",
  color: "#eee",
  border: "1px solid #555",
  borderRadius: 4,
  padding: "2px 6px",
  fontSize: 13,
};