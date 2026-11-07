export const fmtMs = (ms: number | null | undefined): string => {
  if (ms === null || ms === undefined) return '-'
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms} ms`
}

export const fmtNum = (n: number | null | undefined): string =>
  n === null || n === undefined ? '-' : n.toLocaleString()

export const fmtTime = (iso: string): string => new Date(iso).toLocaleString()
