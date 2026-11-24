import { expect, test } from 'claude-code/testing'

const PANE = {
  plugin: 'sdlc-stages',
  component: 'Pane',
  requestId: 'sdlc-stages',
  props: {
    title: 'SDLC stages',
    isFocused: false,
    bodyColumns: 48,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const stage = (key: string, state: string, detail = '') => ({
  key,
  label: key.charAt(0).toUpperCase() + key.slice(1),
  gate: `onto ${key}`,
  state,
  detail,
})

// What `onto view --format json` prints, cut to what the mod draws.
const VIEW = {
  task_in_hand: 'TASK-0004',
  tasks: [
    {
      id: 'TASK-0001',
      title: 'Guard the write path',
      status: 'done',
      stage: 'complete',
      blocked: false,
      stages: [stage('intake', 'done'), stage('verify', 'done')],
    },
    {
      id: 'TASK-0004',
      title: 'Keep Utterance text out of the logs',
      status: 'in_progress',
      stage: 'design',
      blocked: false,
      stages: [
        stage('intake', 'done'),
        stage('design', 'current', 'no Decision on these terms yet'),
        stage('verify', 'todo'),
      ],
    },
  ],
  trace: {
    coverage: { requirements: 8, with_test: 7, verified: 7 },
    violations: [],
  },
}

const RUN = {
  command: 'sdlc',
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 120 },
} as const

const ran = (stdout: string, exitCode = 0) => ({
  value: {
    exitCode,
    stdout,
    stderr: exitCode === 0 ? '' : stdout,
    isStdoutTruncated: false,
    isStderrTruncated: false,
  },
})

test('the pane shows the stage of the task in hand, on every surface', async ($, on) => {
  // Each hook here stands for the engine beneath the mod.
  on('command.register', () => ({ value: { command: 'sdlc' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/repo/apps/call-qa-agent' }))
  // onto.toml is found two folders up, at the monorepo root.
  on('fs.stat', (_, e) =>
    e.path === '/repo/onto.toml'
      ? { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
      : { deny: 'missing' },
  )
  const calls: (readonly string[])[] = []
  on('process.run', (_, e) => {
    calls.push(e.argv)

    return ran(JSON.stringify(VIEW))
  })

  await $.session.start({ cwd: '/repo/apps/call-qa-agent', surface: 'desktop', isInteractive: true })
  await $.command.run(RUN)

  expect(calls.at(-1)).toEqual(['/repo/bin/onto', 'view', '--format', 'json'])

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })

    expect((await ui.find({ type: 'Text', text: /TASK-0004 \[in_progress\]/ }))?.text).toContain('in hand')
    expect((await ui.find({ type: 'Text', text: /no Decision/ }))?.text).toContain('gate: onto design')
    expect(await ui.find({ type: 'Text', text: /▶ Design/ })).toBeDefined()
    await ui.unmount()
  }
})

test('a failing onto run is shown, not hidden', async ($, on) => {
  on('command.register', () => ({ value: { command: 'sdlc' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.cwd', () => ({ value: '/repo' }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }))
  on('process.run', () => ran('onto: ontology/schemas/workflow.schema.json is missing: run `onto gen`', 1))

  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })

  expect((await ui.find({ type: 'Text', text: /onto gen/ }))?.text).toContain('is missing')
  await ui.unmount()
})

test('outside the monorepo the pane says so', async ($, on) => {
  on('command.register', () => ({ value: { command: 'sdlc' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.cwd', () => ({ value: '/somewhere/else' }))
  on('fs.stat', () => ({ deny: 'missing' }))

  await $.command.run(RUN)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  expect((await ui.find({ type: 'Text', text: /onto\.toml/ }))?.text).toContain('monorepo')
  await ui.unmount()
})
