const NAMED_ENTITIES = Object.freeze({
  amp: "&",
  apos: "'",
  gt: ">",
  lt: "<",
  nbsp: " ",
  quot: '"',
});

function decodeEntity(match, entity) {
  const normalized = entity.toLowerCase();
  if (Object.hasOwn(NAMED_ENTITIES, normalized)) {
    return NAMED_ENTITIES[normalized];
  }
  if (normalized.startsWith("#x")) {
    const codePoint = Number.parseInt(normalized.slice(2), 16);
    return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : match;
  }
  if (normalized.startsWith("#")) {
    const codePoint = Number.parseInt(normalized.slice(1), 10);
    return Number.isFinite(codePoint) ? String.fromCodePoint(codePoint) : match;
  }
  return match;
}

export function alertText(value) {
  if (typeof value !== "string") return "";
  return value
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p\s*>/gi, "\n")
    .replace(/<[^>]*>/g, " ")
    .replace(/&([a-z]+|#\d+|#x[\da-f]+);/gi, decodeEntity)
    .replace(/[ \t]+/g, " ")
    .replace(/\s*\n\s*/g, "\n")
    .trim();
}
