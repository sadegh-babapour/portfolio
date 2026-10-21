// Bus markers glide between their once-a-second positions with a CSS transition
// (App.css). When the zoom changes or the view resets, Leaflet repositions every
// marker; a glide then would slide buses across the screen. This marks the map
// container while that happens so the CSS can turn the glide off.
export function createGlideGuard(container, {
  className = "map-zooming",
  requestFrame = (callback) => globalThis.requestAnimationFrame(callback),
  cancelFrame = (id) => globalThis.cancelAnimationFrame(id),
} = {}) {
  let pendingFrame = null;
  const cancelPending = () => {
    if (pendingFrame !== null) cancelFrame(pendingFrame);
    pendingFrame = null;
  };

  return {
    start() {
      cancelPending();
      container.classList.add(className);
    },

    // Wait two frames so Leaflet's final reposition paints before the glide returns.
    end() {
      cancelPending();
      pendingFrame = requestFrame(() => {
        pendingFrame = requestFrame(() => {
          pendingFrame = null;
          container.classList.remove(className);
        });
      });
    },

    dispose() {
      cancelPending();
      container.classList.remove(className);
    },
  };
}
