// One step of the playbook, as Claude's task tools hold it.
export type Step = {
  id: string
  subject: string
  status: 'pending' | 'in_progress' | 'completed'
}

// The part of `onto view --format json` this mod draws.
export type PlannedTask = {
  id: string
  title: string
  status: string
  stage: string
  blocked: boolean
  blocked_by: string[]
}

export type Plan = {
  order: string[]
  requirements_by_status: Record<string, string[]>
  decisions_in_force: { id: string; title: string }[]
  superseded_decisions: { id: string; title: string; superseded_by: string | null }[]
  open_change_requests: { id: string; status: string; term: string }[]
}

export type Loaded =
  | { status: 'ok'; tasks: PlannedTask[]; plan: Plan }
  | { status: 'error'; message: string }
  | null

declare module 'claude-code' {
  interface PluginState {
    'work-plan': { loaded: Shaped<Loaded>; steps: Shaped<Step[]> }
  }
}
