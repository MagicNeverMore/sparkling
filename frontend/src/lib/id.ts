export function createClientId(prefix: string): string {
  const randomUuid = globalThis.crypto?.randomUUID?.()
  if (randomUuid) return `${prefix}-${randomUuid}`

  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}
