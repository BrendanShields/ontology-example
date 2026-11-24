import type { EngineInterface } from 'claude-code'

// Runs `bin/onto view --format json` at the monorepo root and hands back what
// it printed. This file is the same in each of the three mods under mods/:
// a mod can only import files of its own folder.

export type Ran =
  | { status: 'ok'; view: unknown }
  | { status: 'error'; message: string }

// The monorepo root: the nearest folder, from the session's own upwards, that
// holds onto.toml.
export async function findRoot($: EngineInterface): Promise<string | null> {
  let dir = await $.session.cwd()

  for (let depth = 0; depth < 12; depth += 1) {
    try {
      await $.fs.stat(`${dir}/onto.toml`)

      return dir
    } catch {
      const parent = dir.replace(/\/[^/]+\/?$/, '')

      if (parent === dir || parent === '') {
        return null
      }
      dir = parent
    }
  }

  return null
}

export async function runView($: EngineInterface): Promise<Ran> {
  const root = await findRoot($)

  if (root === null) {
    return {
      status: 'error',
      message: 'No onto.toml here. Start Claude Code inside the monorepo.',
    }
  }
  try {
    const ran = await $.process.run(
      [`${root}/bin/onto`, 'view', '--format', 'json'],
      { cwd: root, timeoutMs: 30_000 },
    )

    if (ran.exitCode !== 0) {
      return {
        status: 'error',
        message: (ran.stderr || ran.stdout).trim().slice(0, 400),
      }
    }

    return { status: 'ok', view: JSON.parse(ran.stdout) as unknown }
  } catch (error) {
    return { status: 'error', message: String(error).slice(0, 400) }
  }
}
