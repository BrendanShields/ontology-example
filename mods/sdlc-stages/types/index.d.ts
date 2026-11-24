// The part of `onto view --format json` this mod draws.
export type StageState = 'done' | 'current' | 'blocked' | 'todo'

export type Stage = {
  key: string
  label: string
  gate: string
  state: StageState
  detail: string
}

export type Task = {
  id: string
  title: string
  status: string
  stage: string
  blocked: boolean
  stages: Stage[]
}

export type View = {
  task_in_hand: string | null
  tasks: Task[]
  trace: {
    coverage: { requirements: number; with_test: number; verified: number }
    violations: { message: string; subject?: string }[]
  }
}

// What the last run of `onto view` came to.
export type Loaded =
  | { status: 'ok'; view: View }
  | { status: 'error'; message: string }
  | null

declare module 'claude-code' {
  interface PluginState {
    'sdlc-stages': { loaded: Shaped<Loaded>; selected: string | null }
  }
}
