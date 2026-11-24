import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Loaded, Plan, PlannedTask, Step } from '../types'
import { runView } from './onto'

// The plan, from two places that are kept apart on purpose.
//
// The playbook steps come from Claude's own task list: the ostack-mode skill
// copies a playbook into it step by step, and a skipped step stays listed with
// its reason. This mod mirrors that list by watching the task tools.
//
// Everything else comes from the repository through `onto view`: what is typed
// under work/ is the plan of record, and it outlives the session.

const PANE = 'work-plan'
const TITLE = 'Plan'

const loaded = atom({ plugin: 'work-plan', key: 'loaded' } as const, null, {
  shape: 'plan-1',
})
const steps = atom({ plugin: 'work-plan', key: 'steps' } as const, [], {
  shape: 'steps-1',
})

const STEP_MARK = { completed: '[x]', in_progress: '[>]', pending: '[ ]' } as const

async function refresh($: EngineInterface): Promise<void> {
  const ran = await runView($)
  let next: Loaded = null

  if (ran.status === 'ok') {
    const view = ran.view as { tasks: PlannedTask[]; plan: Plan }
    next = { status: 'ok', tasks: view.tasks, plan: view.plan }
  } else {
    next = ran
  }
  await update($, loaded, () => next)
}

export const register: Register = on => {

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'work-plan',
      description: 'Show the playbook steps and the typed plan under work/',
    })
    void refresh($)

    return next(e)
  })

  on('command.run', { command: 'work-plan' }, async $ => {
    await refresh($)
    await $.ui.open({ id: PANE, title: TITLE })

    return { text: 'Plan pane opened.' }
  })

  on('turn.complete', async ($, e, next) => {
    void refresh($)

    return next(e)
  })

  // Mirror the task list. Each hook lets the call run first and records only
  // what the tool reported, so a refused or failed call changes nothing here.
  // These hooks only watch: if mirroring fails, the `.catch` hands the call on,
  // and `next(e)` there replays what the call settled to without running it twice.
  on('tool.call', { tool: 'TaskCreate' }, async ($, e, next) => {
    const ran = await next(e)

    if (ran.deny === undefined && ran.isError !== true) {
      const { id, subject } = ran.result.task
      await update($, steps, list => [
        ...list.filter(step => step.id !== id),
        { id, subject, status: 'pending' as const },
      ])
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'TaskUpdate' }, async ($, e, next) => {
    const ran = await next(e)

    if (ran.deny === undefined && ran.isError !== true && ran.result.success) {
      const { status, subject } = e
      await update($, steps, list =>
        status === 'deleted'
          ? list.filter(step => step.id !== e.taskId)
          : list.map(step =>
              step.id === e.taskId
                ? {
                    ...step,
                    subject: subject ?? step.subject,
                    status: status ?? step.status,
                  }
                : step,
            ),
      )
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'TodoWrite' }, async ($, e, next) => {
    const ran = await next(e)

    if (ran.deny === undefined && ran.isError !== true) {
      await update($, steps, () =>
        ran.result.newTodos.map((todo, index) => ({
          id: String(index + 1),
          subject: todo.content,
          status: todo.status,
        })),
      )
    }

    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Progress, Text } = $.ui.resolve(e)
    const list: Step[] = await read($, steps)
    const state = await read($, loaded)
    const done = list.filter(step => step.status === 'completed').length

    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>Playbook steps</Text>
          {list.length === 0 ? (
            <Text dimColor>
              None yet. /ostack-mode copies its playbook into the task list.
            </Text>
          ) : (
            <Progress
              label="Steps done"
              value={done}
              max={list.length}
              valueText={`${done} of ${list.length}`}
            />
          )}
          {list.map(step => (
            <Text
              dimColor={step.status === 'completed'}
              color={step.status === 'in_progress' ? 'suggestion' : undefined}
            >
              {STEP_MARK[step.status]} {step.subject}
            </Text>
          ))}
        </Box>

        {state === null && <Text dimColor>Reading the repository…</Text>}
        {state !== null && state.status === 'error' && (
          <Box flexDirection="column">
            <Text color="error">onto view failed</Text>
            <Text>{state.message}</Text>
          </Box>
        )}
        {state !== null && state.status === 'ok' && (
          <Box flexDirection="column" gap={1}>
            <Box flexDirection="column">
              <Text bold>Next up</Text>
              {state.plan.order.length === 0 && (
                <Text dimColor>No open Task.</Text>
              )}
              {state.plan.order.map(id => {
                const task = state.tasks.find(one => one.id === id)

                return (
                  <Text color={task?.blocked ? 'error' : undefined}>
                    {id} at {task?.stage ?? '?'}
                    {task !== undefined && task.blocked_by.length > 0
                      ? ` (after ${task.blocked_by.join(', ')})`
                      : ''}
                    {' · '}
                    {task?.title ?? ''}
                  </Text>
                )
              })}
            </Box>

            <Box flexDirection="column">
              <Text bold>Requirements</Text>
              {Object.entries(state.plan.requirements_by_status)
                .filter(([, ids]) => ids.length > 0)
                .map(([status, ids]) => (
                  <Text>
                    {status}: {ids.length}
                    {status === 'done' ? '' : ` (${ids.join(', ')})`}
                  </Text>
                ))}
            </Box>

            <Box flexDirection="column">
              <Text bold>Decisions in force</Text>
              {state.plan.decisions_in_force.map(decision => (
                <Text wrap="truncate-end">
                  {decision.id} {decision.title}
                </Text>
              ))}
              {state.plan.superseded_decisions.map(decision => (
                <Text dimColor wrap="truncate-end">
                  {decision.id} superseded by {decision.superseded_by ?? '?'}
                </Text>
              ))}
            </Box>

            {state.plan.open_change_requests.length > 0 && (
              <Box flexDirection="column">
                <Text bold>Open ontology change requests</Text>
                {state.plan.open_change_requests.map(request => (
                  <Text color="warning">
                    {request.id} [{request.status}] {request.term}
                  </Text>
                ))}
              </Box>
            )}
          </Box>
        )}
        <Button key="refresh" label="Refresh" onPress={() => refresh($)} />
      </Box>
    )
  })
}
