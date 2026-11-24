import { expect, test } from 'claude-code/testing'

const PANE = {
  plugin: 'ontology-map',
  component: 'Pane',
  requestId: 'ontology-map',
  props: {
    title: 'Ontology',
    isFocused: false,
    bodyColumns: 48,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const RUN = {
  command: 'ontology',
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 120 },
} as const

const cls = (name: string, extra: object = {}) => ({
  name,
  definition: `What a ${name} is.`,
  classification: 'internal',
  abstract: false,
  parent: null,
  attributes: [],
  aliases: [],
  denied_synonyms: [],
  ...extra,
})

// What `onto view --format json` prints, cut to what the mod draws.
const VIEW = {
  ontology: {
    workflow: [
      {
        name: 'Task',
        abstract: false,
        parent: 'WorkItem',
        definition: 'A unit of work.',
        links: [{ slot: 'implements', to: 'Requirement', many: true }],
      },
    ],
    contexts: [
      {
        name: 'call-qa',
        title: 'Call quality assurance glossary (L2)',
        source: 'ontology/domains/call-qa.yaml',
        governs: ['apps/call-qa-agent/**'],
        terms: 57,
        classes: [
          cls('Call', { classification: 'PII' }),
          cls('Scorecard', {
            denied_synonyms: ['Rubric', 'EvaluationForm'],
            attributes: [
              { name: 'pass_mark', range: 'integer', required: true, many: false, constraints: ['>= 0', '<= 100'] },
            ],
          }),
        ],
        enums: [
          {
            name: 'Disposition',
            definition: 'What happens to an Evaluation.',
            values: [
              { name: 'FINAL', definition: 'Stands.' },
              { name: 'NEEDS_REVIEW', definition: 'A person reviews it.' },
            ],
          },
        ],
        denied: [{ synonym: 'Rubric', use: 'Scorecard' }],
      },
    ],
  },
}

test('the pane lists the classes and opens one on a press, on every surface', async ($, on) => {
  on('command.register', () => ({ value: { command: 'ontology' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.cwd', () => ({ value: '/repo' }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }))
  on('process.run', () => ({
    value: {
      exitCode: 0,
      stdout: JSON.stringify(VIEW),
      stderr: '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))

  await $.command.run(RUN)

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })

    // The classification of a sensitive class is on its row.
    expect(await ui.find({ type: 'Button', key: 'class-call-qa-Call' })).toBeDefined()
    expect((await ui.find({ type: 'Text', text: /57 terms/ }))?.text).toContain('call-qa')
    expect((await ui.find({ type: 'Text', text: /Task —implements→ Requirement/ }))?.text).toContain('*')
    expect((await ui.find({ type: 'Text', text: /Disposition:/ }))?.text).toContain('FINAL | NEEDS_REVIEW')

    await ui.press({ key: 'class-call-qa-Scorecard' })

    expect((await ui.find({ type: 'Text', text: /Never write/ }))?.text).toContain('Rubric, EvaluationForm')
    expect((await ui.find({ type: 'Text', text: /pass_mark/ }))?.text).toContain('integer, required, >= 0, <= 100')
    await ui.unmount()
  }
})
