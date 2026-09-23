export function forecastThreshold(
  years: number[],
  values: Record<string, number | null>,
  historicalCutoff: number,
  threshold: number,
): { status: 'breach' | 'safe' | 'unknown'; year: number | null } {
  const predictedYears = [...new Set(years)].filter(year => year > historicalCutoff).sort((a, b) => a - b)
  let lastYear: number | null = null
  for (const year of predictedYears) {
    const value = values[String(year)]
    if (year !== (lastYear ?? historicalCutoff) + 1 || value == null || !Number.isFinite(value)) {
      return { status: 'unknown', year: lastYear }
    }
    if (value < threshold) return { status: 'breach', year }
    lastYear = year
  }
  return { status: lastYear === null ? 'unknown' : 'safe', year: lastYear }
}
