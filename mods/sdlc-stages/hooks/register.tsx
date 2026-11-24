import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Loaded, Stage, Task, View } from '../types'
import { runView } from './onto'

// Which SDLC stage each task is at, read from the repository by `onto view`.
// The mod works nothing out: every judgement about a stage is made, and
// tested, in packages/onto. It only draws what that command reports.

const PANE = 'sdlc-stages'
const TITLE = 'SDLC stages'

// Change the tag when the drawn part of `onto view` changes shape: a value an
// earlier version stored outlives a reload and is then read as "not loaded".
const loaded = atom({ plugin: 'sdlc-stages', key: 'loaded' } as const, null, {
  shape: 'view-1',
})
const selected = atom({ plugin: 'sdlc-stages', key: 'selected' } as const, null)

const MARK = { done: '✓', current: '▶', blocked: '!', todo: '·' } as const
const COLOR = {
  done: 'success',
  current: 'suggestion',
  blocked: 'error',
  todo: 'inactive',
} as const

async function refresh($: EngineInterface): Promise<void> {
  const ran = await runView($)
  const next: Loaded =
    ran.status === 'ok' ? { status: 'ok', view: ran.view as View } : ran
  await update($, loaded, () => next)
}

function pick(view: View, wanted: string | null): Task | undefined {
  return (
    view.tasks.find(task => task.id === wanted) ??
    view.tasks.find(task => task.id === view.task_in_hand) ??
    view.tasks.find(task => task.stage !== 'complete') ??
    view.tasks[0]
  )
}

function at(task: Task): Stage | undefined {
  return task.stages.find(
    stage => stage.state === 'current' || stage.state === 'blocked',
  )
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'sdlc',
      description: 'Show which SDLC stage each task is at',
    })
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'sdlc' }, async $ => {
    await refresh($)
    await $.ui.open({ id: PANE, title: TITLE })

    return { text: 'SDLC stages pane opened.' }
  })

  // The repository changes during a turn: read it again when the turn ends.
  on('turn.complete', async ($, e, next) => {
    void refresh($)

    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const state = await read($, loaded)

    if (e.props.hasSurvey || state === null || state.status !== 'ok') {
      return next(e)
    }
    const task = state.view.tasks.find(
      one => one.id === state.view.task_in_hand,
    )
    const stage = task === undefined ? undefined : at(task)

    if (task === undefined || stage === undefined) {
      return next(e)
    }
    const { Box, Text } = $.ui.resolve(e)
    const { verified, requirements } = state.view.trace.coverage

    return (
      <Box>
        <Text color={COLOR[stage.state]}>
          {MARK[stage.state]} {task.id} at {stage.label.toLowerCase()}
        </Text>
        <Text dimColor>
          {' '}
          · gate: {stage.gate} · {verified}/{requirements} verified
        </Text>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Progress, Text } = $.ui.resolve(e)
    const state = await read($, loaded)

    if (state === null) {
      return <Text dimColor>Reading the repository…</Text>
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

    const { view } = state
    const task = pick(view, await read($, selected))
    const { verified, requirements } = view.trace.coverage
    const errors = view.trace.violations.length

    return (
      <Box flexDirection="column" gap={1}>
        {task === undefined ? (
          <Text dimColor>No Task under work/ yet.</Text>
        ) : (
          <Box flexDirection="column">
            <Text bold>
              {task.id} [{task.status}]
              {task.id === view.task_in_hand ? ' · in hand' : ''}
            </Text>
            <Text wrap="truncate-end">{task.title}</Text>
            {task.stages.map(stage => (
              <Box flexDirection="column">
                <Text color={COLOR[stage.state]}>
                  {MARK[stage.state]} {stage.label}
                </Text>
                {(stage.state === 'current' || stage.state === 'blocked') && (
                  <Text dimColor>
                    {'  '}
                    {stage.detail} (gate: {stage.gate})
                  </Text>
                )}
              </Box>
            ))}
          </Box>
        )}

        <Box flexDirection="column">
          <Text dimColor>All tasks</Text>
          {view.tasks.map(one => (
            <Button
              key={`task-${one.id}`}
              plain
              label={`${one.stages.map(s => MARK[s.state]).join('')} ${one.id} ${
                one.stage === 'complete' ? 'shipped' : `at ${one.stage}`
              }`}
              onPress={() => update($, selected, () => one.id)}
            />
          ))}
        </Box>

        <Progress
          label="Requirements verified"
          value={verified}
          max={Math.max(1, requirements)}
          valueText={`${verified} of ${requirements}`}
          color={errors > 0 ? 'error' : 'success'}
        />
        {errors > 0 && (
          <Text color="error">
            {errors} gate error(s): {view.trace.violations[0]?.message}
          </Text>
        )}
        <Button key="refresh" label="Refresh" onPress={() => refresh($)} />
      </Box>
    )
  })
}
