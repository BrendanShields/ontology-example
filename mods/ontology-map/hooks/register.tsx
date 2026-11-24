import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Attribute, ClassTerm, Context, Loaded, Ontology } from '../types'
import { runView } from './onto'

// The ontology as a pane: what each bounded context calls things, what it
// refuses to call them, and how the workflow classes link. It draws what
// `onto view` reports and holds no copy of the ontology itself.

const PANE = 'ontology-map'
const TITLE = 'Ontology'

const loaded = atom({ plugin: 'ontology-map', key: 'loaded' } as const, null, {
  shape: 'ontology-1',
})
const selected = atom(
  { plugin: 'ontology-map', key: 'selected' } as const,
  null,
)

async function refresh($: EngineInterface): Promise<void> {
  const ran = await runView($)
  const next: Loaded =
    ran.status === 'ok'
      ? {
          status: 'ok',
          ontology: (ran.view as { ontology: Ontology }).ontology,
        }
      : ran
  await update($, loaded, () => next)
}

function attributeLine(attribute: Attribute): string {
  const parts = [
    attribute.range + (attribute.many ? ' list' : ''),
    attribute.required ? 'required' : 'optional',
    ...attribute.constraints,
  ]

  return `${attribute.name}: ${parts.join(', ')}`
}

function find(
  ontology: Ontology,
  wanted: string | null,
): { context: Context; term: ClassTerm } | undefined {
  for (const context of ontology.contexts) {
    for (const term of context.classes) {
      if (wanted === null || wanted === `${context.name}/${term.name}`) {
        return { context, term }
      }
    }
  }

  return undefined
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'ontology',
      description: 'Browse the ontology: terms, definitions, denied synonyms',
    })
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'ontology' }, async $ => {
    await refresh($)
    await $.ui.open({ id: PANE, title: TITLE })

    return { text: 'Ontology pane opened.' }
  })

  // An ontology change request may have landed during the turn.
  on('turn.complete', async ($, e, next) => {
    void refresh($)

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const state = await read($, loaded)

    if (state === null) {
      return <Text dimColor>Reading the ontology…</Text>
    }
    if (state.status === 'error') {
      return (
        <Box flexDirection="column" gap={1}>
          <Text color="error">onto view failed</Text>
          <Text>{state.message}</Text>
          <Button key="retry" label="Try again" onPress={() => refresh($)} />
        </Box>
      )
    }

    const { ontology } = state
    const wanted = await read($, selected)
    const shown = find(ontology, wanted) ?? find(ontology, null)

    return (
      <Box flexDirection="column" gap={1}>
        {ontology.contexts.map(context => (
          <Box flexDirection="column">
            <Text bold>
              {context.name} · {context.terms} terms
            </Text>
            <Text dimColor wrap="truncate-end">
              {context.source} governs {context.governs.join(', ') || 'nothing'}
            </Text>
            {context.classes.map(term => (
              <Button
                key={`class-${context.name}-${term.name}`}
                plain
                label={
                  (shown?.term === term ? '▶ ' : '  ') +
                  term.name +
                  (term.classification === 'internal'
                    ? ''
                    : ` (${term.classification})`)
                }
                onPress={() =>
                  update($, selected, () => `${context.name}/${term.name}`)
                }
              />
            ))}
          </Box>
        ))}

        {shown !== undefined && (
          <Box flexDirection="column">
            <Text bold color="suggestion">
              {shown.term.name}
            </Text>
            <Text>{shown.term.definition}</Text>
            {shown.term.attributes.map(attribute => (
              <Text dimColor>- {attributeLine(attribute)}</Text>
            ))}
            {shown.term.aliases.length > 0 && (
              <Text dimColor>Also resolves: {shown.term.aliases.join(', ')}</Text>
            )}
            {shown.term.denied_synonyms.length > 0 && (
              <Text color="warning">
                Never write: {shown.term.denied_synonyms.join(', ')}
              </Text>
            )}
          </Box>
        )}

        {ontology.contexts.map(context => (
          <Box flexDirection="column">
            <Text dimColor>Enums of {context.name}</Text>
            {context.enums.map(one => (
              <Text wrap="truncate-end">
                {one.name}: {one.values.map(value => value.name).join(' | ')}
              </Text>
            ))}
          </Box>
        ))}

        <Box flexDirection="column">
          <Text dimColor>Workflow links (shared by every context)</Text>
          {ontology.workflow.flatMap(cls =>
            cls.links.map(link => (
              <Text>
                {cls.name} —{link.slot}→ {link.to}
                {link.many ? ' *' : ''}
              </Text>
            )),
          )}
        </Box>
        <Button key="refresh" label="Refresh" onPress={() => refresh($)} />
      </Box>
    )
  })
}
