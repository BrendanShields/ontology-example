import { expect, test } from 'claude-code/testing'
import type { TestBody } from 'claude-code/testing'

const PANE = {
  plugin: 'work-plan',
  component: 'Pane',
  requestId: 'work-plan',
  props: {
    title: 'Plan',
    isFocused: false,
    bodyColumns: 48,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const RUN = {
  command: 'work-plan',
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 120 },
} as const

// What `onto view --format json` prints, cut to what the mod draws.
const VIEW = {
  tasks: [
    { id: 'TASK-0003', title: 'Bound the turns', status: 'done', stage: 'complete', blocked: false, blocked_by: ['TASK-0001'] },
    { id: 'TASK-0004', title: 'Keep Utterance text out of the logs', status: 'in_progress', stage: 'design', blocked: false, blocked_by: [] },
  ],
  plan: {
    order: ['TASK-0004'],
    requirements_by_status: { draft: ['REQ-0009'], ready: [], in_progress: ['REQ-0008'], done: ['REQ-0001', 'REQ-0002'], superseded: [] },
    decisions_in_force: [{ id: 'DEC-0002', title: 'Call it a Scorecard' }],
    superseded_decisions: [{ id: 'DEC-0001', title: 'Call it a rubric', superseded_by: 'DEC-0002' }],
    open_change_requests: [{ id: 'OCR-0002', status: 'draft', term: 'Calibration' }],
  },
}

// The engine beneath the mod: what each call on `$` is answered with.
function engine(on: Parameters<TestBody>[1]) {
  on('command.register', () => ({ value: { command: 'work-plan' } }))
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
}

test('the pane shows the typed plan, on every surface', async ($, on) => {
  engine(on)
  await $.command.run(RUN)

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })

    expect((await ui.find({ type: 'Text', text: /TASK-0004 at design/ }))?.text).toContain('Keep Utterance text')
    expect((await ui.find({ type: 'Text', text: /in_progress: 1/ }))?.text).toContain('REQ-0008')
    expect((await ui.find({ type: 'Text', text: /DEC-0001 superseded/ }))?.text).toContain('DEC-0002')
    expect((await ui.find({ type: 'Text', text: /OCR-0002/ }))?.text).toContain('Calibration')
    expect(await ui.find({ type: 'Text', text: /None yet/ })).toBeDefined()
    await ui.unmount()
  }
})

test('the playbook steps follow the task tools, skipped steps included', async ($, on) => {
  engine(on)
  // The engine beneath answers each task tool as Claude Code does.
  let created = 0
  on('tool.call', { tool: 'TaskCreate' }, (_, e) => {
    created += 1

    return { result: { task: { id: String(created), subject: e.subject } } }
  })
  on('tool.call', { tool: 'TaskUpdate' }, (_, e) => ({
    result: { success: true, taskId: e.taskId, updatedFields: ['status'] },
  }))

  await $.tool.call({ tool: 'TaskCreate', subject: '1. Intake', description: 'Find or create the Task' })
  await $.tool.call({ tool: 'TaskCreate', subject: '2. Close the vocabulary gap', description: 'term-gap' })
  await $.tool.call({ tool: 'TaskCreate', subject: '3. architect for the shape', description: 'architect' })
  await $.tool.call({ tool: 'TaskUpdate', taskId: '1', status: 'completed' })
  await $.tool.call({ tool: 'TaskUpdate', taskId: '2', status: 'in_progress' })
  await $.tool.call({ tool: 'TaskUpdate', taskId: '3', subject: '3. architect for the shape. skip: one-line change', status: 'completed' })

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  expect((await ui.find({ type: 'Text', text: /Intake/ }))?.text).toBe('[x] 1. Intake')
  expect((await ui.find({ type: 'Text', text: /vocabulary gap/ }))?.text).toBe('[>] 2. Close the vocabulary gap')
  expect((await ui.find({ type: 'Text', text: /skip:/ }))?.text).toContain('skip: one-line change')
  await ui.unmount()
})

test('a task tool call that was refused changes nothing', async ($, on) => {
  engine(on)
  on('tool.call', { tool: 'TaskCreate' }, () => ({ deny: 'not now' }))

  await $.tool.call({ tool: 'TaskCreate', subject: 'Never created', description: 'x' })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })

  expect(await ui.find({ type: 'Text', text: /Never created/ })).toBeUndefined()
  await ui.unmount()
})
