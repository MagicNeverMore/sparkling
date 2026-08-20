export interface LogFileInfo {
  name: string
  size_bytes: number
  modified_at: string
}

export interface LogEntry {
  line_number: number
  text: string
}

export interface LogPage {
  file: string | null
  files: LogFileInfo[]
  total_matches: number
  next_before: number | null
  items: LogEntry[]
}
