// The part of `onto view --format json` this mod draws.
export type Attribute = {
  name: string
  range: string
  required: boolean
  many: boolean
  constraints: string[]
}

export type ClassTerm = {
  name: string
  definition: string
  classification: string
  abstract: boolean
  parent: string | null
  attributes: Attribute[]
  aliases: string[]
  denied_synonyms: string[]
}

export type EnumTerm = {
  name: string
  definition: string
  values: { name: string; definition: string }[]
}

export type Context = {
  name: string
  title: string
  source: string
  governs: string[]
  classes: ClassTerm[]
  enums: EnumTerm[]
  denied: { synonym: string; use: string }[]
  terms: number
}

export type WorkflowClass = {
  name: string
  abstract: boolean
  parent: string | null
  definition: string
  links: { slot: string; to: string; many: boolean }[]
}

export type Ontology = { workflow: WorkflowClass[]; contexts: Context[] }

export type Loaded =
  | { status: 'ok'; ontology: Ontology }
  | { status: 'error'; message: string }
  | null

declare module 'claude-code' {
  interface PluginState {
    // `selected` is "<context>/<Class>", or null for the first class.
    'ontology-map': { loaded: Shaped<Loaded>; selected: string | null }
  }
}
