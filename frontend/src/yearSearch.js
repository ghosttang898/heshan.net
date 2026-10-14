function normalize(value) {
  return String(value ?? "").normalize("NFKC").trim().toLowerCase();
}

export function parseYearRange(value) {
  const match = normalize(value).match(/^(\d{4})\s*年?(?:\s*[-\u2013\u2014~\u81f3\u5230/]\s*(\d{4})\s*年?)?$/);
  if (!match) return null;
  const first = Number(match[1]);
  const last = Number(match[2] ?? match[1]);
  if (first === 0 || last === 0) return null;
  return { start: Math.min(first, last), end: Math.max(first, last) };
}

export function matchesYearSearch(record, query) {
  const text = normalize(record);
  const search = normalize(query);
  if (!search) return true;
  const recordedYears = parseYearRange(text);
  const searchedYears = parseYearRange(search);
  if (recordedYears && searchedYears) {
    return recordedYears.start <= searchedYears.end && searchedYears.start <= recordedYears.end;
  }
  // Preserve literal searches for existing free-text year descriptions.
  return text.includes(search);
}
