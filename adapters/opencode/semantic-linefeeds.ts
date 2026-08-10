// opencode plugin: enforce semantic linefeeds on edit/write via the core CLI.
// Install: copy this file AND scripts/check_linefeeds.py into
// ~/.config/opencode/plugins/ (they must sit side by side), or set
// SEMANTIC_LINEFEEDS_CHECK to the script's absolute path.
import type { Plugin } from "@opencode-ai/plugin"

// Module-private: opencode's loader calls every export as a plugin factory
// and treats the return value as a hooks object,
// so a helper export whose call returns null crashes the server.
// Models with native patch support get an apply_patch tool instead of edit/write;
// its Codex-grammar patch goes to the core's codex parser.
function buildCheck(
  tool: string,
  args: Record<string, unknown>,
): { payload: string; agent: "claude" | "codex" } | null {
  if (tool === "apply_patch") {
    const patch = args.patchText as string | undefined
    if (!patch) return null
    return {
      agent: "codex",
      payload: JSON.stringify({
        tool_name: "apply_patch",
        tool_input: { command: patch },
      }),
    }
  }
  if (tool !== "edit" && tool !== "write") return null
  const filePath = args.filePath as string | undefined
  const text = (tool === "edit" ? args.newString : args.content) as
    | string
    | undefined
  if (!filePath || !text) return null
  return {
    agent: "claude",
    payload: JSON.stringify({
      tool_name: "Edit",
      tool_input: { file_path: filePath, new_string: text },
    }),
  }
}

// Non-blocking findings exit 0,
// arriving as the hosts' additional-context object on stdout,
// since exit-0 stderr reaches no model.
//
// Three outcomes, and the caller treats each differently.
// `readable` false means stdout held something this plugin could not interpret,
// which is a configuration problem worth one word to the user.
// A readable payload with null advice is the ordinary clean result.
type Advisory = { readable: true; advice: string | null } | { readable: false }

// Ceiling on remembered sessions, so a long-lived plugin instance cannot grow one.
const MAX_WARNED_SESSIONS = 256

function advisoryFrom(stdout: string): Advisory {
  const raw = stdout.trim()
  if (!raw) return { readable: true, advice: null }
  try {
    const parsed = JSON.parse(raw) as {
      hookSpecificOutput?: { additionalContext?: unknown }
    }
    const context = parsed?.hookSpecificOutput?.additionalContext
    if (typeof context !== "string") return { readable: false }
    return { readable: true, advice: context.trim() || null }
  } catch {
    return { readable: false }
  }
}


export const SemanticLinefeeds: Plugin = async ({ $ }) => {
  const script =
    process.env.SEMANTIC_LINEFEEDS_CHECK ??
    new URL("./check_linefeeds.py", import.meta.url).pathname
  // Said once per session, not once per edit:
  // only a human can repair a mismatched install,
  // so repeating the notice would crowd the model's context for no gain.
  //
  // Keyed by session rather than by a flag on this closure,
  // because opencode does not document how long a plugin instance lives.
  // If it is one per session the two agree;
  // under a longer-lived instance a flag would silence every later session,
  // and under a shorter-lived one it would repeat within a session.
  // Keying by session is right in all three cases.
  const warnedSessions = new Set<string>()
  return {
    "tool.execute.after": async (input, output) => {
      const args = (input as { args?: Record<string, unknown> }).args ?? {}
      const check = buildCheck(input.tool, args)
      if (!check) return
      let proc
      try {
        proc = await $`printf '%s' ${check.payload} | python3 ${script} --hook ${check.agent}`
          .quiet()
          .nothrow()
      } catch {
        return // advisory tool: a broken checker must never break the agent
      }
      if (proc.exitCode === 2) {
        output.output += `\n\n${proc.stderr.toString().trim()}`
        return // one report, on one stream; stdout carries nothing here
      }
      if (proc.exitCode !== 0) return
      const result = advisoryFrom(proc.stdout?.toString() ?? "")
      if (!result.readable) {
        // Never echo what could not be read: it is transport, not advice.
        const session = (input as { sessionID?: string }).sessionID ?? ""
        if (warnedSessions.has(session)) return
        // A broken install warns once per session forever,
        // so the set is bounded rather than left to grow with session count.
        // Dropping the history costs at most one repeated notice.
        if (warnedSessions.size >= MAX_WARNED_SESSIONS) warnedSessions.clear()
        warnedSessions.add(session)
        output.output +=
          "\n\nsemantic-linefeeds: the checker replied in a shape this plugin" +
          " could not read, so advisory findings are being dropped." +
          " Tell the user that check_linefeeds.py should come from the same release" +
          " as this plugin, either beside it or at the path in SEMANTIC_LINEFEEDS_CHECK." +
          " Do not try to repair the installation yourself."
        return
      }
      if (result.advice) output.output += `\n\n${result.advice}`
    },
  }
}
